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


# Client validation responses pass; a server error for malformed input must fail normally.
@pytest.mark.parametrize("status", [400, 422, 500])
def test_malformed_filter_requires_client_error(filters, status):
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


# Failed valid-search controls must stop the scenario before any malformed request is sent.
def test_date_filter_control_failure_is_visible(filters):
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
