from uuid import uuid4

import allure
import pytest

from reporting import assert_booking_matches, attach_json, compare, response_body
from booker_qa.client import BookerClient


class TokenRevocationUnsupported(AssertionError):
    """Only confirmed acceptance of the previous token is an expected sandbox gap."""


# An unknown user must receive Bad credentials and no authentication token.
@pytest.mark.live
def test_auth_rejects_nonexistent_user(api):
    with allure.step("Attempt authentication with a unique nonexistent username"):
        response = api.request("POST", "/auth", json={
            "username": f"nonexistent-{uuid4().hex}",
            "password": "invalid-password",
        })
        body = response_body(response)
        attach_json("Unknown-user authentication result", {
            "expected_status": 200, "actual_status": response.status_code,
            "expected_reason": "Bad credentials",
            "actual_reason": body.get("reason") if isinstance(body, dict) else None,
            "token_present": isinstance(body, dict) and "token" in body,
        })
        compare("Unknown-user response contract", {"reason": "Bad credentials"}, body)
        assert response.status_code == 200
        assert body == {"reason": "Bad credentials"}
        assert "token" not in body


def probe_previous_token_after_new_login(api, settings, booking):
    path = f"/booking/{booking.booking_id}"
    first_payload = {**booking.payload, "totalprice": 321}
    second_payload = {**booking.payload, "totalprice": 654}
    old_token_payload = {**booking.payload, "totalprice": 987}
    with allure.step("Login on the first client and verify its token on a protected PUT"):
        first_token = api.auth.token()
        # Explicit raw cookie: authenticated=True would refresh a rejected token and mask revocation.
        first_response = api.request("PUT", path, json=first_payload,
                                     headers={"Cookie": "token=" + first_token})
        compare("First token validity before second login", 200, first_response.status_code)
        assert first_response.status_code == 200
        assert_booking_matches("First authenticated update", first_payload, response_body(first_response))
    second_client = BookerClient(settings, observer=api.observer)
    try:
        with allure.step("Login with the same credentials using a separate client"):
            second_token = second_client.auth.token()
            different_tokens = first_token != second_token
            attach_json("Second login token summary", {"new_token_issued": True,
                                                        "tokens_differ": different_tokens})
            assert different_tokens
            second_response = second_client.request("PUT", path, json=second_payload,
                                                     headers={"Cookie": "token=" + second_token})
            compare("New token validity", 200, second_response.status_code)
            assert second_response.status_code == 200
            assert_booking_matches("New token update response", second_payload, response_body(second_response))
        with allure.step("Negative control: invalid token must be rejected"):
            invalid_response = second_client.request("PUT", path, json=old_token_payload,
                                                     headers={"Cookie": "token=deliberately-invalid"})
            compare("Invalid-token protection", 403, invalid_response.status_code)
            assert invalid_response.status_code == 403
            unchanged = second_client.request("GET", path)
            assert unchanged.status_code == 200
            assert_booking_matches("Rejected invalid token leaves state unchanged", second_payload, response_body(unchanged))
        with allure.step("Reuse the original token after the second login, without automatic refresh"):
            old_response = api.request("PUT", path, json=old_token_payload,
                                       headers={"Cookie": "token=" + first_token})
            persisted = api.request("GET", path)
            attach_json("Previous-token validity after new login", {
                "first_token_before_login_status": first_response.status_code,
                "new_token_status": second_response.status_code,
                "invalid_token_status": invalid_response.status_code,
                "previous_token_after_login_status": old_response.status_code,
                "previous_token_accepted": old_response.status_code == 200,
                "automatic_auth_refresh": False,
                "claim_scope": "new-login revocation only; time-based token expiration is unmeasured",
                "persisted_status": persisted.status_code, "persisted_body": response_body(persisted),
            })
            assert old_response.status_code in {200, 401, 403}, "Unexpected API failure, not a revocation result"
            assert persisted.status_code == 200
            expected = old_token_payload if old_response.status_code == 200 else second_payload
            assert_booking_matches("State after original-token attempt", expected, response_body(persisted))
            if old_response.status_code == 200:
                assert_booking_matches("Original-token update response", old_token_payload, response_body(old_response))
            return old_response.status_code
    finally:
        second_client.close()


# Characterize whether the sandbox retains the first session after a second login.
@pytest.mark.live
def test_sandbox_keeps_previous_token_valid_after_new_login(api, settings, booking):
    assert probe_previous_token_after_new_login(api, settings, booking) == 200


# A single-session policy would revoke the old token; confirmed acceptance is a sandbox gap.
@pytest.mark.live
@pytest.mark.business_gap
@pytest.mark.xfail(strict=True, raises=TokenRevocationUnsupported,
                   reason="Sandbox retains previous tokens after a new login; single-session revocation unsupported")
def test_new_login_invalidates_previous_token(api, settings, booking):
    status = probe_previous_token_after_new_login(api, settings, booking)
    if status == 200:
        raise TokenRevocationUnsupported("Previous token still authorizes PUT after another client logs in")
    assert status in {401, 403}
