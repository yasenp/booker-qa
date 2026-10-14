"""Verify cross-session duplicate assertions without treating model results as hosted evidence."""
from copy import deepcopy
from datetime import date
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from booker_qa import data
from booker_qa.bookings import BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings


@pytest.fixture(scope="module")
def capabilities():
    path = Path(__file__).parents[1] / "live/test_capabilities.py"
    spec = importlib.util.spec_from_file_location("duplicate_context_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Duplicate assertions must distinguish real rejection from acceptance or hidden mutation.
@pytest.mark.parametrize("outcome", ["accepted", "reject_400", "reject_409", "server_error",
                                     "malformed_acceptance", "rejection_mutates_original",
                                     "accepted_201", "rejection_creates_duplicate", "success_with_error_text"])
def test_duplicate_context_and_failure_classification(capabilities, monkeypatch, outcome):
    """Run the actual duplicate scenario with two mocked HTTP clients and a fixed date crossing
    year-end; model rejection, acceptance, malformed results, and rejection with side
    effects.

    Type: Controlled cross-session regression.

    Expected: Only clean 400/409 rejection passes. Both sessions use their own issued
    cookie, identical calculated dates are submitted, failures raise ordinary assertions,
    and every created record is cleaned up.

    Cases: 9 duplicate response/state outcomes.

    Scope: The model verifies request construction and assertion behavior, not hosted
    overlap enforcement or distinct-user authorization.
    """
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2028, 12, 15)

    monkeypatch.setattr(data, "date", FixedDate)
    records, submissions, auth_requests, clients = {}, [], [], []

    def respond(request):
        if request.url.path == "/auth":
            auth_requests.append(json.loads(request.content))
            return httpx.Response(200, json={"token": f"session-{len(auth_requests)}"})
        if request.method == "POST":
            payload = json.loads(request.content)
            submissions.append((payload, request.headers.get("cookie")))
            if len(submissions) == 2:
                if outcome == "success_with_error_text":
                    return httpx.Response(200, json={"reason": "Duplicate booking"})
                if outcome == "rejection_mutates_original":
                    records[1]["totalprice"] = 999
                    return httpx.Response(409)
                if outcome in {"reject_400", "reject_409", "server_error"}:
                    return httpx.Response({"reject_400": 400, "reject_409": 409, "server_error": 500}[outcome])
            booking_id = len(records) + 1
            records[booking_id] = deepcopy(payload)
            body = {"bookingid": booking_id, "booking": deepcopy(payload)}
            if len(submissions) == 2 and outcome == "malformed_acceptance":
                del body["booking"]["bookingdates"]
            status = {"accepted_201": 201, "rejection_creates_duplicate": 409}.get(outcome, 200)
            return httpx.Response(status if len(submissions) == 2 else 200, json=body)
        booking_id = int(request.url.path.rsplit("/", 1)[1])
        if request.method == "DELETE":
            records.pop(booking_id)
            return httpx.Response(201)
        return httpx.Response(200, json=deepcopy(records[booking_id]))

    def new_client(settings, **kwargs):
        client = BookerClient(settings, transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(capabilities, "BookerClient", new_client)
    api = new_client(Settings())
    registry = BookingRegistry(api)
    try:
        if outcome not in {"reject_400", "reject_409"}:
            with pytest.raises(AssertionError) as caught:
                capabilities.test_business_duplicate_rejection(registry, Settings())
            assert type(caught.value) is AssertionError
            if outcome in {"accepted", "accepted_201", "success_with_error_text", "malformed_acceptance"}:
                assert "must be rejected with HTTP 400 or 409" in str(caught.value)
        else:
            capabilities.test_business_duplicate_rejection(registry, Settings())
        assert len(clients) == 2 and clients[0].http is not clients[1].http
        assert clients[1].http.is_closed
        assert len(auth_requests) == 2 and auth_requests[0] == auth_requests[1]
        assert [cookie for _, cookie in submissions] == ["token=session-1", "token=session-2"]
        assert submissions[0][0] == submissions[1][0]
        assert submissions[0][0]["bookingdates"] == {"checkin": "2029-01-14", "checkout": "2029-01-17"}
        created_duplicate = outcome in {"accepted", "malformed_acceptance", "accepted_201", "rejection_creates_duplicate"}
        assert registry.ids == ([1, 2] if created_duplicate else [1])
    finally:
        try:
            registry.cleanup()
        finally:
            api.close()
    assert records == {}
