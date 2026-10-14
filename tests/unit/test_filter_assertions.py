"""Exercise live filter assertions with controlled validation and infrastructure responses."""
import importlib.util
from pathlib import Path

import httpx
import pytest

from booker_qa.bookings import BookingHandle
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload


@pytest.fixture(scope="module")
def filters():
    spec = importlib.util.spec_from_file_location("filters_under_test",
                                                Path(__file__).parents[1] / "live/test_filters.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Malformed-filter assertions must accept validation errors and reject server failures.
@pytest.mark.parametrize("status", [400, 422, 500])
def test_malformed_filter_requires_client_error(filters, status):
    """Run the live check-in validation scenario against a mock that keeps valid controls
    healthy and varies only the malformed-filter response.

    Type: Controlled search assertion check.

    Expected: 400/422 pass the scenario; 500 raises an ordinary assertion with the actual
    status.

    Cases: HTTP 400, 422, and 500.
    """
    payload = booking_payload()

    def respond(request):
        if request.url.params.get("checkin") == "not-a-date":
            return httpx.Response(status, text="Internal Server Error" if status == 500 else "Invalid date")
        if request.url.path == "/booking/1":
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json=[{"bookingid": 1}])

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        if status == 500:
            with pytest.raises(AssertionError, match="got HTTP 500"):
                filters.test_malformed_date_filter_returns_client_error(api, BookingHandle(1, payload), "checkin")
        else:
            filters.test_malformed_date_filter_returns_client_error(api, BookingHandle(1, payload), "checkin")
    finally:
        api.close()


# A failed positive search control must stop malformed-filter validation immediately.
def test_date_filter_control_failure_is_visible(filters):
    """Run the live filter-validation scenario against an unavailable mocked search endpoint.

    Type: Controlled search resilience.

    Expected: The control failure raises AssertionError and no date-filter request is sent.

    Cases: Positive control always returns 503.

    Scope: A general outage must not be mistaken for successful rejection of malformed
    input.
    """
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    try:
        with pytest.raises(AssertionError):
            filters.test_malformed_date_filter_returns_client_error(api, BookingHandle(1, booking_payload()), "checkin")
        assert all("checkin" not in request.url.params for request in requests)
    finally:
        api.close()
