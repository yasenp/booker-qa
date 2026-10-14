"""Invalid booking inputs must be rejected without corrupting stored state."""
import pytest

from booker_qa.data import booking_payload
from booker_qa.evidence import json_diff
from reporting import assert_booking_matches, attach_json, response_body

pytestmark = pytest.mark.live


def read_state(api, booking):
    response = api.request("GET", f"/booking/{booking.booking_id}")
    assert response.status_code == 200, "Owned booking unavailable"
    return response_body(response)


# Invalid price and boolean strings must be rejected without changing any booking field.
def test_patch_rejects_invalid_types_without_mutation(api, registry):
    payload = {**booking_payload(), "depositpaid": False}
    booking, _ = registry.create(payload)
    assert_booking_matches("Invalid-type PATCH baseline", payload, read_state(api, booking))
    response = api.request("PATCH", f"/booking/{booking.booking_id}",
                           json={"totalprice": "abc", "depositpaid": "false"}, authenticated=True)
    after = read_state(api, booking)
    differences = json_diff(payload, after)
    attach_json("Invalid-type PATCH rejection", {
        "expected_statuses": [400, 422], "actual_status": response.status_code,
        "response": response_body(response), "before": payload, "after": after, "differences": differences,
    })
    assert response.status_code in {400, 422}, (
        f"Invalid PATCH must be rejected, got HTTP {response.status_code}; state differences: {differences}"
    )
    assert not differences, f"Rejected PATCH changed booking state: {differences}"
    assert_booking_matches("Rejected PATCH leaves state unchanged", payload, after)


# Missing mandatory POST fields must return a client validation error, with valid POST controls working.
def test_incomplete_post_returns_client_error(api, registry, booking):
    assert_booking_matches("Valid POST control before invalid input", booking.payload, read_state(api, booking))
    response = api.request("POST", "/booking", json={"firstname": booking_payload()["firstname"]})
    body = response_body(response)
    # Track an unexpected successful creation so a failing assertion still cleans it up.
    if isinstance(body, dict) and type(body.get("bookingid")) is int and body["bookingid"] > 0:
        registry.ids.append(body["bookingid"])
    attach_json("Incomplete POST validation", {
        "expected_statuses": [400, 422], "actual_status": response.status_code, "response": body,
    })
    control, created = registry.create()
    assert_booking_matches("Valid POST control after invalid input", control.payload, created)
    assert_booking_matches("Persisted POST control after invalid input", control.payload, read_state(api, control))
    assert response.status_code in {400, 422}, (
        f"Incomplete POST must return a client validation error, got HTTP {response.status_code}"
    )
