"""Real-token lifetime checks; the target's absolute TTL must be explicitly supplied."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import monotonic, sleep

import allure
import pytest

from booker_qa.client import BookerClient
from reporting import assert_booking_matches, attach_json, compare, response_body

pytestmark = [pytest.mark.live, pytest.mark.requires_token_ttl]


def exercise_token_expiry(api, booking, lifetime, workers, *, fresh_client, clock=monotonic, sleeper=sleep):
    ttl, grace = lifetime
    path = f"/booking/{booking.booking_id}"
    baseline = {**booking.payload, "totalprice": 321}
    rejected_payload = {**booking.payload, "totalprice": 654}
    recovered_payload = {**booking.payload, "totalprice": 987}

    with allure.step("Acquire a real token and prove it works before its configured expiry"):
        login_started = clock()
        original_token = api.auth.token()
        login_finished = clock()
        before = api.request("PUT", path, json=baseline, headers={"Cookie": "token=" + original_token})
        baseline_finished = clock()
        compare("Token validity before expiry", 200, before.status_code)
        assert before.status_code == 200
        assert_booking_matches("Pre-expiry update", baseline, response_body(before))
        assert baseline_finished - login_started < ttl, "TTL too short to establish a valid pre-expiry control"
        persisted = api.request("GET", path)
        assert persisted.status_code == 200
        assert_booking_matches("Persisted pre-expiry state", baseline, response_body(persisted))

    with allure.step("Age the unchanged token beyond its configured lifetime"):
        # Completion time is a conservative lower bound on token age, avoiding early probes.
        deadline = login_finished + ttl + grace
        while (remaining := deadline - clock()) > 0:
            sleeper(min(remaining, 30.0))
        minimum_age = clock() - login_finished
        attach_json("Token lifetime observation", {
            "configured_absolute_ttl_seconds": ttl, "grace_seconds": grace,
            "minimum_token_age_seconds": minimum_age,
            "pre_expiry_control_elapsed_seconds": baseline_finished - login_started,
            "original_token_unchanged": True, "automatic_refresh_on_expiry_probe": False,
        })
        assert minimum_age >= ttl + grace

    with allure.step("Expired token must be rejected and leave the booking unchanged"):
        expired = api.request("PUT", path, json=rejected_payload, headers={"Cookie": "token=" + original_token})
        after = api.request("GET", path)
        attach_json("Expired-token rejection", {
            "expected_statuses": [401, 403], "actual_status": expired.status_code,
            "persisted_status": after.status_code, "expected_state": baseline, "actual_state": response_body(after),
        })
        # Fresh credentials must still work; an outage must not look like successful expiry enforcement.
        control = fresh_client()
        try:
            healthy = control.request("PUT", path, json=baseline, authenticated=True)
            assert healthy.status_code == 200, "Fresh-token positive control failed"
            assert_booking_matches("Fresh-token positive control", baseline, response_body(healthy))
        finally:
            control.close()
        assert expired.status_code in {401, 403}, (
            f"Expected 401/403 after configured TTL {ttl}s plus {grace}s grace, got HTTP {expired.status_code}"
        )
        assert after.status_code == 200
        assert not compare("Expired token cannot change booking", baseline, response_body(after))

    if not workers:
        return

    with allure.step(f"Recover from the naturally expired cached token with {workers} caller(s)"):
        cursor = len(api.observer.snapshot())
        barrier = Barrier(workers, timeout=30)

        def update(_):
            barrier.wait()
            return api.request("PUT", path, json=recovered_payload, authenticated=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            responses = list(pool.map(update, range(workers), timeout=60))
        events = api.observer.snapshot()[cursor:]
        auth = [e for e in events if e["kind"] == "http" and e["method"] == "POST" and e["path"] == "/auth"]
        protected = [e for e in events if e["kind"] == "http" and e["method"] == "PUT" and e["path"] == path]
        summary = {"callers": workers, "logical_auth_requests": len({e["request_id"] for e in auth}),
                   "successful_issuances": sum(e["status"] == 200 for e in auth),
                   "rejected_attempts": sum(e["status"] in {401, 403} for e in protected),
                   "successful_updates": sum(e["status"] == 200 for e in protected)}
        attach_json("Expired-token recovery summary", summary)
        assert summary["logical_auth_requests"] == summary["successful_issuances"] == 1
        assert summary["rejected_attempts"] >= 1
        assert summary["successful_updates"] == workers
        for response in responses:
            assert response.status_code == 200
            assert_booking_matches("Recovered update response", recovered_payload, response_body(response))
        final = api.request("GET", path)
        assert final.status_code == 200
        assert_booking_matches("State after expiry recovery", recovered_payload, response_body(final))


# An unchanged issued token must expire, preserve state on rejection, and refresh once across callers.
@pytest.mark.parametrize("workers", [0, 1, 4], ids=["reject-expired", "refresh-sequential", "refresh-concurrent"])
def test_real_token_expiry_and_reauthentication(api, settings, booking, token_lifetime, workers):
    exercise_token_expiry(api, booking, token_lifetime, workers,
                          fresh_client=lambda: BookerClient(settings, observer=api.observer))
