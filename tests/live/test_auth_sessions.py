from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import allure
import pytest

from reporting import assert_booking_matches, attach_json, compare, response_body
from booker_qa.client import BookerClient


# Valid credentials must authorize a protected update and persist the complete booking.
@pytest.mark.live
def test_valid_login_authorizes_booking_update(api, booking):
    token = api.auth.token()
    payload = {**booking.payload, "totalprice": 432}
    path = f"/booking/{booking.booking_id}"
    response = api.request("PUT", path, json=payload, headers={"Cookie": "token=" + token})
    persisted = api.request("GET", path)
    assert response.status_code == 200
    assert_booking_matches("Valid-token update response", payload, response_body(response))
    assert persisted.status_code == 200
    assert_booking_matches("Valid-token persisted update", payload, response_body(persisted))


# Wrong, empty, or omitted credentials must return Bad credentials without issuing a token.
@pytest.mark.live
@pytest.mark.parametrize("case", ["wrong_password", "empty_credentials", "missing_credentials"])
def test_auth_rejects_invalid_credentials(api, settings, case):
    credentials = {
        "wrong_password": {"username": settings.username, "password": "wrong-" + uuid4().hex},
        "empty_credentials": {"username": "", "password": ""},
        "missing_credentials": {},
    }[case]
    response = api.request("POST", "/auth", json=credentials)
    body = response_body(response)
    attach_json("Invalid credentials result", {
        "case": case, "status": response.status_code,
        "reason": body.get("reason") if isinstance(body, dict) else None,
        "token_present": isinstance(body, dict) and "token" in body,
    })
    assert response.status_code == 200
    matches_bad_credentials = body == {"reason": "Bad credentials"}
    assert matches_bad_credentials, "Invalid credentials must return only Bad credentials, without a token"


def assert_unauthorized_mutation_preserves_booking(api, booking, method, headers):
    path = f"/booking/{booking.booking_id}"
    kwargs = {} if method == "DELETE" else {
        "json": {**booking.payload, "totalprice": 876} if method == "PUT" else {"totalprice": 876}}
    # Explicit headers without authenticated=True prevent the client from masking rejection with refresh.
    response = api.request(method, path, headers=headers, **kwargs)
    persisted = api.request("GET", path)
    actual = {"mutation_status": response.status_code, "get_status": persisted.status_code,
              "booking": response_body(persisted)}
    expected = {"mutation_status": 403, "get_status": 200, "booking": booking.payload}
    differences = compare("Unauthorized mutation must be rejected without changing state", expected, actual)
    assert not differences, f"{method} authorization or state preservation failed: {differences}"


# Missing, empty, unissued, and modified tokens must not authorize PUT, PATCH, or DELETE.
@pytest.mark.live
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("token_case", ["missing", "empty", "unissued", "modified"])
def test_protected_mutations_reject_bad_tokens(api, booking, method, token_case):
    headers = {}
    if token_case == "empty":
        headers["Cookie"] = "token="
    elif token_case == "unissued":
        headers["Cookie"] = "token=unissued-" + uuid4().hex
    elif token_case == "modified":
        original = api.auth.token()
        altered = original[:-1] + ("0" if original[-1] != "0" else "1")
        headers["Cookie"] = "token=" + altered
    assert_unauthorized_mutation_preserves_booking(api, booking, method, headers)


# Object-prototype property names are not issued credentials and must never authorize a mutation.
@pytest.mark.live
@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("property_name", ["toString", "constructor", "__proto__"])
def test_inherited_property_tokens_are_rejected(api, booking, method, property_name):
    assert_unauthorized_mutation_preserves_booking(api, booking, method, {"Cookie": "token=" + property_name})


# Independent parallel login requests must each issue a usable token for their own booking.
@pytest.mark.live
def test_parallel_independent_logins_issue_usable_tokens(api, settings, registry):
    handles = [registry.create()[0] for _ in range(4)]
    clients = [BookerClient(settings, observer=api.observer) for _ in handles]
    barrier = Barrier(4, timeout=30)
    cursor = len(api.observer.snapshot())

    def login_and_update(index):
        client, handle = clients[index], handles[index]
        barrier.wait()
        token = client.auth.token()
        payload = {**handle.payload, "totalprice": 500 + index}
        response = client.request("PUT", f"/booking/{handle.booking_id}", json=payload,
                                  headers={"Cookie": "token=" + token})
        return token, {"client": index, "status": response.status_code, "expected": payload,
                       "response": response_body(response)}

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(login_and_update, range(4), timeout=60))
        unique_tokens = len({token for token, _ in results})
        auth = [e for e in api.observer.snapshot()[cursor:]
                if e["kind"] == "http" and e["method"] == "POST" and e["path"] == "/auth"]
        summary = {"clients": 4, "unique_token_count": unique_tokens,
                   "logical_auth_requests": len({e["request_id"] for e in auth}),
                   "successful_issuances": sum(e["status"] == 200 for e in auth),
                   "updates": [outcome for _, outcome in results]}
        attach_json("Independent parallel login results", summary)
        assert unique_tokens == summary["logical_auth_requests"] == summary["successful_issuances"] == 4
        for handle, (_, outcome) in zip(handles, results):
            assert outcome["status"] == 200
            assert_booking_matches("Independent-client response", outcome["expected"], outcome["response"])
            persisted = api.request("GET", f"/booking/{handle.booking_id}")
            assert persisted.status_code == 200
            assert_booking_matches("Independent-client persisted state", outcome["expected"], response_body(persisted))
    finally:
        for client in clients:
            client.close()


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
        assert response.status_code == 200
        matches_bad_credentials = body == {"reason": "Bad credentials"}
        assert matches_bad_credentials, "Unknown user must return only Bad credentials, without a token"
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


# A new login must revoke the previous token under the requested single-session policy.
@pytest.mark.live
def test_new_login_invalidates_previous_token(api, settings, booking):
    status = probe_previous_token_after_new_login(api, settings, booking)
    assert status in {401, 403}, (
        f"Previous token must be rejected after a new login under the requested policy; got HTTP {status}"
    )
