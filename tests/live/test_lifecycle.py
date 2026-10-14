"""Live booking contracts, state reconciliation, authentication recovery, and owned-record hygiene."""

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


# A created booking must round-trip with its complete contract and valid business values.
def test_create_contract(api, booking):
    """Use the booking fixture's validated POST result and independently GET the owned
    resource.

    Type: Live creation contract.

    Expected: Stored values exactly match the original payload, strict schema types hold,
    price is nonnegative, and checkout follows check-in.

    Cases: One generated valid booking.
    """
    body = persisted(api, booking)
    assert_booking_matches("Created booking contract and invariants: expected vs actual", booking.payload, body)
    validate_invariants(body)


# Three identical PUTs must produce three identical valid persisted snapshots.
def test_put_three_times_is_idempotent(api, booking):
    """Set lastname and price in a complete booking payload, submit it three times, and read
    after each update.

    Type: Live idempotency.

    Expected: Every write returns 200 with the expected body; all three GET snapshots equal
    the same full payload.

    Cases: Exactly 3 consecutive PUTs.

    Scope: Response equality is checked as the sandbox contract. Hidden side effects,
    operation counts, and resource versions are unmeasured.
    """
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


# A price-only PATCH must leave all unreferenced booking fields unchanged.
def test_patch_preserves_every_untouched_field(api, booking):
    """Capture the complete booking, PATCH totalprice to 777, and independently read the stored
    result.

    Type: Live partial-update integrity.

    Expected: HTTP 200 response and GET equal the baseline with only totalprice replaced;
    names, flags, needs, and both nested dates are preserved.

    Cases: Only totalprice changes.
    """
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


# A check-in-only nested PATCH must preserve checkout and all unrelated fields.
def test_nested_patch_preserves_checkout(api, booking):
    """Advance check-in by one day within the generated stay and capture both PATCH response
    and independent GET before asserting.

    Type: Live nested-update regression.

    Expected: Both statuses are 200 and complete payloads equal the intended nested merge,
    with the original checkout retained.

    Cases: Only bookingdates.checkin changes.

    Scope: Corruption is a normal failure; post-operation reads do not recreate a missing or
    damaged booking.
    """
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


# Supported mutation routes must report missing resources and keep them absent.
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_missing_resource_mutation_reports_absence(api, booking, method):
    """Delete an owned booking, confirm GET 404, then call its mutation route and check absence
    again.

    Type: Live HTTP semantics negative.

    Expected: PUT/PATCH return 404/410; repeated DELETE returns 200/204/404/410. The
    resource remains absent with GET 404.

    Cases: PUT, PATCH, and DELETE after confirmed deletion.

    Scope: HTTP 405 fails this semantics check even though cleanup and DELETE-idempotency
    scenarios can tolerate it when absence is confirmed.
    """
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


# A rejected cached token must allow the protected update to recover successfully.
def test_invalid_token_is_refreshed(api, booking):
    """Replace the client's cached token with an invalid value, then perform an authenticated
    PUT on an owned booking.

    Type: Live authentication recovery.

    Expected: The client recovers to HTTP 200 and response plus final GET match the intended
    full payload.

    Cases: Deliberately invalid cached token.

    Scope: Invalid-token rejection simulates expiry. Actual elapsed-time expiry and exact
    shared-refresh counts have separate tests.
    """
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


# A purged prerequisite must be recreated once so the protected scenario can continue.
def test_missing_prerequisite_is_recreated(api, registry, independent_api):
    """Delete an owned prerequisite through a separate client, call registry.ensure, then
    update and read the replacement.

    Type: Live sandbox recovery.

    Expected: The handle changes to a tracked replacement ID, one recovery is recorded, and
    protected PUT/GET match the updated full payload.

    Cases: Independent-client deletion followed by one recreation.

    Scope: Both clients use the sandbox account and target only owned IDs. Recovery applies
    to prerequisites; post-operation failures remain visible.
    """
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


# Cleanup must handle an already-absent booking and continue through every owned ID.
def test_sandbox_cleanup_handles_external_purge(api, registry, independent_api):
    """Simulate external deletion, clean up both tracked IDs, and inspect cleanup events and
    confirming reads.

    Type: Live sandbox hygiene.

    Expected: Each ID receives a successful deletion/absence outcome, both final GETs return
    404, and cleanup creates no replacement booking.

    Cases: 2 owned records; first removed through a separate client.

    Scope: DELETE 405 requires GET 404. Repeated fixture cleanup is allowed; unrelated
    resource IDs and global reset routes are never used.
    """
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


# Conflicting full updates must settle on one complete payload that stays stable.
@pytest.mark.parametrize("round_number", range(3))
def test_conflicting_updates_reconcile_to_one_complete_payload(api, booking, round_number, record_property):
    """Release distinct complete payloads against one owned ID and reconcile both write
    outcomes with three subsequent GETs.

    Type: Live concurrency integrity.

    Expected: Both writes return 200 and their own payload; all three reads equal one full
    candidate with strict types and invariants. Partial merges and drift fail.

    Cases: 3 rounds, each with 2 synchronized PUT writers.

    Scope: Either writer may win. Client timing cannot reveal commit order; direct database
    state and optimistic locking are unverified. Unexpected 409/412 fail the configured
    overwrite policy.
    """
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


# With a known write order, the second complete PUT must be the stable winner.
@pytest.mark.parametrize("writer_order", [(0, 1), (1, 0)], ids=["A_then_B", "B_then_A"])
def test_ordered_conflicting_put_uses_last_completed_write(api, booking, writer_order, record_property):
    """Complete the first PUT and confirming GET before starting the second; then reconcile
    three final reads.

    Type: Live overwrite-policy control.

    Expected: Both responses match their submitted payloads and every final GET equals the
    second writer's complete booking.

    Cases: A_then_B and B_then_A.

    Scope: This sequential control verifies overwrite behavior when order is known. It does
    not establish concurrent server commit order.
    """
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


# Conflicting price PATCHes must preserve one submitted value and every untouched field.
def test_conflicting_patch_preserves_one_price_and_untouched_fields(api, booking, record_property):
    """Capture a baseline, authenticate before releasing two threads, and compare their
    outcomes and three final reads with both complete candidates.

    Type: Live concurrency integrity.

    Expected: Both PATCHes return 200 with their own update; one price wins and the
    identical complete booking appears in every reconciliation GET.

    Cases: 2 synchronized PATCH writers: prices 250 and 850.

    Scope: Client release skew is recorded, not constrained. Exact server overlap, hidden
    effects, and commit order are unmeasured.
    """
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


# Concurrent PATCHes to separate fields must preserve both changes without drift.
def test_concurrent_patch_preserves_both_independent_changes(api, booking, record_property):
    """PATCH different top-level fields on one booking, collect both responses, and read the
    final state three times.

    Type: Live lost-update detection.

    Expected: Both writes return 200. Each response includes its own change alone or both;
    all final reads contain both changes and preserve unrelated fields.

    Cases: 2 synchronized writers: totalprice and lastname.

    Scope: This checks commutative partial-update integrity. A response before the other
    write completes is valid; exact server overlap is not guaranteed.
    """
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



# Four simultaneous setup callers must share one successful live token issuance.
def test_parallel_setup_acquires_one_live_token(api):
    """Release token requests through a barrier and inspect sanitized authentication attempt
    evidence after all callers return.

    Type: Live authentication concurrency.

    Expected: All tokens are nonempty and identical, with one logical POST /auth request and
    one successful issuance.

    Cases: 4 threads sharing one AuthManager.

    Scope: Pre-send connection retries may add HTTP attempts while retaining one logical
    request ID. Token values are omitted from report summaries.
    """
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
