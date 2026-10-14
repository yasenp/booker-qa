"""Verify invalid-input assertions and cleanup against controlled server behavior."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from booker_qa.bookings import BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload


@pytest.fixture(scope="module")
def validation():
    spec = importlib.util.spec_from_file_location("validation_checks_under_test",
                                                Path(__file__).parents[1] / "live/test_validation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Invalid-input assertions must require both correct rejection and preserved state.
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
@pytest.mark.parametrize("behavior", ["reject_400", "reject_422", "accept_200", "server_500", "reject_but_change"])
def test_invalid_input_status_state_and_cleanup(validation, method, behavior):
    """Run the live rejection helper against clean 400/422 responses, accepted input, HTTP 500,
    or a rejection that still changes state.

    Type: Controlled validation assertion check.

    Expected: Only clean rejection passes. Other cases raise AssertionError, POST uses a
    distinct guest, and all returned IDs remain registered and are cleaned up.

    Cases: POST/PUT/PATCH x 5 response/state behaviors.

    Scope: This validates the test oracle and ownership handling; it does not claim hosted
    validation behavior.
    """
    records, invalid_requests = {}, []

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-validation-token"})
        if request.method == "POST" and not records:
            records[1] = json.loads(request.content)
            return httpx.Response(200, json={"bookingid": 1, "booking": deepcopy(records[1])})
        if request.method in {"POST", "PUT", "PATCH"}:
            payload = json.loads(request.content)
            invalid_requests.append(payload)
            status = {"reject_400": 400, "reject_422": 422, "accept_200": 200,
                      "server_500": 500, "reject_but_change": 422}[behavior]
            if behavior in {"accept_200", "reject_but_change"}:
                if request.method == "POST":
                    records[2] = payload
                    return httpx.Response(status, json={"bookingid": 2, "booking": deepcopy(payload)})
                records[1].update(payload)
                return httpx.Response(status, json=deepcopy(records[1]))
            return httpx.Response(status, json={"reason": "Invalid input"})
        booking_id = int(request.url.path.rsplit("/", 1)[1])
        if request.method == "DELETE":
            records.pop(booking_id)
            return httpx.Response(201)
        return httpx.Response(200, json=deepcopy(records[booking_id]))

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    try:
        booking, _ = registry.create(booking_payload())
        if behavior in {"reject_400", "reject_422"}:
            validation.assert_invalid_booking_rejected(api, registry, booking, method,
                                                       {"totalprice": "abc"}, "price_string")
        else:
            with pytest.raises(AssertionError):
                validation.assert_invalid_booking_rejected(api, registry, booking, method,
                                                           {"totalprice": "abc"}, "price_string")
        if method == "POST":
            assert invalid_requests[0]["firstname"] != booking.payload["firstname"]
        expected_ids = [1, 2] if method == "POST" and behavior in {"accept_200", "reject_but_change"} else [1]
        assert registry.ids == expected_ids
    finally:
        try:
            registry.cleanup()
        finally:
            api.close()
    assert records == {}
