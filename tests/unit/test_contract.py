import pytest
from jsonschema import ValidationError
from booker_qa.data import booking_payload
from booker_qa.schemas.booking import validate_contract, validate_invariants


def test_generated_payload_has_valid_contract_and_business_invariants():
    validate_invariants(booking_payload())


@pytest.mark.parametrize("change", [
    {"depositpaid": "true"}, {"totalprice": True}, {"totalprice": "123"},
    {"bookingdates": {"checkin": "2027-02-30", "checkout": "2027-03-01"}},
    {"bookingdates": {"checkin": "2027-01-01T12:00:00Z", "checkout": "2027-01-02"}},
    {"bookingdates": {"checkin": "2027-01-01"}},
    {"unexpected": "value"},
])
def test_contract_rejects_malformed_wire_values(change):
    with pytest.raises(ValidationError):
        validate_contract({**booking_payload(), **change})


@pytest.mark.parametrize("dates", [
    {"checkin": "2027-01-02", "checkout": "2027-01-01"},
    {"checkin": "2027-01-01", "checkout": "2027-01-01"},
])
def test_date_order_is_a_separate_business_invariant(dates):
    payload = {**booking_payload(), "bookingdates": dates}
    validate_contract(payload)
    with pytest.raises(ValueError, match="checkout"):
        validate_invariants(payload)


def test_negative_price_is_a_separate_business_invariant():
    payload = {**booking_payload(), "totalprice": -1}
    validate_contract(payload)
    with pytest.raises(ValueError, match="nonnegative"):
        validate_invariants(payload)
