"""Observable state guarantees; no claims about hidden server-side effects."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter_ns

import allure
import pytest

from booker_qa.evidence import json_diff
from reporting import attach_json, compare, response_body

pytestmark = pytest.mark.live


def read_booking(api, booking):
    response = api.request("GET", f"/booking/{booking.booking_id}")
    compare("Persisted read status", 200, response.status_code)
    assert response.status_code == 200
    return response.json()


def repeat_update(api, booking, method, payload, repetitions):
    initial = read_booking(api, booking)
    expected = payload if method == "PUT" else {**initial, **payload}
    outcomes, snapshots = [], []
    try:
        for iteration in range(repetitions):
            with allure.step(f"Identical {method} {iteration + 1}/{repetitions}: apply and verify state"):
                response = api.request(method, f"/booking/{booking.booking_id}", json=payload, authenticated=True)
                outcomes.append({"status": response.status_code, "body": response_body(response)})
                compare(f"{method} {iteration + 1}: response contract", expected, response_body(response))
                assert response.status_code == 200
                assert response.json() == expected
                actual = read_booking(api, booking)
                snapshots.append(actual)
                differences = compare(f"{method} {iteration + 1}: persisted state", expected, actual)
                assert not differences
    finally:
        attach_json("Observable state idempotency summary", {
            "method": method, "initial_state": initial, "request_payload": payload,
            "requested_repetitions": repetitions, "completed_state_checks": len(snapshots),
            "response_outcomes": outcomes, "persisted_snapshots": snapshots,
            "expected_state": expected, "final_observed_state": snapshots[-1] if snapshots else None,
            "matching_snapshots": sum(not json_diff(expected, snapshot) for snapshot in snapshots),
            "snapshot_differences": [json_diff(expected, snapshot) for snapshot in snapshots],
            "claim_scope": "observable booking state only; hidden effects are unmeasured",
        })


@pytest.mark.parametrize("repetitions", [2, 5])
def test_sequential_identical_put_preserves_observable_state(api, booking, repetitions):
    # Keep the original three-PUT test unchanged for stable Allure history.
    repeat_update(api, booking, "PUT", {**booking.payload, "lastname": "Repeated", "totalprice": 456}, repetitions)


def test_repeated_set_value_patch_preserves_observable_state(api, booking):
    # This scope is a set-value PATCH, not increment/append PATCH operations.
    repeat_update(api, booking, "PATCH", {"totalprice": 777}, 3)


@pytest.mark.parametrize("workers", [2, 4])
def test_concurrent_identical_put_preserves_observable_state(api, booking, workers):
    initial = read_booking(api, booking)
    payload = {**booking.payload, "lastname": "ConcurrentIdentical", "totalprice": 888}
    api.auth.token()
    barrier = Barrier(workers, timeout=30)
    def update():
        barrier.wait()
        started = perf_counter_ns()
        response = api.request("PUT", f"/booking/{booking.booking_id}", json=payload, authenticated=True)
        return {"started_ns": started, "status": response.status_code, "body": response_body(response)}
    outcomes, failures = [], []
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(update) for _ in range(workers)]
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=60))
                except Exception as exc:
                    outcomes.append({"error": type(exc).__name__})
                    failures.append(exc)
    finally:
        attach_json("Identical concurrent writer outcomes", {
            "initial_state": initial, "request_payload": payload, "workers": workers, "outcomes": outcomes})
    if failures:
        raise failures[0]
    final = read_booking(api, booking)
    differences = compare("Concurrent identical PUT final state", payload, final)
    starts = [outcome["started_ns"] for outcome in outcomes]
    attach_json("Identical-request idempotency summary", {
        "workers": workers, "final_state": final, "matches_single_request_effect": not differences,
        "release_skew_ms": (max(starts) - min(starts)) / 1_000_000,
        "claim_scope": "observable state; operation counts and hidden effects are unmeasured",
    })
    for index, outcome in enumerate(outcomes):
        compare(f"Writer {index}: response contract", payload, outcome["body"])
        assert outcome["status"] == 200
        assert outcome["body"] == payload
    assert not differences


def test_repeated_delete_keeps_booking_absent(api, booking):
    initial = read_booking(api, booking)
    outcomes = []
    try:
        for iteration in range(3):
            with allure.step(f"DELETE {iteration + 1}/3 and confirm resource remains absent"):
                response = api.request("DELETE", f"/booking/{booking.booking_id}", authenticated=True)
                get = api.request("GET", f"/booking/{booking.booking_id}")
                outcomes.append({"delete_status": response.status_code, "confirming_get_status": get.status_code})
                compare(f"DELETE {iteration + 1}: absence", 404, get.status_code)
                if iteration == 0:
                    assert response.status_code == 201
                else:
                    # The observed sandbox returns 405 on repeated deletion;
                    # it is accepted here only together with a confirming GET 404.
                    assert response.status_code in {200, 201, 204, 404, 405}
                assert get.status_code == 404
    finally:
        attach_json("DELETE idempotency summary", {
            "initial_state": initial, "requested_repetitions": 3, "outcomes": outcomes,
            "absence_verified_count": sum(outcome["confirming_get_status"] == 404 for outcome in outcomes),
            "claim_scope": "resource remains absent; equal DELETE response codes are not required",
        })
