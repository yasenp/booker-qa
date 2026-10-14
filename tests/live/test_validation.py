"""Invalid booking inputs must be rejected without corrupting stored state."""
from copy import deepcopy
import pytest

from booker_qa.data import booking_payload
from booker_qa.evidence import json_diff
from reporting import assert_booking_matches, attach_json, compare, response_body

pytestmark = pytest.mark.live


def read_state(api, booking):
    response = api.request("GET", f"/booking/{booking.booking_id}")
    assert response.status_code == 200, "Owned booking unavailable"
    return response_body(response)


# Invalid scalar types and nested dates must be rejected by both full and partial updates.
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize("invalid", ["price_string", "boolean_string", "dates_null", "checkin_invalid",
                                    "checkout_number", "firstname_number"])
def test_updates_reject_invalid_field_types(api, booking, method, invalid):
    changes = {
        "price_string": {"totalprice": "abc"},
        "boolean_string": {"depositpaid": "false"},
        "dates_null": {"bookingdates": None},
        "checkin_invalid": {"bookingdates": {**booking.payload["bookingdates"], "checkin": "not-a-date"}},
        "checkout_number": {"bookingdates": {**booking.payload["bookingdates"], "checkout": 99}},
        "firstname_number": {"firstname": 123},
    }[invalid]
    payload = {**deepcopy(booking.payload), **changes} if method == "PUT" else changes
    response = api.request(method, f"/booking/{booking.booking_id}", json=payload, authenticated=True)
    persisted = api.request("GET", f"/booking/{booking.booking_id}")
    differences = compare("Invalid update must leave the full booking unchanged", booking.payload, response_body(persisted))
    attach_json("Invalid field rejection", {"method": method, "case": invalid,
                "expected_statuses": [400, 422], "actual_status": response.status_code,
                "get_status": persisted.status_code, "response": response_body(response)})
    assert response.status_code in {400, 422}, f"Invalid {invalid} in {method}: HTTP {response.status_code}; {differences}"
    assert persisted.status_code == 200
    assert not differences, f"Rejected update changed state: {differences}"


# Clients must not replace booking IDs or storage metadata; both test-owned bookings must survive unchanged.
@pytest.mark.parametrize("field", ["bookingid", "meta"])
def test_patch_rejects_internal_fields(api, registry, field):
    first, _ = registry.create()
    second, _ = registry.create()
    payload = {field: second.booking_id if field == "bookingid" else {"revision": -1, "created": 0}}
    if field == "bookingid":
        # If the API aliases the first record to the second ID, two records can share that owned ID.
        # Register it twice BEFORE mutation so teardown deletes both even when assertions fail.
        registry.ids.append(second.booking_id)
    response = api.request("PATCH", f"/booking/{first.booking_id}", json=payload, authenticated=True)
    states = [api.request("GET", f"/booking/{handle.booking_id}") for handle in (first, second)]
    actual = [{"id": handle.booking_id, "status": state.status_code, "booking": response_body(state)}
              for handle, state in zip((first, second), states)]
    expected = [{"id": handle.booking_id, "status": 200, "booking": handle.payload} for handle in (first, second)]
    differences = compare("Internal-field update preserves both owned bookings", expected, actual)
    attach_json("Internal-field rejection", {"field": field, "expected_statuses": [400, 422],
                "actual_status": response.status_code, "response": response_body(response),
                "owned_ids": [first.booking_id, second.booking_id]})
    assert response.status_code in {400, 422}, f"Internal field {field} must be rejected; HTTP {response.status_code}; {differences}"
    assert not differences, f"Internal-field update changed resource identity or state: {differences}"


# Malformed IDs must not resolve to the numeric prefix or access/mutate its booking.
@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("suffix", ["abc", ".9"], ids=["text-suffix", "fractional-id"])
def test_resource_ids_require_exact_integer(api, booking, method, suffix):
    kwargs = {} if method in {"GET", "DELETE"} else {
        "json": {**booking.payload, "totalprice": 765} if method == "PUT" else {"totalprice": 765}}
    response = api.request(method, f"/booking/{booking.booking_id}{suffix}",
                           authenticated=method != "GET", **kwargs)
    persisted = api.request("GET", f"/booking/{booking.booking_id}")
    differences = compare("Malformed resource ID cannot affect the valid numeric ID",
                          {"status": 200, "booking": booking.payload},
                          {"status": persisted.status_code, "booking": response_body(persisted)})
    attach_json("Strict resource ID validation", {"method": method, "suffix": suffix,
                "expected_statuses": [400, 404, 422], "actual_status": response.status_code,
                "response": response_body(response)})
    assert response.status_code in {400, 404, 422}, f"Malformed ID resolved through {method}: HTTP {response.status_code}; {differences}"
    assert not differences, f"Malformed ID changed the valid resource: {differences}"


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
