import allure
import pytest
from booker_qa.client import BookerClient
from booker_qa.data import booking_payload
from booker_qa.schemas.booking import validate_invariants
from reporting import assert_booking_matches, attach_json, response_body

pytestmark = pytest.mark.live


def attempt_duplicate_in_second_context(registry, settings):
    """Use independent authenticated sessions; the sandbox has one account and no rooms."""
    # The factory calculates check-in = today + 30 days and checkout = check-in + 3 days.
    payload = booking_payload()
    validate_invariants(payload)
    first_client = registry.client
    with allure.step("Context A: log in and create the calculated date-range booking"):
        first_token = first_client.auth.token()
        first_client.http.cookies.set("token", first_token)
        first, body = registry.create(payload)
        assert_booking_matches("First booking matches calculated dates and payload", payload, body)
    second_client = BookerClient(settings, observer=registry.client.observer)
    try:
        with allure.step("Context B: log in independently and submit the identical booking"):
            second_token = second_client.auth.token()
            distinct_tokens = first_token != second_token
            assert distinct_tokens, "Independent logins must issue distinct session tokens"
            second_client.http.cookies.set("token", second_token)
            response = second_client.request("POST", "/booking", json=payload)
            body = response_body(response)
            duplicate_id = body.get("bookingid") if isinstance(body, dict) else None
            # Register before assertions so an unexpected response still gets cleaned up.
            if type(duplicate_id) is int and duplicate_id > 0 and duplicate_id != first.booking_id:
                registry.ids.append(duplicate_id)
            attach_json("Duplicate booking contexts and outcome", {
                "bookingdates": payload["bookingdates"], "arrival_offset_days": 30, "stay_nights": 3,
                "first_booking_id": first.booking_id, "duplicate_booking_id": duplicate_id,
                "independent_http_clients": first_client.http is not second_client.http,
                "distinct_session_tokens": distinct_tokens, "same_credentials": True,
                "scope": "Two sessions of the sandbox account; distinct users and room inventory are unsupported",
                "expected_rejection_statuses": [400, 409], "actual_status": response.status_code,
                "actual_body": body,
            })
        with allure.step("Verify the original booking remains unchanged after the duplicate attempt"):
            original = first_client.request("GET", f"/booking/{first.booking_id}")
            assert original.status_code == 200
            assert_booking_matches("Original booking after duplicate attempt", payload, response_body(original))
        if type(duplicate_id) is int and duplicate_id > 0 and duplicate_id != first.booking_id:
            persisted = second_client.request("GET", f"/booking/{duplicate_id}")
            attach_json("Duplicate resource after submission", {
                "booking_id": duplicate_id, "get_status": persisted.status_code,
                "persisted_body": response_body(persisted),
            })
            if response.status_code in {400, 409}:
                assert persisted.status_code == 404, (
                    "Duplicate rejection must not create another booking; "
                    f"returned booking ID is still accessible with HTTP {persisted.status_code}"
                )
        return response
    finally:
        second_client.close()


# The same calculated date range from a second session must be rejected; acceptance is a defect.
@allure.story("Overlapping bookings: duplicate date range")
def test_business_duplicate_rejection(registry, settings):
    response = attempt_duplicate_in_second_context(registry, settings)
    assert response.status_code in {400, 409}, (
        "Duplicate date-range booking must be rejected with HTTP 400 or 409; "
        f"got HTTP {response.status_code}. See the duplicate-context and HTTP attachments for evidence."
    )
