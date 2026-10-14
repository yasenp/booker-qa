import pytest
from jsonschema import ValidationError
from booker_qa.data import booking_payload
from booker_qa.schemas.booking import validate_contract, validate_invariants
from reporting import assert_booking_matches


# Generated bookings must satisfy both the wire schema and the date/price business rules.
def test_generated_payload_has_valid_contract_and_business_invariants():
    validate_invariants(booking_payload())


# Scalar coercions, malformed calendars, timestamps, and incomplete nested dates violate the contract.
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
    with pytest.raises(ValidationError):
        validate_contract({**booking_payload(), **change})


# Equal and reversed dates are structurally valid but must fail checkout > checkin.
@pytest.mark.parametrize("dates", [
    {"checkin": "2027-01-02", "checkout": "2027-01-01"},
    {"checkin": "2027-01-01", "checkout": "2027-01-01"},
])
def test_date_order_is_a_separate_business_invariant(dates):
    payload = {**booking_payload(), "bookingdates": dates}
    validate_contract(payload)
    with pytest.raises(ValueError, match="checkout"):
        validate_invariants(payload)


# A negative integer is a valid JSON type but an invalid booking price.
def test_negative_price_is_a_separate_business_invariant():
    payload = {**booking_payload(), "totalprice": -1}
    validate_contract(payload)
    with pytest.raises(ValueError, match="nonnegative"):
        validate_invariants(payload)


# Valid leap-day and year-end stays, zero price, and both boolean values must pass strict validation.
@pytest.mark.parametrize("checkin,checkout,totalprice,depositpaid", [
    ("2028-02-28", "2028-03-01", 0, False),
    ("2028-02-29", "2028-03-01", 1, True),
    ("2028-12-31", "2029-01-01", 200, False),
])
def test_contract_accepts_valid_calendar_and_value_boundaries(checkin, checkout, totalprice, depositpaid):
    payload = {**booking_payload(), "bookingdates": {"checkin": checkin, "checkout": checkout},
               "totalprice": totalprice, "depositpaid": depositpaid}
    assert_booking_matches("Valid boundary booking", payload, payload)


# Equal expected/actual bodies cannot make invalid prices, flags, dates, or date order pass.
@pytest.mark.parametrize("change", [
    {"totalprice": -1}, {"totalprice": 123.0}, {"depositpaid": 1},
    {"bookingdates": {"checkin": "2027-01-01", "checkout": "2027-01-01"}},
    {"bookingdates": {"checkin": "2027-01-02", "checkout": "2027-01-01"}},
    {"bookingdates": {"checkin": "2027-02-30", "checkout": "2027-03-01"}},
])
def test_matching_payloads_still_require_contract_and_invariants(change):
    payload = {**booking_payload(), **change}
    with pytest.raises(AssertionError):
        assert_booking_matches("Invalid booking despite identical values", payload, payload)
