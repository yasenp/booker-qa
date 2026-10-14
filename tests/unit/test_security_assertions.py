"""Security assertions must detect unauthorized changes and clean up test-owned ID collisions."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from booker_qa.bookings import BookingHandle, BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload


@pytest.fixture(scope="module")
def scenarios():
    modules = {}
    for name in ("auth_sessions", "validation"):
        spec = importlib.util.spec_from_file_location(name + "_security_checks",
                                                    Path(__file__).parents[1] / "live" / f"test_{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


# Rejection passes only when status and state agree; a 403 cannot hide a mutation or deletion.
@pytest.mark.parametrize("status,mutation", [(403, "none"), (200, "none"), (200, "update"),
                                            (403, "update"), (403, "delete")])
def test_unauthorized_mutation_checks_status_and_state(scenarios, status, mutation):
    payload = booking_payload()
    state = deepcopy(payload)

    def respond(request):
        if request.method == "GET":
            return httpx.Response(404) if mutation == "delete" else httpx.Response(200, json=state)
        if mutation == "update":
            state.update(json.loads(request.content))
        return httpx.Response(status)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        check = scenarios["auth_sessions"].assert_unauthorized_mutation_preserves_booking
        if status == 403 and mutation == "none":
            check(api, BookingHandle(1, payload), "PATCH", {})
        else:
            with pytest.raises(AssertionError, match="authorization or state preservation"):
                check(api, BookingHandle(1, payload), "PATCH", {})
    finally:
        api.close()


# A corrupted booking ID must fail the scenario and still allow both owned records to be deleted.
@pytest.mark.parametrize("patch_status", [405, 400], ids=["missing-original", "reject-but-mutates"])
def test_internal_id_collision_is_reported_and_cleaned(scenarios, patch_status):
    records = []
    deleted = []

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        if request.method == "POST":
            payload = json.loads(request.content)
            record = {"id": len(records) + 1, "payload": payload}
            records.append(record)
            return httpx.Response(200, json={"bookingid": record["id"], "booking": payload})
        booking_id = int(request.url.path.rsplit("/", 1)[1])
        record = next((record for record in records if record["id"] == booking_id), None)
        if request.method == "PATCH":
            record["id"] = json.loads(request.content)["bookingid"]
            return httpx.Response(patch_status)
        if request.method == "GET":
            return httpx.Response(200, json=record["payload"]) if record else httpx.Response(404)
        if request.method == "DELETE" and record:
            deleted.append(booking_id)
            records.remove(record)
            return httpx.Response(201)
        return httpx.Response(405)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    registry = BookingRegistry(api)
    try:
        with pytest.raises(AssertionError, match="Internal.field"):
            scenarios["validation"].test_patch_rejects_internal_fields(api, registry, "bookingid")
        assert registry.ids == [1, 2, 2]
    finally:
        try:
            registry.cleanup()
        finally:
            api.close()
    assert deleted == [2, 2]
    assert records == []
