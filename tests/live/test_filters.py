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


# Check-in filtering must include the exact date boundary and exclude later thresholds.
def test_checkin_filter_includes_boundary(api, booking):
    """Search a unique guest's booking at three calculated check-in thresholds, with unfiltered
    presence controls before and after.

    Type: Live search boundary.

    Expected: The booking appears for the earlier and equal thresholds, disappears for the
    later threshold, and retains its full payload.

    Cases: Thresholds one day before, equal to, and one day after check-in.
    """
    verify_search_control(api, booking)
    boundary = date.fromisoformat(booking.payload["bookingdates"]["checkin"])
    actual = {label: scoped_ids(api, booking, checkin=(boundary + timedelta(days=offset)).isoformat())
              for label, offset in [("before", -1), ("equal", 0), ("after", 1)]}
    verify_search_control(api, booking)
    expected = {"before": [booking.booking_id], "equal": [booking.booking_id], "after": []}
    differences = compare("Check-in threshold membership", expected, actual)
    assert not differences, f"Check-in filter must be inclusive: {differences}"


# Checkout filtering must apply the documented inclusive lower-bound comparison.
def test_checkout_filter_uses_documented_direction(api, booking):
    """Search a unique guest's booking at three calculated checkout thresholds and verify the
    record remains available.

    Type: Live search boundary.

    Expected: The booking appears for earlier/equal thresholds and is excluded for the later
    threshold; unrelated guest records never appear.

    Cases: Thresholds one day before, equal to, and one day after checkout.
    """
    verify_search_control(api, booking)
    boundary = date.fromisoformat(booking.payload["bookingdates"]["checkout"])
    actual = {label: scoped_ids(api, booking, checkout=(boundary + timedelta(days=offset)).isoformat())
              for label, offset in [("before", -1), ("equal", 0), ("after", 1)]}
    verify_search_control(api, booking)
    expected = {"before": [booking.booking_id], "equal": [booking.booking_id], "after": []}
    differences = compare("Checkout threshold membership", expected, actual)
    assert not differences, f"Checkout filter must select dates on or after the threshold: {differences}"


# Malformed date filters must fail validation while valid searches remain available.
@pytest.mark.parametrize("field", ["checkin", "checkout"])
def test_malformed_date_filter_returns_client_error(api, booking, field):
    """Surround a not-a-date search with valid guest/date searches and full-state presence
    checks.

    Type: Live search negative.

    Expected: The malformed filter receives 400/422 and the valid controls still succeed
    without changing the owned booking.

    Cases: checkin and checkout.

    Scope: A server error or failed positive control remains a failure rather than being
    interpreted as correct validation.
    """
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
