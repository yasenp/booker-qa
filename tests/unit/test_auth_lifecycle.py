"""Validate lifecycle assertions against controlled models; these do not prove hosted token expiry."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Lock

import httpx
import pytest

from booker_qa.bookings import BookingHandle
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.data import booking_payload
from booker_qa.evidence import EvidenceCollector


@pytest.fixture(scope="module")
def auth_scenarios():
    modules = {}
    for name in ("auth_expiry", "auth_sessions"):
        spec = importlib.util.spec_from_file_location(name + "_under_test",
                                                    Path(__file__).parents[1] / "live" / f"test_{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


def run_expiry_model(scenario, workers, rejection=403, behavior="expires"):
    payload = booking_payload()
    state = deepcopy(payload)
    issued = {}
    now = [100.0]
    waits = []
    lock = Lock()
    collector = EvidenceCollector()

    def respond(request):
        nonlocal state
        with lock:
            if request.url.path == "/auth":
                token = f"controlled-{len(issued) + 1}"
                issued[token] = now[0]
                return httpx.Response(200, json={"token": token})
            if request.method == "GET":
                return httpx.Response(200, json=state)
            token = request.headers.get("Cookie", "").removeprefix("token=")
            expired = now[0] - issued.get(token, 0) >= 10.0
            body = json.loads(request.content)
            if behavior == "fresh_failure" and token == "controlled-2":
                return httpx.Response(503)
            if behavior == "recovery_rejected" and token == "controlled-3":
                return httpx.Response(rejection)
            if expired and behavior != "never_expires":
                if behavior == "rejection_mutates":
                    state = body
                return httpx.Response(500 if behavior == "server_error" else rejection)
            state = body
            return httpx.Response(200, json=state)

    def client():
        return BookerClient(Settings(), transport=httpx.MockTransport(respond), observer=collector)

    def advance(seconds):
        waits.append(seconds)
        now[0] += seconds

    api = client()
    try:
        scenario.exercise_token_expiry(api, BookingHandle(1, payload), (10.0, 1.0), workers,
                                       fresh_client=client, clock=lambda: now[0], sleeper=advance)
        assert sum(waits) == 11.0
        assert len(issued) == (3 if workers else 2)
    finally:
        api.close()


# The expiry workflow must handle both rejection codes and each recovery mode.
@pytest.mark.parametrize("workers", [0, 1, 4])
@pytest.mark.parametrize("rejection", [401, 403])
def test_token_expiry_workflow_with_controlled_clock(auth_scenarios, workers, rejection):
    """Run the actual expiry workflow against a clock-controlled token model with a ten-second
    lifetime and one-second grace.

    Type: Controlled lifecycle assertion check.

    Expected: The workflow advances eleven simulated seconds, rejects the aged token,
    accepts a fresh control, and issues exactly one recovery token when callers are enabled.

    Cases: 401/403 x 0/1/4 recovery callers.

    Scope: Clock advancement and token validity are simulated; these passes do not establish
    expiry in the hosted sandbox.
    """
    run_expiry_model(auth_scenarios["auth_expiry"], workers, rejection)


# The expiry assertions must reject non-expiration, outages, unauthorized mutation, and failed
# recovery.
@pytest.mark.parametrize("behavior", ["never_expires", "server_error", "rejection_mutates", "fresh_failure", "recovery_rejected"])
def test_token_expiry_workflow_detects_failures(auth_scenarios, behavior):
    """Inject each invalid server behavior into the clock-controlled model used by the live
    expiry workflow.

    Type: Controlled lifecycle regression.

    Expected: The actual scenario raises AssertionError rather than treating the injected
    failure as successful expiry enforcement.

    Cases: Never expires, server error, rejection mutates, fresh failure, recovery
    rejection.

    Scope: This verifies the test oracle with deterministic models, not live server fault
    handling.
    """
    with pytest.raises(AssertionError):
        run_expiry_model(auth_scenarios["auth_expiry"], 1, behavior=behavior)


# Revocation assertions must distinguish rejected old tokens from still-valid sessions.
@pytest.mark.parametrize("revokes", [True, False])
def test_new_login_policy_assertion_without_automatic_refresh(auth_scenarios, revokes, monkeypatch):
    """Run the live two-client login workflow against a model that either clears old tokens or
    keeps them valid.

    Type: Controlled session-policy regression.

    Expected: The revoking model passes; continued old-token acceptance raises the policy
    assertion. Exactly two logins occur, so a silent refresh cannot hide revocation.

    Cases: Revoking and non-revoking token models.

    Scope: Validates the requested single-session test policy; it is not hosted revocation
    or TTL evidence.
    """
    payload = booking_payload()
    state = deepcopy(payload)
    valid = set()
    issued = []

    def respond(request):
        nonlocal state
        if request.url.path == "/auth":
            token = f"controlled-{len(issued) + 1}"
            issued.append(token)
            if revokes:
                valid.clear()
            valid.add(token)
            return httpx.Response(200, json={"token": token})
        if request.method == "GET":
            return httpx.Response(200, json=state)
        if request.headers.get("Cookie", "").removeprefix("token=") not in valid:
            return httpx.Response(403)
        state = json.loads(request.content)
        return httpx.Response(200, json=state)

    module = auth_scenarios["auth_sessions"]
    monkeypatch.setattr(module, "BookerClient", lambda settings, **kwargs:
                        BookerClient(settings, transport=httpx.MockTransport(respond), **kwargs))
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        if revokes:
            module.test_new_login_invalidates_previous_token(api, Settings(), BookingHandle(1, payload))
        else:
            with pytest.raises(AssertionError, match="Previous token must be rejected"):
                module.test_new_login_invalidates_previous_token(api, Settings(), BookingHandle(1, payload))
        assert len(issued) == 2
    finally:
        api.close()
