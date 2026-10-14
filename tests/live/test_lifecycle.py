from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from threading import Barrier, get_ident
from time import perf_counter_ns

import allure
import pytest

from booker_qa.schemas.booking import validate_contract, validate_invariants
from booker_qa.evidence import json_diff
from reporting import assert_booking_matches, attach_json, compare, response_body

pytestmark = pytest.mark.live


def persisted(api, handle):
    # A post-operation 404 is a real failed assertion; never recreate here.
    response = api.request("GET", f"/booking/{handle.booking_id}")
    compare("Persisted GET status", 200, response.status_code)
    assert response.status_code == 200
    body = response.json()
    validate_contract(body)
    return body


def test_create_contract(api, booking):
    body = persisted(api, booking)
    assert_booking_matches("Created booking contract and invariants: expected vs actual", booking.payload, body)
    validate_invariants(body)


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
            assert response.status_code == 200
            assert_booking_matches(f"PUT {iteration + 1}: response payload", payload, response_body(response))
            snapshot = persisted(api, booking)
            assert_booking_matches(f"PUT {iteration + 1}: persisted state", payload, snapshot)
            snapshots.append(snapshot)
    assert not compare("Idempotency summary: three persisted snapshots", [payload] * 3, snapshots)


def test_patch_preserves_every_untouched_field(api, booking):
    with allure.step("Capture full state before the partial update"):
        before = persisted(api, booking)
    response = api.request("PATCH", f"/booking/{booking.booking_id}", json={"totalprice": 777}, authenticated=True)
    expected = {**before, "totalprice": 777}
    compare("PATCH status", 200, response.status_code)
    assert response.status_code == 200
    assert_booking_matches("PATCH response: expected vs actual", expected, response_body(response))
    with allure.step("Verify every unreferenced field is unchanged"):
        after = persisted(api, booking)
        differences = json_diff(before, after)
        attach_json("PATCH preservation summary", {
            "patch_payload": {"totalprice": 777}, "before": before, "after": after,
            "changed_fields": differences,
            "untouched_fields_match": not json_diff({k:v for k,v in before.items() if k != "totalprice"},
                                                    {k:v for k,v in after.items() if k != "totalprice"}),
        })
        assert_booking_matches("PATCH persisted state: expected vs actual", expected, after)


# Updating only check-in must preserve checkout and every other unreferenced field.
def test_nested_patch_preserves_checkout(api, booking):
    before = persisted(api, booking)
    assert_booking_matches("Nested PATCH baseline", booking.payload, before)
    checkin = (date.fromisoformat(before["bookingdates"]["checkin"]) + timedelta(days=1)).isoformat()
    expected = deepcopy(before)
    expected["bookingdates"]["checkin"] = checkin
    response = api.request("PATCH", f"/booking/{booking.booking_id}",
                           json={"bookingdates": {"checkin": checkin}}, authenticated=True)
    # Read independently before asserting so both response and persisted corruption are reported.
    after = api.request("GET", f"/booking/{booking.booking_id}")
    actual = {"patch_status": response.status_code, "response": response_body(response),
              "get_status": after.status_code, "persisted": response_body(after)}
    differences = compare("Nested PATCH response and persisted state",
                          {"patch_status": 200, "response": expected, "get_status": 200, "persisted": expected}, actual)
    assert not differences, f"Nested PATCH must preserve untouched booking fields: {differences}"
    validate_contract(actual["response"])
    validate_contract(actual["persisted"])


# Supported mutation routes must report a missing booking correctly and leave it absent.
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_missing_resource_mutation_reports_absence(api, booking, method):
    path = f"/booking/{booking.booking_id}"
    assert api.request("DELETE", path, authenticated=True).status_code == 201
    assert api.request("GET", path).status_code == 404
    kwargs = {} if method == "DELETE" else {"json": booking.payload if method == "PUT" else {"totalprice": 456}}
    response = api.request(method, path, authenticated=True, **kwargs)
    absent = api.request("GET", path)
    expected_statuses = [200, 204, 404, 410] if method == "DELETE" else [404, 410]
    attach_json("Missing-resource HTTP semantics", {
        "method": method, "expected_statuses": expected_statuses,
        "mutation_status": response.status_code, "confirming_get_status": absent.status_code,
        "claim_scope": "HTTP error semantics; repeated DELETE idempotency is tested separately",
    })
    assert absent.status_code == 404, "Mutation recreated the missing resource"
    assert response.status_code in expected_statuses, (
        f"{method} on a missing booking should return one of {expected_statuses}, got HTTP {response.status_code}"
    )


def test_invalid_token_is_refreshed(api, booking):
    # A live invalidation simulates expiry; no server TTL is claimed.
    api.auth._token = "deliberately-invalid"
    response = api.request("PUT", f"/booking/{booking.booking_id}", json=booking.payload, authenticated=True)
    compare("Reauthenticated update status", 200, response.status_code)
    assert response.status_code == 200
    final = persisted(api, booking)
    assert_booking_matches("Reauthenticated update response", booking.payload, response_body(response))
    assert_booking_matches("Reauthenticated update persisted state", booking.payload, final)


def purge_owned_prerequisite(api, independent_api, handle):
    response = independent_api.request("DELETE", f"/booking/{handle.booking_id}", authenticated=True)
    absent = api.request("GET", f"/booking/{handle.booking_id}")
    attach_json("Controlled external purge of an owned prerequisite", {
        "booking_id": handle.booking_id, "delete_status": response.status_code,
        "confirming_get_status": absent.status_code,
        "scope": "separate HTTP client, same sandbox account; only an ID created by this test is targeted",
    })
    # Another sandbox actor may have removed it first; absence is the required setup state.
    assert response.status_code in {200, 201, 204, 404, 405}
    assert absent.status_code == 404, "Controlled purge did not leave the prerequisite absent"


# An independent client's purge must trigger one prerequisite recreation and allow the scenario to continue.
def test_missing_prerequisite_is_recreated(api, registry, independent_api):
    handle, body = registry.create()
    assert_booking_matches("Original prerequisite", handle.payload, body)
    old_id = handle.booking_id
    purge_owned_prerequisite(api, independent_api, handle)
    recovered = registry.ensure(handle)
    assert_booking_matches("Recreated prerequisite payload", handle.payload, recovered)
    assert handle.booking_id != old_id
    assert registry.recoveries == [(old_id, handle.booking_id)]
    assert registry.ids == [old_id, handle.booking_id]
    expected = {**handle.payload, "totalprice": 654, "lastname": "RecoveredGuest"}
    updated = api.request("PUT", f"/booking/{handle.booking_id}", json=expected, authenticated=True)
    final = api.request("GET", f"/booking/{handle.booking_id}")
    attach_json("Scenario continues after external purge", {
        "original_id": old_id, "replacement_id": handle.booking_id,
        "recoveries": registry.recoveries, "update_status": updated.status_code,
        "get_status": final.status_code,
        "scope": "separate clients using the sandbox account; only this test's owned record is purged",
    })
    assert updated.status_code == final.status_code == 200
    assert_booking_matches("Recovered booking PUT response", expected, response_body(updated))
    assert_booking_matches("Recovered booking persisted update", expected, response_body(final))
    # Teardown accepts the old ID's DELETE 404, or sandbox 405 only after a confirming GET 404.


# Cleanup must accept an externally deleted record and still remove every remaining owned booking.
def test_sandbox_cleanup_handles_external_purge(api, registry, independent_api):
    handles = []
    for _ in range(2):
        handle, body = registry.create()
        handles.append(handle)
        assert_booking_matches("Cleanup prerequisite", handle.payload, body)
    purged = handles[0]
    purge_owned_prerequisite(api, independent_api, purged)
    cursor = len(api.observer.snapshot())
    registry.cleanup()
    events = api.observer.snapshot()[cursor:]
    cleanups = [event for event in events if event["kind"] == "cleanup_result"]
    attach_json("Cleanup after external purge", {
        "purged_id": purged.booking_id, "owned_ids": registry.ids, "cleanup_results": cleanups,
        "scope": "separate clients, same sandbox account; cleanup must never recreate missing records",
    })
    assert [event["booking_id"] for event in cleanups] == [handle.booking_id for handle in handles]
    assert cleanups[0]["outcome"] in {"already absent", "absence confirmed"}
    assert all(event["outcome"] in {"deleted", "already absent", "absence confirmed"} for event in cleanups)
    assert registry.recoveries == []
    assert not any(event["kind"] == "http" and event["method"] == "POST" and event["path"] == "/booking"
                   for event in events), "Cleanup must not create replacement bookings"
    for handle in handles:
        assert api.request("GET", f"/booking/{handle.booking_id}").status_code == 404


def conflicting_payloads(booking):
    return [
        {**booking.payload, "firstname": "WinnerA", "lastname": "Alpha", "totalprice": 100, "depositpaid": False,
         "bookingdates": {"checkin": "2027-03-01", "checkout": "2027-03-04"}, "additionalneeds": "Tea"},
        {**booking.payload, "firstname": "WinnerB", "lastname": "Beta", "totalprice": 900, "depositpaid": True,
         "bookingdates": {"checkin": "2027-04-10", "checkout": "2027-04-15"}, "additionalneeds": "Coffee"},
    ]


def reconcile_writes(api, booking, candidates, outcomes, record_property, *, policy="last-write-wins"):
    # Collect every observation before asserting; a later read must not hide an earlier corrupt state.
    snapshots = []
    for _ in range(3):
        response = api.request("GET", f"/booking/{booking.booking_id}")
        snapshots.append({"status": response.status_code, "body": response_body(response)})
    statuses = [outcome.get("status") for outcome in outcomes]
    observed = "unexpected-statuses"
    if statuses == [200, 200]:
        observed = "both-writes-accepted"
    elif statuses.count(200) == 1 and any(status in {409, 412} for status in statuses):
        observed = "one-conflict-rejected"
    differences = [[json_diff(candidate, snapshot["body"]) for candidate in candidates] for snapshot in snapshots]
    matches = [[index for index, diff in enumerate(read_diffs) if not diff] for read_diffs in differences]
    attach_json("Write policy and stable state reconciliation", {
        "expected_policy": policy, "observed_write_outcome": observed, "write_statuses": statuses,
        "candidates": candidates, "snapshots": snapshots, "matching_candidate_indexes": matches,
        "candidate_differences": differences,
        "state_scope": "API-visible state across three GETs; direct database state and later drift are unmeasured",
        "ordering_scope": "concurrent client start/response order does not identify server commit order",
        "locking_scope": "no version precondition is sent; 409/412 alone does not prove optimistic locking",
    })
    record_property("expected_resolution_policy", policy)
    record_property("observed_write_outcome", observed)
    record_property("reconciliation_reads", len(snapshots))
    assert statuses == [200, 200], (
        f"Expected {policy} with both writes accepted; got {statuses} ({observed}). "
        "Unexpected rejection must be investigated, not accepted as an alternative policy."
    )
    for index, snapshot in enumerate(snapshots):
        assert snapshot["status"] == 200, f"Reconciliation GET {index + 1} returned HTTP {snapshot['status']}"
    assert len(matches[0]) == 1, "Final state does not match one complete candidate; lost update or partial payload merge"
    winner = candidates[matches[0][0]]
    for index, snapshot in enumerate(snapshots):
        assert_booking_matches(f"Reconciled snapshot {index + 1}", winner, snapshot["body"])
    record_property("matching_candidate_index", matches[0][0])
    return snapshots[0]["body"]


# Conflicting writers must leave one complete candidate that remains stable across repeated reads.
@pytest.mark.parametrize("round_number", range(3))
def test_conflicting_updates_reconcile_to_one_complete_payload(api, booking, round_number, record_property):
    candidates = conflicting_payloads(booking)
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
    with allure.step("Reconcile both write outcomes and three final-state reads"):
        final = reconcile_writes(api, booking, candidates, outcomes, record_property)
    candidate_diffs = [json_diff(candidate, final) for candidate in candidates]
    skew_ms = abs(outcomes[0]["started_ns"] - outcomes[1]["started_ns"]) / 1_000_000
    attach_json("Concurrent update reconciliation", {
        "candidates": candidates, "responses": outcomes, "release_skew_ms": skew_ms,
        "final_state": final, "matching_candidate_indexes": [i for i,diff in enumerate(candidate_diffs) if not diff],
        "candidate_differences": candidate_diffs,
    })
    for index, (outcome, candidate) in enumerate(zip(outcomes, candidates)):
        # Separate sandbox response-contract check: each PUT returns its own update.
        assert_booking_matches(f"Writer {index}: response payload", candidate, outcome["body"])
    record_property("release_skew_ms", skew_ms)
    record_property("winner", final["firstname"])
    # Exact server arrival at the same millisecond cannot be guaranteed by client scheduling.


# With a known write order, the second completed PUT must be the stable winner in both directions.
@pytest.mark.parametrize("writer_order", [(0, 1), (1, 0)], ids=["A_then_B", "B_then_A"])
def test_ordered_conflicting_put_uses_last_completed_write(api, booking, writer_order, record_property):
    candidates = conflicting_payloads(booking)
    outcomes = []
    attach_json("Ordered overwrite control", {
        "writer_order": writer_order, "expected_winner_index": writer_order[-1],
        "scope": "sequential policy control; the first response and confirming GET precede the second write",
    })
    for position, writer in enumerate(writer_order):
        response = api.request("PUT", f"/booking/{booking.booking_id}",
                               json=candidates[writer], authenticated=True)
        outcome = {"writer": writer, "status": response.status_code, "body": response_body(response)}
        outcomes.append(outcome)
        if position == 0:
            assert response.status_code == 200, f"First ordered PUT returned HTTP {response.status_code}"
            assert_booking_matches("First ordered PUT response", candidates[writer], outcome["body"])
            retrieved = api.request("GET", f"/booking/{booking.booking_id}")
            assert retrieved.status_code == 200
            assert_booking_matches("First write persisted before second starts", candidates[writer], response_body(retrieved))
    reconcile_writes(api, booking, [candidates[writer_order[-1]]], outcomes, record_property)
    for outcome in outcomes:
        assert_booking_matches(f"Ordered writer {outcome['writer']}: response",
                               candidates[outcome["writer"]], outcome["body"])
    record_property("writer_order", str(writer_order))
    record_property("winner", candidates[writer_order[-1]]["firstname"])


def parallel_patches(api, booking, patches, record_property):
    # Finish authentication before releasing writers; attach evidence only on the test thread.
    api.auth.token()
    barrier = Barrier(2, timeout=30)
    outcomes = [{"writer": index, "patch": patch} for index, patch in enumerate(patches)]

    def update(outcome):
        outcome["thread_id"] = get_ident()
        try:
            barrier.wait()
            outcome["started_ns"] = perf_counter_ns()
            response = api.request("PATCH", f"/booking/{booking.booking_id}",
                                   json=outcome["patch"], authenticated=True)
            outcome.update(status=response.status_code, body=response_body(response))
        except Exception as exc:
            outcome["error"] = type(exc).__name__
            raise
        finally:
            outcome["finished_ns"] = perf_counter_ns()

    failures = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(update, outcome) for outcome in outcomes]
            for future in futures:
                try:
                    future.result(timeout=60)
                except Exception as exc:
                    failures.append(exc)
    finally:
        skew_ms = (abs(outcomes[0]["started_ns"] - outcomes[1]["started_ns"]) / 1_000_000
                   if all("started_ns" in outcome for outcome in outcomes) else None)
        attach_json("Concurrent PATCH writer outcomes", {
            "booking_id": booking.booking_id, "outcomes": outcomes, "release_skew_ms": skew_ms,
            "timing_scope": "client release only; server arrival and execution overlap are unmeasured",
        })
        if skew_ms is not None:
            record_property("release_skew_ms", skew_ms)
    if failures:
        raise failures[0]
    assert len({outcome["thread_id"] for outcome in outcomes}) == 2
    return outcomes


# Two conflicting price PATCHes must leave one submitted price and preserve all other fields.
def test_conflicting_patch_preserves_one_price_and_untouched_fields(api, booking, record_property):
    before = persisted(api, booking)
    assert_booking_matches("Conflicting PATCH baseline", booking.payload, before)
    patches = [{"totalprice": 250}, {"totalprice": 850}]
    candidates = [{**before, **patch} for patch in patches]
    outcomes = parallel_patches(api, booking, patches, record_property)
    final = reconcile_writes(api, booking, candidates, outcomes, record_property)
    candidate_diffs = [json_diff(candidate, final) for candidate in candidates]
    attach_json("Conflicting PATCH reconciliation", {
        "before": before, "candidates": candidates, "final_state": final,
        "candidate_differences": candidate_diffs,
        "matching_candidate_indexes": [index for index, diff in enumerate(candidate_diffs) if not diff],
    })
    for index, (outcome, candidate) in enumerate(zip(outcomes, candidates)):
        # As with PUT, this separately checks the sandbox's own-update response contract.
        assert_booking_matches(f"PATCH writer {index}: response", candidate, outcome["body"])
    record_property("winner", final["totalprice"])


# Concurrent PATCHes to separate fields must both survive, without changing any other fields.
def test_concurrent_patch_preserves_both_independent_changes(api, booking, record_property):
    before = persisted(api, booking)
    assert_booking_matches("Independent PATCH baseline", booking.payload, before)
    patches = [{"totalprice": 675}, {"lastname": "ConcurrentGuest"}]
    expected = {**before, **patches[0], **patches[1]}
    outcomes = parallel_patches(api, booking, patches, record_property)
    final = reconcile_writes(api, booking, [expected], outcomes, record_property, policy="preserve-independent-patches")
    differences = compare("Independent PATCH final state", expected, final)
    attach_json("Independent PATCH reconciliation", {
        "before": before, "patches": patches, "expected": expected,
        "final_state": final,
        "differences": differences,
    })
    for index, (outcome, patch) in enumerate(zip(outcomes, patches)):
        # A response can precede the other write or already include it; its own change must be present.
        permitted = [{**before, **patch}, expected]
        response_diffs = [json_diff(candidate, outcome["body"]) for candidate in permitted]
        attach_json(f"PATCH writer {index}: allowed response states", {
            "permitted": permitted, "actual": outcome["body"], "differences": response_diffs,
        })
        assert any(not diff for diff in response_diffs), f"PATCH writer {index} lost a change or corrupted the response"
        validate_invariants(outcome["body"])



# Parallel setup threads must share one valid token from the live auth manager.
def test_parallel_setup_acquires_one_live_token(api):
    barrier = Barrier(4, timeout=30)
    def setup(_):
        barrier.wait()
        return api.auth.token()
    with ThreadPoolExecutor(max_workers=4) as pool:
        tokens = list(pool.map(setup, range(4), timeout=60))
    # Assert summary values so pytest's failure introspection cannot print tokens.
    valid_tokens = all(isinstance(token, str) and bool(token) for token in tokens)
    unique_token_count = len(set(tokens))
    auth_attempts = [event for event in api.observer.snapshot()
                     if event["kind"] == "http" and event["method"] == "POST" and event["path"] == "/auth"]
    # Pre-send connection retries retain one request_id; count successful issuance separately.
    auth_requests = len({event["request_id"] for event in auth_attempts})
    successful_issuances = sum(event["status"] == 200 for event in auth_attempts)
    attach_json("Parallel token acquisition summary", {
        "callers": 4, "valid_tokens": valid_tokens, "unique_token_count": unique_token_count,
        "logical_auth_requests": auth_requests, "http_attempts": len(auth_attempts),
        "successful_issuances": successful_issuances,
    })
    assert valid_tokens
    assert unique_token_count == 1
    assert auth_requests == successful_issuances == 1
