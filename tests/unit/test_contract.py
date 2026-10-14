"""Offline schema, calendar, business-invariant, and comparison-assertion checks."""

import pytest
from jsonschema import ValidationError
from booker_qa.data import booking_payload
from booker_qa.schemas.booking import validate_contract, validate_invariants
from reporting import assert_booking_matches


# Generated test data must satisfy the schema and booking invariants before use.
def test_generated_payload_has_valid_contract_and_business_invariants():
    """Build a booking with the shared factory and pass it through the combined validator.

    Type: Controlled data/schema positive.

    Expected: Validation succeeds with complete nested dates, strict field types,
    nonnegative price, and checkout after check-in.

    Cases: One generated payload.
    """
    validate_invariants(booking_payload())


# Strict schema validation must reject coercible values and malformed booking structures.
@pytest.mark.parametrize("change", [
    {"depositpaid": "true"}, {"totalprice": True}, {"totalprice": "123"},
    {"bookingdates": {"checkin": "2027-02-30", "checkout": "2027-03-01"}},
    {"bookingdates": {"checkin": "2027-01-01T12:00:00Z", "checkout": "2027-01-02"}},
    {"bookingdates": {"checkin": "2027-01-01"}},
    {"unexpected": "value"},
    {"totalprice": 123.0}, {"totalprice": 123.45}, {"totalprice": None},
    {"depositpaid": 0}, {"depositpaid": None},
    {"bookingdates": None}, {"bookingdates": []}, {"bookingdates": "2027-01-01"},
    {"bookingdates": {"checkout": "2027-01-02"}},
    {"bookingdates": {"checkin": "2027-01-01", "checkout": "2027-01-02T12:00:00Z"}},
    {"bookingdates": {"checkin": "2027-1-01", "checkout": "2027-01-02"}},
    {"bookingdates": {"checkin": "2027-02-29", "checkout": "2027-03-01"}},
])
def test_contract_rejects_malformed_wire_values(change):
    """Overlay each malformed change onto a valid generated booking and run the wire-contract
    validator.

    Type: Controlled schema negative.

    Expected: ValidationError is raised for wrong types, missing dates, extra fields,
    impossible calendars, non-padded dates, or timestamps.

    Cases: 19 malformed scalar, nested, date, or extra-field changes.

    Scope: Integer representation is deliberately strict: booleans and floats, including
    123.0, do not satisfy the framework's integer policy.
    """
    with pytest.raises(ValidationError):
        validate_contract({**booking_payload(), **change})


# Valid date strings must still fail the booking rule when checkout is not later.
@pytest.mark.parametrize("dates", [
    {"checkin": "2027-01-02", "checkout": "2027-01-01"},
    {"checkin": "2027-01-01", "checkout": "2027-01-01"},
])
def test_date_order_is_a_separate_business_invariant(dates):
    """Use structurally valid dates that violate chronological order; run schema validation
    before the business validator.

    Type: Controlled invariant negative.

    Expected: The wire schema passes, then validate_invariants raises a checkout-related
    ValueError.

    Cases: Equal and reversed dates.
    """
    payload = {**booking_payload(), "bookingdates": dates}
    validate_contract(payload)
    with pytest.raises(ValueError, match="checkout"):
        validate_invariants(payload)


# A negative integer price must fail the business rule despite a valid wire type.
def test_negative_price_is_a_separate_business_invariant():
    """Apply a negative integer price to a valid generated booking and validate shape
    separately from invariants.

    Type: Controlled invariant negative.

    Expected: Schema validation succeeds, while the business validator raises a
    nonnegative-price ValueError.

    Cases: totalprice = -1.
    """
    payload = {**booking_payload(), "totalprice": -1}
    validate_contract(payload)
    with pytest.raises(ValueError, match="nonnegative"):
        validate_invariants(payload)


# Valid calendar boundaries, zero price, and both deposit flags must remain accepted.
@pytest.mark.parametrize("checkin,checkout,totalprice,depositpaid", [
    ("2028-02-28", "2028-03-01", 0, False),
    ("2028-02-29", "2028-03-01", 1, True),
    ("2028-12-31", "2029-01-01", 200, False),
])
def test_contract_accepts_valid_calendar_and_value_boundaries(checkin, checkout, totalprice, depositpaid):
    """Build complete bookings spanning leap dates or a year boundary and compare each valid
    payload with itself using the reporting assertion.

    Type: Controlled contract boundary positive.

    Expected: Strict contract, logical invariants, and equality checks all succeed.

    Cases: 3 leap-day/year-end/price/deposit combinations.
    """
    payload = {**booking_payload(), "bookingdates": {"checkin": checkin, "checkout": checkout},
               "totalprice": totalprice, "depositpaid": depositpaid}
    assert_booking_matches("Valid boundary booking", payload, payload)


# Identical expected and actual JSON must not allow invalid bookings to pass.
@pytest.mark.parametrize("change", [
    {"totalprice": -1}, {"totalprice": 123.0}, {"depositpaid": 1},
    {"bookingdates": {"checkin": "2027-01-01", "checkout": "2027-01-01"}},
    {"bookingdates": {"checkin": "2027-01-02", "checkout": "2027-01-01"}},
    {"bookingdates": {"checkin": "2027-02-30", "checkout": "2027-03-01"}},
])
def test_matching_payloads_still_require_contract_and_invariants(change):
    """Give assert_booking_matches the same invalid body as both its expected and actual
    values.

    Type: Controlled assertion regression.

    Expected: The comparison still raises AssertionError through schema or invariant
    validation, even though the values match.

    Cases: 6 invalid price, flag, date-format, or date-order changes.
    """
    payload = {**booking_payload(), **change}
    with pytest.raises(AssertionError):
        assert_booking_matches("Invalid booking despite identical values", payload, payload)
