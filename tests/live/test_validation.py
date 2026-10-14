"""Invalid booking inputs must be rejected without corrupting stored state."""
from copy import deepcopy
from datetime import date, timedelta
import pytest

from booker_qa.data import booking_payload
from booker_qa.evidence import json_diff
from reporting import assert_booking_matches, attach_json, compare, response_body

pytestmark = pytest.mark.live

INVALID_FIELD_CASES = (
    "price_string", "price_boolean", "price_fractional", "price_null",
    "boolean_string", "boolean_number", "boolean_null",
    "dates_null", "dates_array", "dates_string",
    "checkin_invalid", "checkin_timestamp", "checkout_number", "checkout_impossible", "firstname_number",
)


def invalid_field_changes(case, payload):
    dates = payload["bookingdates"]
    return {
        "price_string": {"totalprice": "abc"},
        "price_boolean": {"totalprice": True},
        "price_fractional": {"totalprice": 123.45},
        "price_null": {"totalprice": None},
        "boolean_string": {"depositpaid": "false"},
        "boolean_number": {"depositpaid": 0},
        "boolean_null": {"depositpaid": None},
        "dates_null": {"bookingdates": None},
        "dates_array": {"bookingdates": []},
        "dates_string": {"bookingdates": dates["checkin"]},
        "checkin_invalid": {"bookingdates": {**dates, "checkin": "not-a-date"}},
        "checkin_timestamp": {"bookingdates": {**dates, "checkin": dates["checkin"] + "T12:00:00Z"}},
        "checkout_number": {"bookingdates": {**dates, "checkout": 99}},
        "checkout_impossible": {"bookingdates": {**dates, "checkout": "2027-02-30"}},
        "firstname_number": {"firstname": 123},
    }[case]


def assert_invalid_booking_rejected(api, registry, booking, method, changes, case, statuses=(400, 422)):
    # A separate unique guest prevents an implemented duplicate rule from masking invalid POST data.
    base = booking_payload() if method == "POST" else deepcopy(booking.payload)
    payload = changes if method == "PATCH" else {**base, **changes}
    path = "/booking" if method == "POST" else f"/booking/{booking.booking_id}"
    response = api.request(method, path, json=payload, authenticated=method != "POST")
    body = response_body(response)
    created_id = body.get("bookingid") if method == "POST" and isinstance(body, dict) else None
    created = None
    if type(created_id) is int and created_id > 0 and created_id != booking.booking_id:
        # Register any returned ID before checking status or schema, including erroneous rejection responses.
        registry.ids.append(created_id)
        created = api.request("GET", f"/booking/{created_id}")
    persisted = api.request("GET", f"/booking/{booking.booking_id}")
    differences = compare("Invalid input must leave the existing booking unchanged",
                          booking.payload, response_body(persisted))
    attach_json("Deep validation rejection", {
        "case": case, "method": method, "expected_statuses": list(statuses),
        "actual_status": response.status_code, "response": body,
        "original_get_status": persisted.status_code,
        "unexpected_booking_id": created_id,
        "created_get_status": created.status_code if created is not None else None,
        "created_body": response_body(created) if created is not None else None,
    })
    assert response.status_code in statuses, (
        f"{method} must reject {case} with HTTP {list(statuses)}; got HTTP {response.status_code}. "
        f"Existing-state differences: {differences}"
    )
    assert persisted.status_code == 200
    assert not differences, f"Rejected input changed the original booking: {differences}"
    assert created is None or created.status_code == 404, "Rejected input still created a booking"


def read_state(api, booking):
    response = api.request("GET", f"/booking/{booking.booking_id}")
    assert response.status_code == 200, "Owned booking unavailable"
    return response_body(response)


# Invalid scalar types and nested dates must be rejected by both full and partial updates.
@pytest.mark.parametrize("method", ["PUT", "PATCH"])
@pytest.mark.parametrize("invalid", INVALID_FIELD_CASES)
def test_updates_reject_invalid_field_types(api, registry, booking, method, invalid):
    assert_invalid_booking_rejected(api, registry, booking, method,
                                    invalid_field_changes(invalid, booking.payload), invalid)


# Invalid scalar types and malformed nested dates must also be rejected during booking creation.
@pytest.mark.parametrize("invalid", INVALID_FIELD_CASES)
def test_creates_reject_invalid_field_types(api, registry, booking, invalid):
    assert_invalid_booking_rejected(api, registry, booking, "POST",
                                    invalid_field_changes(invalid, booking.payload), invalid)


# POST and PUT require both nested dates; a partial PATCH is covered by the preservation test instead.
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("missing", ["checkin", "checkout"])
def test_full_requests_require_both_dates(api, registry, booking, method, missing):
    dates = {key: value for key, value in booking.payload["bookingdates"].items() if key != missing}
    assert_invalid_booking_rejected(api, registry, booking, method, {"bookingdates": dates}, "missing_" + missing)


# Checkout must be later than check-in and totalprice nonnegative on every write operation.
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH"])
@pytest.mark.parametrize("invalid", ["reversed_dates", "equal_dates", "negative_price"])
def test_business_invalid_values_rejected(api, registry, booking, method, invalid):
    dates = booking.payload["bookingdates"]
    if invalid == "negative_price":
        changes = {"totalprice": -1}
    elif invalid == "equal_dates":
        changes = {"bookingdates": {"checkin": dates["checkin"], "checkout": dates["checkin"]}}
    else:
        changes = {"bookingdates": {"checkin": dates["checkout"], "checkout": dates["checkin"]}}
    assert_invalid_booking_rejected(api, registry, booking, method, changes, invalid, statuses=(400, 409, 422))


# Client-calculated totals, true/false flags, and complete dates must survive POST, PUT, PATCH, and GET exactly.
@pytest.mark.parametrize("nights,nightly_rate,depositpaid", [(1, 0, False), (1, 1, True),
                                                         (3, 125, False), (7, 199, True)])
def test_calculated_price_and_deposit_round_trip(api, registry, nights, nightly_rate, depositpaid):
    payload = booking_payload()
    checkin = date.fromisoformat(payload["bookingdates"]["checkin"])
    payload["bookingdates"]["checkout"] = (checkin + timedelta(days=nights)).isoformat()
    duration = (date.fromisoformat(payload["bookingdates"]["checkout"]) - checkin).days
    payload.update(totalprice=duration * nightly_rate, depositpaid=depositpaid)
    attach_json("Client-calculated price expectation", {
        "nights": duration, "nightly_rate": nightly_rate, "expected_totalprice": payload["totalprice"],
        "depositpaid": depositpaid,
        "scope": "Client-side test-data calculation and exact API persistence; no server rate/tax formula is exposed",
    })
    booking, body = registry.create(payload)
    assert_booking_matches("POST deep contract and invariants", payload, body)
    assert_booking_matches("POST persisted price, flag, and dates", payload, read_state(api, booking))
    updated = deepcopy(payload)
    updated["bookingdates"]["checkout"] = (checkin + timedelta(days=nights + 1)).isoformat()
    updated.update(totalprice=(duration + 1) * nightly_rate, depositpaid=not depositpaid)
    response = api.request("PUT", f"/booking/{booking.booking_id}", json=updated, authenticated=True)
    assert response.status_code == 200
    assert_booking_matches("PUT recalculated total and changed flag", updated, response_body(response))
    assert_booking_matches("PUT persisted deep contract", updated, read_state(api, booking))
    # A deposit flag changes payment state; it must not silently change the submitted total or dates.
    response = api.request("PATCH", f"/booking/{booking.booking_id}",
                           json={"depositpaid": depositpaid}, authenticated=True)
    expected = {**updated, "depositpaid": depositpaid}
    assert response.status_code == 200
    assert_booking_matches("PATCH deposit flag preserves total and dates", expected, response_body(response))
    assert_booking_matches("PATCH persisted deep contract", expected, read_state(api, booking))


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
