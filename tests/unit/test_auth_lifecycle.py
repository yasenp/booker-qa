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


# The expiry workflow accepts 401/403 and verifies one refresh for sequential or concurrent recovery.
@pytest.mark.parametrize("workers", [0, 1, 4])
@pytest.mark.parametrize("rejection", [401, 403])
def test_token_expiry_workflow_with_controlled_clock(auth_scenarios, workers, rejection):
    run_expiry_model(auth_scenarios["auth_expiry"], workers, rejection)


# Nonexpiring tokens, outages, unauthorized mutation, and unsuccessful recovery must fail the live assertions.
@pytest.mark.parametrize("behavior", ["never_expires", "server_error", "rejection_mutates", "fresh_failure", "recovery_rejected"])
def test_token_expiry_workflow_detects_failures(auth_scenarios, behavior):
    with pytest.raises(AssertionError):
        run_expiry_model(auth_scenarios["auth_expiry"], 1, behavior=behavior)


# Revocation passes only when the original token is rejected, without silently authenticating again.
@pytest.mark.parametrize("revokes", [True, False])
def test_new_login_policy_assertion_without_automatic_refresh(auth_scenarios, revokes, monkeypatch):
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
