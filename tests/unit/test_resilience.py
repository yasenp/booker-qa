import httpx
import pytest

from booker_qa.bookings import BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload


def test_get_retries_transient_failure_then_returns_response():
    calls, delays = [], []
    def respond(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("simulated", request=request)
        return httpx.Response(503 if len(calls) == 2 else 200)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=delays.append)
    try:
        assert api.request("GET", "/ping").status_code == 200
        assert len(calls) == 3
        assert delays == [0.25, 0.5]
    finally:
        api.close()


def test_get_retry_exhaustion_is_visible():
    calls = []
    def respond(request):
        calls.append(1)
        raise httpx.ReadTimeout("simulated", request=request)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    try:
        with pytest.raises(httpx.ReadTimeout):
            api.request("GET", "/ping")
        assert len(calls) == 3
    finally:
        api.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_uncertain_writes_are_never_transport_retried(method):
    calls = []
    def respond(request):
        calls.append(1)
        raise httpx.ReadTimeout("response lost", request=request)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    try:
        with pytest.raises(httpx.ReadTimeout):
            api.request(method, "/booking/1")
        assert len(calls) == 1
    finally:
        api.close()


@pytest.mark.parametrize("always_missing", [False, True])
def test_missing_prerequisite_recovery_is_bounded(always_missing):
    created, deleted = [], []
    payload = booking_payload()
    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "valid"})
        if request.method == "POST":
            created.append(len(created) + 1)
            return httpx.Response(200, json={"bookingid": created[-1], "booking": payload})
        if request.method == "DELETE":
            deleted.append(request.url.path)
            return httpx.Response(404)
        return httpx.Response(404 if always_missing or request.url.path == "/booking/1" else 200, json=payload)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    try:
        handle, _ = registry.create(payload)
        if always_missing:
            with pytest.raises(RuntimeError, match="bounded"):
                registry.ensure(handle)
        else:
            assert registry.ensure(handle) == payload
        assert created == [1, 2]
        assert registry.recoveries == [(1, 2)]
        registry.cleanup()
        assert deleted == ["/booking/1", "/booking/2"]
    finally:
        api.close()


def test_cleanup_attempts_all_owned_ids_and_reports_failure():
    deleted = []
    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "valid"})
        deleted.append(request.url.path)
        return httpx.Response(500 if request.url.path == "/booking/1" else 201)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    registry.ids = [1, 2]
    try:
        with pytest.raises(RuntimeError, match="1: HTTP 500"):
            registry.cleanup()
        assert deleted == ["/booking/1", "/booking/2"]
    finally:
        api.close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_connect_failure_before_send_can_be_retried(method):
    calls = []
    def respond(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectTimeout("before send", request=request)
        return httpx.Response(200)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    try:
        assert api.request(method, "/booking/1").status_code == 200
        assert len(calls) == 2
    finally:
        api.close()


@pytest.mark.parametrize("get_status", [404, 200])
def test_delete_405_requires_confirmed_absence(get_status):
    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "valid"})
        return httpx.Response(get_status if request.method == "GET" else 405)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    registry.ids = [1]
    try:
        if get_status == 404:
            registry.cleanup()
        else:
            with pytest.raises(RuntimeError, match="HTTP 405"):
                registry.cleanup()
    finally:
        api.close()
