from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter_ns

import allure
import pytest

from booker_qa.schemas.booking import validate_invariants
from booker_qa.evidence import json_diff
from reporting import attach_json, compare, response_body

pytestmark = pytest.mark.live


def persisted(api, handle):
    # A post-operation 404 is a real failed assertion; never recreate here.
    response = api.request("GET", f"/booking/{handle.booking_id}")
    compare("Persisted GET status", 200, response.status_code)
    assert response.status_code == 200
    return response.json()


def test_create_contract(api, booking):
    body = persisted(api, booking)
    compare("Created booking contract and invariants: expected vs actual", booking.payload, body)
    validate_invariants(body)
    assert body == booking.payload


def test_put_three_times_is_idempotent(api, booking):
    initial = persisted(api, booking)
    attach_json("Idempotency scope and initial state", {
        "initial_state": initial, "repetitions": 3,
        "claim_scope": "observable booking state; response equality is a separate API contract assertion",
        "hidden_side_effects": "unmeasured", "resource_versions": "unsupported",
    })
    payload = {**booking.payload, "lastname": "Updated", "totalprice": 456}
    snapshots = []
    for iteration in range(3):
        with allure.step(f"Apply identical PUT and read persisted state: iteration {iteration + 1}"):
            response = api.request("PUT", f"/booking/{booking.booking_id}", json=payload, authenticated=True)
            compare(f"PUT {iteration + 1}: status", 200, response.status_code)
            compare(f"PUT {iteration + 1}: response payload", payload, response_body(response))
            assert response.status_code == 200
            assert response.json() == payload
            snapshot = persisted(api, booking)
            compare(f"PUT {iteration + 1}: persisted state", payload, snapshot)
            snapshots.append(snapshot)
    compare("Idempotency summary: three persisted snapshots", [payload] * 3, snapshots)
    assert snapshots == [payload] * 3


def test_patch_preserves_every_untouched_field(api, booking):
    with allure.step("Capture full state before the partial update"):
        before = persisted(api, booking)
    response = api.request("PATCH", f"/booking/{booking.booking_id}", json={"totalprice": 777}, authenticated=True)
    expected = {**before, "totalprice": 777}
    compare("PATCH status", 200, response.status_code)
    compare("PATCH response: expected vs actual", expected, response_body(response))
    assert response.status_code == 200
    assert response.json() == expected
    with allure.step("Verify every unreferenced field is unchanged"):
        after = persisted(api, booking)
        differences = json_diff(before, after)
        attach_json("PATCH preservation summary", {
            "patch_payload": {"totalprice": 777}, "before": before, "after": after,
            "changed_fields": differences,
            "untouched_fields_match": not json_diff({k:v for k,v in before.items() if k != "totalprice"},
                                                    {k:v for k,v in after.items() if k != "totalprice"}),
        })
        compare("PATCH persisted state: expected vs actual", expected, after)
        assert after == expected


def test_invalid_token_is_refreshed(api, booking):
    # A live invalidation simulates expiry; no server TTL is claimed.
    api.auth._token = "deliberately-invalid"
    response = api.request("PUT", f"/booking/{booking.booking_id}", json=booking.payload, authenticated=True)
    compare("Reauthenticated update status", 200, response.status_code)
    assert response.status_code == 200
    final = persisted(api, booking)
    compare("Reauthenticated update persisted state", booking.payload, final)
    assert final == booking.payload


def test_missing_prerequisite_is_recreated(api, registry):
    handle, _ = registry.create()
    old_id = handle.booking_id
    deleted = api.request("DELETE", f"/booking/{old_id}", authenticated=True)
    compare("Simulated external deletion status", 201, deleted.status_code)
    assert deleted.status_code == 201
    recovered = registry.ensure(handle)
    compare("Recreated prerequisite payload", handle.payload, recovered)
    assert recovered == handle.payload
    assert handle.booking_id != old_id
    assert registry.recoveries == [(old_id, handle.booking_id)]
    # Teardown sees a 404 for the original ID and accepts it.


@pytest.mark.parametrize("round_number", range(3))
def test_conflicting_updates_reconcile_to_one_complete_payload(api, booking, round_number, record_property):
    candidates = [
        {**booking.payload, "firstname": "WinnerA", "lastname": "Alpha", "totalprice": 100, "depositpaid": False,
         "bookingdates": {"checkin": "2027-03-01", "checkout": "2027-03-04"}, "additionalneeds": "Tea"},
        {**booking.payload, "firstname": "WinnerB", "lastname": "Beta", "totalprice": 900, "depositpaid": True,
         "bookingdates": {"checkin": "2027-04-10", "checkout": "2027-04-15"}, "additionalneeds": "Coffee"},
    ]
    barrier = Barrier(2, timeout=30)
    def update(payload):
        # httpx Client is thread-safe; the auth manager is shared within this process.
        api.auth.token()
        barrier.wait()
        started = perf_counter_ns()
        response = api.request("PUT", f"/booking/{booking.booking_id}", json=payload, authenticated=True)
        return started, response
    outcomes = []
    failures = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(update, payload) for payload in candidates]
            # Capture both outcomes even if one worker fails, then fail visibly.
            for future in futures:
                try:
                    started, response = future.result(timeout=60)
                    outcomes.append({"started_ns": started, "status": response.status_code,
                                     "body": response_body(response)})
                except Exception as exc:
                    outcomes.append({"error": type(exc).__name__})
                    failures.append(exc)
    finally:
        attach_json("Concurrent writer outcomes", {"candidates": candidates, "outcomes": outcomes})
    if failures:
        raise failures[0]
    with allure.step("Read final state and reconcile against both complete candidates"):
        final = persisted(api, booking)
    candidate_diffs = [json_diff(candidate, final) for candidate in candidates]
    skew_ms = abs(outcomes[0]["started_ns"] - outcomes[1]["started_ns"]) / 1_000_000
    attach_json("Concurrent update reconciliation", {
        "candidates": candidates, "responses": outcomes, "release_skew_ms": skew_ms,
        "final_state": final, "matching_candidate_indexes": [i for i,diff in enumerate(candidate_diffs) if not diff],
        "candidate_differences": candidate_diffs,
    })
    for index, (outcome, candidate) in enumerate(zip(outcomes, candidates)):
        compare(f"Writer {index}: status", 200, outcome["status"])
        compare(f"Writer {index}: response payload", candidate, outcome["body"])
        assert outcome["status"] == 200
        assert outcome["body"] == candidate
    validate_invariants(final)
    assert final in candidates, "Final state was corrupted or merged across conflicting payloads"
    record_property("release_skew_ms", skew_ms)
    record_property("winner", final["firstname"])
    # Exact server arrival at the same millisecond cannot be guaranteed by client scheduling.



def test_parallel_setup_acquires_one_live_token(api):
    barrier = Barrier(4, timeout=30)
    def setup(_):
        barrier.wait()
        return api.auth.token()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(setup, range(4)))
    # Assert summary values so pytest's failure introspection cannot print tokens.
    valid_tokens = all(isinstance(token, str) and bool(token) for token in tokens)
    unique_token_count = len(set(tokens))
    assert valid_tokens
    assert unique_token_count == 1
