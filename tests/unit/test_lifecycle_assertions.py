"""Run the live assertions against controlled contract regressions, without network access."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import httpx
from jsonschema import ValidationError
import pytest

from booker_qa.bookings import BookingHandle, BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload


@pytest.fixture(scope="module")
def lifecycle():
    path = Path(__file__).parents[1] / "live/test_lifecycle.py"
    spec = importlib.util.spec_from_file_location("lifecycle_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# A correct nested merge passes; lost fields, other corruption, and request failures must fail.
@pytest.mark.parametrize("behavior", ["fixed", "lost_checkout", "other_corruption", "missing", "server_error", "timeout"])
def test_nested_patch_detects_corruption(lifecycle, behavior):
    payload = booking_payload()
    state = deepcopy(payload)
    patched = False

    def respond(request):
        nonlocal patched
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        if request.method == "PATCH":
            patched = True
            if behavior == "timeout":
                raise httpx.ReadTimeout("simulated response loss", request=request)
            if behavior == "server_error":
                return httpx.Response(500)
            state["bookingdates"].update(json.loads(request.content)["bookingdates"])
            if behavior in {"lost_checkout", "other_corruption"}:
                state["bookingdates"]["checkout"] = "0NaN-aN-aN"
            if behavior == "other_corruption":
                state["firstname"] = "Unexpected mutation"
        if request.method == "GET" and patched and behavior == "missing":
            return httpx.Response(404)
        return httpx.Response(200, json=state)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        if behavior == "fixed":
            lifecycle.test_nested_patch_preserves_checkout(api, BookingHandle(1, payload))
        else:
            error = httpx.ReadTimeout if behavior == "timeout" else AssertionError
            with pytest.raises(error):
                lifecycle.test_nested_patch_preserves_checkout(api, BookingHandle(1, payload))
    finally:
        api.close()


# The actual PUT/PATCH scenarios must reject type drift in either responses or stored state.
@pytest.mark.parametrize("scenario", ["test_put_three_times_is_idempotent", "test_patch_preserves_every_untouched_field"],
                         ids=["put", "patch"])
@pytest.mark.parametrize("failure_point", ["response", "persisted"])
@pytest.mark.parametrize("field", ["depositpaid", "totalprice"])
def test_live_update_checks_reject_type_drift(lifecycle, scenario, failure_point, field):
    payload = booking_payload()
    state = deepcopy(payload)
    writes = []

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        if request.method in {"PUT", "PATCH"}:
            state.update(json.loads(request.content))
            writes.append(request.method)
        body = deepcopy(state)
        if writes and ((request.method == "GET") == (failure_point == "persisted")):
            body[field] = 1 if field == "depositpaid" else float(body[field])
        return httpx.Response(200, json=body)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        error = ValidationError if field == "depositpaid" else AssertionError
        with pytest.raises(error):
            getattr(lifecycle, scenario)(api, BookingHandle(1, payload))
        assert len(writes) == 1
    finally:
        api.close()


# A malformed create response must fail even if a subsequent GET would return valid data.
@pytest.mark.parametrize("defect", ["booking_shape", "missing_booking", "extra_envelope_field", "status"])
def test_create_contract_failure_keeps_id_available_for_cleanup(defect):
    payload = booking_payload()
    body = {"bookingid": 1, "booking": payload}
    if defect == "booking_shape":
        body["booking"] = {"broken": "response"}
    elif defect == "missing_booking":
        del body["booking"]
    elif defect == "extra_envelope_field":
        body["unexpected"] = True
    requests = []

    def respond(request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        if request.method == "POST":
            return httpx.Response(201 if defect == "status" else 200, json=body)
        return httpx.Response(201 if request.method == "DELETE" else 200, json=payload)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    try:
        error = AssertionError if defect == "status" else ValidationError
        with pytest.raises(error):
            registry.create(payload)
        assert registry.ids == [1]
        registry.cleanup()
        assert ("DELETE", "/booking/1") in requests
        assert not any(method == "GET" for method, _ in requests)
    finally:
        api.close()


# Invalid identifiers must never become cleanup targets.
@pytest.mark.parametrize("booking_id", [True, 0, -1, "1", None])
def test_create_rejects_invalid_ids_without_registering_them(booking_id):
    payload = booking_payload()
    api = BookerClient(Settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"bookingid": booking_id, "booking": payload})))
    registry = BookingRegistry(api)
    try:
        with pytest.raises(ValueError, match="Invalid booking ID"):
            registry.create(payload)
        assert registry.ids == []
    finally:
        api.close()
