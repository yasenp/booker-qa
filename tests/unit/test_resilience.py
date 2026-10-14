import httpx
import pytest

from booker_qa.bookings import BookingHandle, BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload
from booker_qa.evidence import EvidenceCollector


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


# DELETE 405 is graceful only when an independent GET proves the record is absent.
@pytest.mark.parametrize("get_status", [404, 200, 500])
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


# An available prerequisite must retain its ID and payload without an unnecessary replacement.
def test_available_prerequisite_is_reused():
    payload = booking_payload()
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(200, json={"bookingid": 1, "booking": payload})
        return httpx.Response(200, json=payload)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    try:
        handle, _ = registry.create(payload)
        assert registry.ensure(handle) == payload
        assert handle.booking_id == 1
        assert registry.ids == [1] and registry.recoveries == []
        assert requests == [("POST", "/booking"), ("GET", "/booking/1")]
    finally:
        api.close()


# Forbidden responses, server errors, timeouts, and malformed bodies must not be mistaken for a purge.
@pytest.mark.parametrize("behavior", ["forbidden", "server_error", "timeout", "invalid_json"])
def test_prerequisite_recovery_requires_confirmed_404(behavior):
    payload = booking_payload()
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if behavior == "timeout":
            raise httpx.ReadTimeout("controlled read failure", request=request)
        if behavior == "invalid_json":
            return httpx.Response(200, text="invalid JSON")
        return httpx.Response(403 if behavior == "forbidden" else 500)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    registry = BookingRegistry(api)
    registry.ids = [1]
    handle = BookingHandle(1, payload)
    try:
        error = (httpx.ReadTimeout if behavior == "timeout" else
                 ValueError if behavior == "invalid_json" else httpx.HTTPStatusError)
        with pytest.raises(error):
            registry.ensure(handle)
        assert handle.booking_id == 1 and registry.ids == [1] and registry.recoveries == []
        assert requests == [("GET", "/booking/1")] * (3 if behavior == "timeout" else 1)
    finally:
        api.close()


# DELETE 404 is already successful cleanup; it needs no confirmation GET or replacement POST.
def test_cleanup_404_is_terminal_without_recreation():
    requests = []
    collector = EvidenceCollector()

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        return httpx.Response(404)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), observer=collector)
    registry = BookingRegistry(api)
    registry.ids = [1]
    try:
        registry.cleanup()
        assert requests == [("POST", "/auth"), ("DELETE", "/booking/1")]
        assert registry.recoveries == []
        results = [event for event in collector.snapshot() if event["kind"] == "cleanup_result"]
        assert len(results) == 1
        assert results[0]["booking_id"] == 1
        assert results[0]["delete_status"] == 404 and results[0]["outcome"] == "already absent"
    finally:
        api.close()


# An uncertain cleanup deletion must remain visible while cleanup continues for other owned records.
def test_cleanup_transport_failure_still_attempts_remaining_ids():
    deleted = []
    collector = EvidenceCollector()

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        assert request.method == "DELETE"
        deleted.append(request.url.path)
        if request.url.path == "/booking/1":
            raise httpx.ReadTimeout("controlled response loss", request=request)
        return httpx.Response(201)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), observer=collector)
    registry = BookingRegistry(api)
    registry.ids = [1, 2]
    try:
        with pytest.raises(RuntimeError, match="1: ReadTimeout"):
            registry.cleanup()
        assert deleted == ["/booking/1", "/booking/2"]
        results = [event for event in collector.snapshot() if event["kind"] == "cleanup_result"]
        assert [event["outcome"] for event in results] == ["failed", "deleted"]
    finally:
        api.close()
