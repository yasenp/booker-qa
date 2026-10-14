"""Controlled retry, prerequisite recovery, and cleanup behavior without public sandbox access."""

import httpx
import pytest

from booker_qa.bookings import BookingHandle, BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload
from booker_qa.evidence import EvidenceCollector


# A transient read failure must retry with bounded exponential backoff.
def test_get_retries_transient_failure_then_returns_response():
    """Send GET /ping through MockTransport and record the requested sleep durations.

    Type: Controlled transport recovery.

    Expected: The third response returns 200 after exactly three attempts and delays of 0.25
    and 0.5 seconds.

    Cases: ConnectTimeout, then 503, then 200.
    """
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


# Repeated read timeouts must stop at the configured attempt limit.
def test_get_retry_exhaustion_is_visible():
    """Make every modeled health GET raise a transport timeout with sleeping disabled.

    Type: Controlled transport exhaustion.

    Expected: ReadTimeout reaches the caller after exactly three attempts rather than being
    converted into a passing result.

    Cases: 3 consecutive ReadTimeout responses.
    """
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


# A mutation with an unknown outcome must not be blindly replayed.
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_uncertain_writes_are_never_transport_retried(method):
    """Raise ReadTimeout when the selected mutation is sent through MockTransport.

    Type: Controlled safe-retry negative.

    Expected: The exception propagates after one request, with no automatic transport
    replay.

    Cases: POST, PUT, PATCH, and DELETE.

    Scope: The model does not establish whether a server committed the write; uncertainty is
    intentionally preserved.
    """
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


# Missing prerequisites must be recreated once, with exhaustion remaining visible.
@pytest.mark.parametrize("always_missing", [False, True])
def test_missing_prerequisite_recovery_is_bounded(always_missing):
    """Model GET 404 for the original owned ID, create one replacement, and vary its
    availability.

    Type: Controlled sandbox recovery.

    Expected: A surviving replacement is returned; repeated absence raises RuntimeError.
    Exactly two IDs are tracked, one recovery is recorded, and both IDs are attempted during
    cleanup.

    Cases: Replacement survives or remains missing.
    """
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


# Cleanup must continue after one HTTP failure and report the failed owned ID.
def test_cleanup_attempts_all_owned_ids_and_reports_failure():
    """Register two modeled owned IDs and call registry cleanup.

    Type: Controlled cleanup resilience.

    Expected: Both DELETE requests are attempted in order and cleanup raises RuntimeError
    identifying the first ID and HTTP 500.

    Cases: First DELETE returns 500; second returns 201.
    """
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


# A confirmed connection-establishment failure may retry a mutation before it is sent.
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_connect_failure_before_send_can_be_retried(method):
    """Make the first transport attempt raise ConnectTimeout and the next return 200.

    Type: Controlled safe-retry positive.

    Expected: The selected mutation returns 200 after exactly two attempts.

    Cases: POST, PUT, PATCH, and DELETE.

    Scope: This covers pre-send connection failure; response-loss retries remain prohibited
    by separate tests.
    """
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


# Cleanup may tolerate DELETE 405 only when GET confirms that the record is absent.
@pytest.mark.parametrize("get_status", [404, 200, 500])
def test_delete_405_requires_confirmed_absence(get_status):
    """Return 405 for deletion of an owned ID and vary the follow-up GET response.

    Type: Controlled cleanup status handling.

    Expected: Only GET 404 permits successful cleanup; a present record or failed
    confirmation raises RuntimeError.

    Cases: Confirming GET returns 404, 200, or 500.
    """
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


# A present prerequisite must retain its ID and payload without extra creation.
def test_available_prerequisite_is_reused():
    """Create a modeled booking and call registry.ensure while its GET remains successful.

    Type: Controlled sandbox recovery positive.

    Expected: The payload and ID are unchanged, no recovery is recorded, and the only calls
    are the initial POST and one GET.

    Cases: One available owned booking.
    """
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


# Recovery must not mistake authorization, server, transport, or JSON failures for a purge.
@pytest.mark.parametrize("behavior", ["forbidden", "server_error", "timeout", "invalid_json"])
def test_prerequisite_recovery_requires_confirmed_404(behavior):
    """Run registry.ensure against each non-404 failure on an existing tracked handle.

    Type: Controlled sandbox recovery negative.

    Expected: The appropriate exception propagates; ID and recovery history stay unchanged
    and no POST occurs. ReadTimeout uses only the bounded three read attempts.

    Cases: 403, 500, ReadTimeout, and malformed JSON.
    """
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


# DELETE 404 must finish cleanup without a confirmation GET or replacement POST.
def test_cleanup_404_is_terminal_without_recreation():
    """Authenticate and return 404 for the owned record's DELETE, while collecting
    HTTP/lifecycle events.

    Type: Controlled cleanup positive.

    Expected: Only authentication and deletion occur, no recovery is recorded, and one
    cleanup event reports the ID as already absent.

    Cases: One already-absent owned ID.
    """
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


# An uncertain deletion must remain visible while cleanup proceeds to the next owned ID.
def test_cleanup_transport_failure_still_attempts_remaining_ids():
    """Raise ReadTimeout for the first of two owned IDs and return 201 for the second.

    Type: Controlled cleanup resilience.

    Expected: Each ID is attempted once, cleanup raises an error naming the timeout, and
    evidence records failed then deleted outcomes.

    Cases: First DELETE loses its response; second succeeds.

    Scope: No ambiguous DELETE replay is attempted; subsequent cleanup work is still
    performed.
    """
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
