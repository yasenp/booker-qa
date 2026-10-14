"""Run the live assertions against controlled contract regressions, without network access."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Barrier, Event, Lock, get_ident

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
        error = AssertionError if failure_point == "response" else ValidationError
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


# The actual concurrent scenarios must allow either write order and detect lost data or failed writes.
@pytest.mark.parametrize("scenario", [
    "test_conflicting_patch_preserves_one_price_and_untouched_fields",
    "test_concurrent_patch_preserves_both_independent_changes",
], ids=["conflicting", "independent"])
@pytest.mark.parametrize("behavior", [
    "first_then_second", "second_then_first", "lost_update", "corrupt_response",
    "corrupt_persisted", "invalid_persisted_type", "server_error", "response_loss",
])
def test_parallel_patch_scenarios_detect_regressions(lifecycle, scenario, behavior):
    payload = booking_payload()
    state = deepcopy(payload)
    arrivals = Barrier(2, timeout=5)
    first_finished = Event()
    lock = Lock()
    writers = []
    properties = {}
    first_price = 250 if "conflicting" in scenario else 675
    leading_writer = 1 if behavior == "second_then_first" else 0

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        if request.method == "GET":
            with lock:
                body = deepcopy(state)
                if len(writers) == 2:
                    if behavior == "lost_update":
                        body["totalprice"] = payload["totalprice"]
                    elif behavior == "corrupt_persisted":
                        body["bookingdates"]["checkout"] = "2031-12-31"
                    elif behavior == "invalid_persisted_type":
                        body["totalprice"] = float(body["totalprice"])
            return httpx.Response(200, json=body)
        assert request.method == "PATCH" and request.url.path == "/booking/1"
        patch = json.loads(request.content)
        index = 0 if patch.get("totalprice") == first_price else 1
        with lock:
            writers.append(get_ident())
        # Both sends must enter the transport before either operation can complete.
        arrivals.wait()
        if index != leading_writer:
            assert first_finished.wait(timeout=5), "Leading writer did not finish"
        try:
            with lock:
                state.update(patch)
                body = deepcopy(state)
            if index == 1:
                if behavior == "response_loss":
                    raise httpx.ReadTimeout("controlled response loss", request=request)
                if behavior == "server_error":
                    return httpx.Response(500)
                if behavior == "corrupt_response":
                    body["firstname"] = "Corrupted guest"
            return httpx.Response(200, json=body)
        finally:
            if index == leading_writer:
                first_finished.set()

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        run = getattr(lifecycle, scenario)
        if behavior in {"first_then_second", "second_then_first"}:
            run(api, BookingHandle(1, payload), properties.__setitem__)
        else:
            error = httpx.ReadTimeout if behavior == "response_loss" else AssertionError
            with pytest.raises(error):
                run(api, BookingHandle(1, payload), properties.__setitem__)
        assert len(writers) == len(set(writers)) == 2
        assert properties["release_skew_ms"] >= 0
    finally:
        api.close()


# Either complete race winner may pass; mixed, unstable, missing, or rejected results must fail.
@pytest.mark.parametrize("behavior", [
    "winner_a", "winner_b", "mixed_fields", "partial_dates", "invalid_price_type",
    "unchanged", "drift", "missing", "conflict409", "precondition412", "server500",
])
def test_conflicting_put_reconciliation_rejects_invalid_outcomes(lifecycle, behavior):
    payload = booking_payload()
    writes = {}
    writer_threads = set()
    arrivals = Barrier(2, timeout=5)
    lock = Lock()
    reads = 0
    properties = {}

    def respond(request):
        nonlocal reads
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        assert request.url.path == "/booking/1"
        if request.method == "PUT":
            body = json.loads(request.content)
            with lock:
                writes[body["firstname"]] = body
                writer_threads.add(get_ident())
            arrivals.wait()
            status = {"conflict409": 409, "precondition412": 412, "server500": 500}.get(behavior, 200)
            return httpx.Response(status if body["firstname"] == "WinnerB" else 200, json=body)
        assert request.method == "GET"
        reads += 1
        body = deepcopy(writes["WinnerB" if behavior == "winner_b" else "WinnerA"])
        if behavior == "mixed_fields":
            body["lastname"] = writes["WinnerB"]["lastname"]
        elif behavior == "partial_dates":
            del body["bookingdates"]["checkout"]
        elif behavior == "invalid_price_type":
            body["totalprice"] = float(body["totalprice"])
        elif behavior == "unchanged":
            body = deepcopy(payload)
        elif behavior == "drift" and reads == 2:
            body = deepcopy(writes["WinnerB"])
        return httpx.Response(404 if behavior == "missing" and reads == 2 else 200, json=body)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        if behavior in {"winner_a", "winner_b"}:
            lifecycle.test_conflicting_updates_reconcile_to_one_complete_payload(
                api, BookingHandle(1, payload), 0, properties.__setitem__)
        else:
            message = "Final state does not match"
            if behavior == "drift":
                message = "Reconciled snapshot 2"
            elif behavior == "missing":
                message = "Reconciliation GET 2"
            elif behavior in {"conflict409", "precondition412", "server500"}:
                message = "Expected last-write-wins"
            with pytest.raises(AssertionError, match=message):
                lifecycle.test_conflicting_updates_reconcile_to_one_complete_payload(
                    api, BookingHandle(1, payload), 0, properties.__setitem__)
        assert len(writes) == len(writer_threads) == 2
        assert reads == properties["reconciliation_reads"] == 3
        expected_outcome = ("one-conflict-rejected" if behavior in {"conflict409", "precondition412"}
                            else "unexpected-statuses" if behavior == "server500" else "both-writes-accepted")
        assert properties["observed_write_outcome"] == expected_outcome
    finally:
        api.close()


# Ordered controls must reject an ignored second write, mixed payloads, and later state drift.
@pytest.mark.parametrize("writer_order", [(0, 1), (1, 0)], ids=["A_then_B", "B_then_A"])
@pytest.mark.parametrize("behavior", ["correct", "ignored_second", "mixed_final", "drift"])
def test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes(lifecycle, writer_order, behavior):
    payload = booking_payload()
    state = deepcopy(payload)
    writes = []
    final_reads = 0
    properties = {}

    def respond(request):
        nonlocal state, final_reads
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "controlled-token"})
        assert request.url.path == "/booking/1"
        if request.method == "PUT":
            body = json.loads(request.content)
            writes.append(body)
            if len(writes) == 1 or behavior != "ignored_second":
                state = deepcopy(body)
            return httpx.Response(200, json=body)
        assert request.method == "GET"
        body = deepcopy(state)
        if len(writes) == 2:
            final_reads += 1
            if behavior == "mixed_final":
                body["firstname"] = writes[0]["firstname"]
            elif behavior == "drift" and final_reads == 2:
                body = deepcopy(writes[0])
        return httpx.Response(200, json=body)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        if behavior == "correct":
            lifecycle.test_ordered_conflicting_put_uses_last_completed_write(
                api, BookingHandle(1, payload), writer_order, properties.__setitem__)
            assert properties["winner"] == writes[-1]["firstname"]
        else:
            message = "Reconciled snapshot 2" if behavior == "drift" else "Final state does not match"
            with pytest.raises(AssertionError, match=message):
                lifecycle.test_ordered_conflicting_put_uses_last_completed_write(
                    api, BookingHandle(1, payload), writer_order, properties.__setitem__)
        assert len(writes) == 2
        assert final_reads == properties["reconciliation_reads"] == 3
    finally:
        api.close()
