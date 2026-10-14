"""Booking search boundaries and validation of date filters."""
from datetime import date, timedelta

import pytest

from reporting import assert_booking_matches, attach_json, compare, response_body

pytestmark = pytest.mark.live


def scoped_ids(api, booking, **filters):
    params = {"firstname": booking.payload["firstname"], **filters}
    response = api.request("GET", "/booking", params=params)
    body = response_body(response)
    attach_json("Scoped booking search", {"params": params, "status": response.status_code, "body": body})
    assert response.status_code == 200
    assert isinstance(body, list)
    assert all(isinstance(item, dict) and type(item.get("bookingid")) is int for item in body)
    ids = sorted(item["bookingid"] for item in body)
    assert set(ids) <= {booking.booking_id}, "Unique guest filter returned unrelated bookings"
    return ids


def verify_search_control(api, booking):
    assert scoped_ids(api, booking) == [booking.booking_id]
    response = api.request("GET", f"/booking/{booking.booking_id}")
    assert response.status_code == 200, "Owned booking unavailable"
    assert_booking_matches("Search control still exists unchanged", booking.payload, response_body(response))


# Check-in search must include bookings equal to or later than the threshold.
def test_checkin_filter_includes_boundary(api, booking):
    verify_search_control(api, booking)
    boundary = date.fromisoformat(booking.payload["bookingdates"]["checkin"])
    actual = {label: scoped_ids(api, booking, checkin=(boundary + timedelta(days=offset)).isoformat())
              for label, offset in [("before", -1), ("equal", 0), ("after", 1)]}
    verify_search_control(api, booking)
    expected = {"before": [booking.booking_id], "equal": [booking.booking_id], "after": []}
    differences = compare("Check-in threshold membership", expected, actual)
    assert not differences, f"Check-in filter must be inclusive: {differences}"


# Checkout search must include bookings on or after the threshold, as documented.
def test_checkout_filter_uses_documented_direction(api, booking):
    verify_search_control(api, booking)
    boundary = date.fromisoformat(booking.payload["bookingdates"]["checkout"])
    actual = {label: scoped_ids(api, booking, checkout=(boundary + timedelta(days=offset)).isoformat())
              for label, offset in [("before", -1), ("equal", 0), ("after", 1)]}
    verify_search_control(api, booking)
    expected = {"before": [booking.booking_id], "equal": [booking.booking_id], "after": []}
    differences = compare("Checkout threshold membership", expected, actual)
    assert not differences, f"Checkout filter must select dates on or after the threshold: {differences}"


# Invalid date filters must return a client validation error while valid searches still work.
@pytest.mark.parametrize("field", ["checkin", "checkout"])
def test_malformed_date_filter_returns_client_error(api, booking, field):
    verify_search_control(api, booking)
    scoped_ids(api, booking, **{field: booking.payload["bookingdates"][field]})
    params = {"firstname": booking.payload["firstname"], field: "not-a-date"}
    response = api.request("GET", "/booking", params=params)
    attach_json("Malformed date filter validation", {
        "params": params, "expected_statuses": [400, 422],
        "actual_status": response.status_code, "response": response_body(response),
    })
    verify_search_control(api, booking)
    scoped_ids(api, booking, **{field: booking.payload["bookingdates"][field]})
    assert response.status_code in {400, 422}, (
        f"Invalid {field} must return a client validation error, got HTTP {response.status_code}"
    )
