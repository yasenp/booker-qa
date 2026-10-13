from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import perf_counter_ns

import json

import allure
import pytest

from booker_qa.schemas.booking import validate_invariants

pytestmark = pytest.mark.live


def persisted(api, handle):
    # A post-operation 404 is a real failed assertion; never recreate here.
    response = api.request("GET", f"/booking/{handle.booking_id}")
    assert response.status_code == 200
    return response.json()


def test_create_contract(api, booking):
    body = persisted(api, booking)
    validate_invariants(body)
    assert body == booking.payload


def test_put_three_times_is_idempotent(api, booking):
    payload = {**booking.payload, "lastname": "Updated", "totalprice": 456}
    snapshots = []
    for iteration in range(3):
        with allure.step(f"Apply identical PUT and read persisted state: iteration {iteration + 1}"):
            response = api.request("PUT", f"/booking/{booking.booking_id}", json=payload, authenticated=True)
            assert response.status_code == 200
            assert response.json() == payload
            snapshots.append(persisted(api, booking))
    assert snapshots == [payload] * 3


def test_patch_preserves_every_untouched_field(api, booking):
    with allure.step("Capture full state before the partial update"):
        before = persisted(api, booking)
    response = api.request("PATCH", f"/booking/{booking.booking_id}", json={"totalprice": 777}, authenticated=True)
    assert response.status_code == 200
    expected = {**before, "totalprice": 777}
    assert response.json() == expected
    with allure.step("Verify every unreferenced field is unchanged"):
        assert persisted(api, booking) == expected


def test_invalid_token_is_refreshed(api, booking):
    # A live invalidation simulates expiry; no server TTL is claimed.
    api.auth._token = "deliberately-invalid"
    response = api.request("PUT", f"/booking/{booking.booking_id}", json=booking.payload, authenticated=True)
    assert response.status_code == 200
    assert persisted(api, booking) == booking.payload


def test_missing_prerequisite_is_recreated(api, registry):
    handle, _ = registry.create()
    old_id = handle.booking_id
    assert api.request("DELETE", f"/booking/{old_id}", authenticated=True).status_code == 201
    assert registry.ensure(handle) == handle.payload
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
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, payload) for payload in candidates]
        outcomes = [future.result(timeout=60) for future in futures]
    for (_, response), candidate in zip(outcomes, candidates):
        assert response.status_code == 200
        assert response.json() == candidate
    with allure.step("Read final state and reconcile against both complete candidates"):
        final = persisted(api, booking)
    allure.attach(json.dumps({
        "candidates": candidates,
        "responses": [{"status": response.status_code, "body": response.json()} for _, response in outcomes],
        "release_skew_ms": abs(outcomes[0][0] - outcomes[1][0]) / 1_000_000,
        "final_state": final,
    }, indent=2), "Concurrent update reconciliation", allure.attachment_type.JSON)
    validate_invariants(final)
    assert final in candidates, "Final state was corrupted or merged across conflicting payloads"
    record_property("release_skew_ms", abs(outcomes[0][0] - outcomes[1][0]) / 1_000_000)
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
