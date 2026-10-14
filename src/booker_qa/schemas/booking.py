"""Wire shape and separately named business invariants."""
from datetime import date
from jsonschema import Draft202012Validator, FormatChecker, validators

BOOKING_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["firstname", "lastname", "totalprice", "depositpaid", "bookingdates"],
    "additionalProperties": False,
    "properties": {
        "firstname": {"type": "string"},
        "lastname": {"type": "string"},
        "totalprice": {"type": "integer"},
        "depositpaid": {"type": "boolean"},
        "additionalneeds": {"type": "string"},
        "bookingdates": {
            "type": "object", "required": ["checkin", "checkout"],
            "additionalProperties": False,
            "properties": {key: {"type": "string", "format": "date", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
                           for key in ["checkin", "checkout"]},
        },
    },
}
# Enforce the Python representation of wire integers: bool and 123.0 are not int values.
STRICT_VALIDATOR = validators.extend(Draft202012Validator, type_checker=
    Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda checker, value: type(value) is int))
VALIDATOR = STRICT_VALIDATOR(BOOKING_SCHEMA, format_checker=FormatChecker())
CREATE_VALIDATOR = STRICT_VALIDATOR({
    "type": "object", "required": ["bookingid", "booking"], "additionalProperties": False,
    "properties": {"bookingid": {"type": "integer", "minimum": 1}, "booking": BOOKING_SCHEMA},
}, format_checker=FormatChecker())


def validate_contract(booking: dict) -> None:
    VALIDATOR.validate(booking)


def validate_create_contract(body: dict) -> None:
    """Validate the POST envelope and nested booking without enforcing business rules."""
    CREATE_VALIDATOR.validate(body)


def validate_invariants(booking: dict) -> None:
    validate_contract(booking)
    dates = booking["bookingdates"]
    if date.fromisoformat(dates["checkout"]) <= date.fromisoformat(dates["checkin"]):
        raise ValueError("checkout must be after checkin")
    if booking["totalprice"] < 0:
        raise ValueError("totalprice must be nonnegative")
