"""Allure presentation helpers; called only by the owning test/fixture thread."""
import json

import allure
from jsonschema import ValidationError

from booker_qa.evidence import json_diff, sanitize
from booker_qa.schemas.booking import validate_invariants


def attach_json(name, value):
    allure.attach(json.dumps(sanitize(value), indent=2, ensure_ascii=False), name, allure.attachment_type.JSON)


def compare(name, expected, actual):
    differences = json_diff(expected, actual)
    attach_json(name, {"matches": not differences, "expected": expected, "actual": actual,
                       "differences": differences})
    return differences


def assert_booking_matches(name, expected, actual):
    """Attach evidence, then enforce the schema, business invariants, and exact values."""
    differences = compare(name, expected, actual)
    try:
        validate_invariants(actual)
    except (ValidationError, ValueError) as error:
        message = error.message if isinstance(error, ValidationError) else str(error)
        attach_json("Booking contract or invariant violation", {"valid": False, "reason": message})
        raise AssertionError(f"{name}: {message}") from error
    assert not differences, f"{name}: {differences}"


def response_body(response):
    try:
        return response.json()
    except ValueError:
        return {"body": "[non-JSON body omitted]"}


def render_events(events, start=0):
    """Chronological start order for completed attempts; retain real timings in data."""
    for index, event in enumerate(sorted(events[start:], key=lambda event: event.get("timestamp_ns", 0)), start + 1):
        kind = event["kind"]
        phase = event.get("phase", "call")
        if kind == "http":
            title = f"{index:02d}. [{phase}] {event['method']} {event['path']} — attempt {event['attempt']}"
            outcome = event["error"] or f"HTTP {event['status']}"
            with allure.step(f"{title} → {outcome} ({event['elapsed_ms']} ms)"):
                attach_json("Request", {"request_id": event["request_id"], "method": event["method"],
                                       "path": event["path"], "headers": event["request_headers"],
                                       "payload": event["request_body"]})
                attach_json("Response", {"request_id": event["request_id"], "status": event["status"],
                                        "headers": event["response_headers"], "payload": event["response_body"],
                                        "elapsed_ms": event["elapsed_ms"], "error": event["error"]})
        else:
            titles = {"retry_scheduled": "Retry scheduled", "auth_acquired": "Token acquired (value omitted)",
                      "auth_refresh": "Authentication rejected; refresh and retry once",
                      "prerequisite_recreated": "Missing prerequisite recreated",
                      "recovery_exhausted": "Prerequisite recovery exhausted", "cleanup_result": "Cleanup result"}
            with allure.step(f"{index:02d}. [{phase}] {titles.get(kind, kind)}"):
                attach_json("Event details", event)
    return len(events)
