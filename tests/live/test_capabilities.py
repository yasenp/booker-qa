import pytest
from booker_qa.client import BookerClient
from booker_qa.data import booking_payload
from reporting import assert_booking_matches, attach_json, response_body

pytestmark = pytest.mark.live


class UnsupportedBusinessRule(AssertionError):
    """Only known business acceptance triggers expected failure."""


def test_sandbox_accepts_duplicate_booking(registry, settings):
    payload = booking_payload()
    first, _ = registry.create(payload)
    second_client = BookerClient(settings, observer=registry.client.observer)
    try:
        second, body = registry.create(payload, client=second_client)
        assert second.booking_id != first.booking_id
        assert_booking_matches("Duplicate booking response payload", payload, body)
    finally:
        second_client.close()


@pytest.mark.parametrize("invalid", ["reversed_dates", "negative_price"])
def test_sandbox_retains_invalid_business_values(registry, invalid):
    payload = booking_payload()
    if invalid == "reversed_dates":
        payload["bookingdates"] = {"checkin": "2027-02-10", "checkout": "2027-02-01"}
    else:
        payload["totalprice"] = -1
    _, body = registry.create(payload)
    assert_booking_matches("Sandbox invalid-value characterization", payload, body)


@pytest.mark.business_gap
@pytest.mark.xfail(strict=True, raises=UnsupportedBusinessRule, reason="Sandbox accepts duplicate date-range bookings; no room inventory")
def test_business_duplicate_rejection(registry):
    payload = booking_payload()
    registry.create(payload)
    response = registry.client.request("POST", "/booking", json=payload)
    if response.status_code == 200:
        registry.ids.append(response.json()["bookingid"])
    attach_json("Business gap: duplicate rejection", {"expected_statuses": [400, 409],
                "actual_status": response.status_code, "actual_body": response_body(response),
                "classification": "known business gap" if response.status_code == 200 else "review response"})
    # Transport/server failures are failures, not expected business gaps.
    assert response.status_code in {200, 400, 409}, "Unexpected API failure"
    if response.status_code == 200:
        assert_booking_matches("Accepted booking matches submitted payload", payload, response.json()["booking"])
        raise UnsupportedBusinessRule("Duplicate was accepted")


@pytest.mark.business_gap
@pytest.mark.parametrize("invalid", ["reversed_dates", "negative_price"])
@pytest.mark.xfail(strict=True, raises=UnsupportedBusinessRule, reason="Sandbox does not enforce date ordering or nonnegative price")
def test_business_invalid_values_rejected(registry, invalid):
    payload = booking_payload()
    if invalid == "reversed_dates":
        payload["bookingdates"] = {"checkin": "2027-02-10", "checkout": "2027-02-01"}
    else:
        payload["totalprice"] = -1
    response = registry.client.request("POST", "/booking", json=payload)
    if response.status_code == 200:
        registry.ids.append(response.json()["bookingid"])
    attach_json("Business gap: invalid value rejection", {"invalid_case": invalid,
                "expected_statuses": [400, 409, 422], "actual_status": response.status_code,
                "actual_body": response_body(response)})
    assert response.status_code in {200, 400, 409, 422}, "Unexpected API failure"
    if response.status_code == 200:
        assert_booking_matches("Accepted booking matches submitted payload", payload, response.json()["booking"])
        raise UnsupportedBusinessRule("Invalid business value was accepted")
