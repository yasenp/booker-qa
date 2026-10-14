"""Controlled AuthManager and client-refresh tests; no public sandbox or real token expiry."""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event, Lock, Thread
from time import monotonic

import httpx
import pytest

from booker_qa.auth.manager import AuthManager
from booker_qa.client import BookerClient
from booker_qa.config import Settings


# Eight simultaneous callers must share one token issuance while the issuer is blocked.
def test_parallel_initial_acquisition_is_single_flight():
    """Release callers together, hold the first issuance open while contenders run, then
    release it and join all threads with bounded waits.

    Type: Controlled authentication concurrency.

    Expected: The issuer runs exactly once, every caller receives the same token, and no
    thread remains alive.

    Cases: 8 threads and one blocked issuer callback.

    Scope: This exercises AuthManager locking without HTTP. The separate live setup test
    counts real POST /auth requests.
    """
    issued = []
    issue_lock = Lock()
    barrier = Barrier(9, timeout=5)
    issuance_started, release_issuer, duplicate_issuer = Event(), Event(), Event()
    outcomes = Queue()
    def issue():
        with issue_lock:
            issued.append("token")
            if len(issued) > 1:
                duplicate_issuer.set()
        issuance_started.set()
        if not release_issuer.wait(timeout=5):
            raise TimeoutError("Test did not release the token issuer")
        return "token"
    manager = AuthManager(issue)
    def acquire():
        try:
            barrier.wait()
            outcomes.put(manager.token())
        except Exception as exc:
            outcomes.put(exc)
    # Daemon threads and bounded joins let a lock regression fail instead of hanging pytest.
    threads = [Thread(target=acquire, daemon=True) for _ in range(8)]
    for thread in threads:
        thread.start()
    try:
        barrier.wait()
        assert issuance_started.wait(timeout=5), "Token issuance never started"
        # Keep the first issuer blocked while competing callers run. A duplicate wakes this early.
        duplicate_issuer.wait(timeout=0.2)
    finally:
        release_issuer.set()
        deadline = monotonic() + 5
        for thread in threads:
            thread.join(timeout=max(0, deadline - monotonic()))
    assert all(not thread.is_alive() for thread in threads), "Token acquisition did not finish"
    assert issued == ["token"]
    assert [outcomes.get_nowait() for _ in threads] == ["token"] * 8


# Concurrent rejection of one cached token must trigger one shared replacement.
@pytest.mark.parametrize("rejection", [401, 403])
def test_concurrent_rejection_refreshes_once(rejection):
    """Use MockTransport to synchronize four rejected requests carrying the same original
    cookie before allowing refreshed requests.

    Type: Controlled authentication concurrency.

    Expected: All four protected calls finish with 200 and only two tokens are issued
    overall: initial acquisition plus one refresh.

    Cases: 401 and 403; 4 callers each.

    Scope: Verifies client coordination under modeled rejection, not a hosted token
    lifetime.
    """
    count = 0
    lock = Lock()
    barrier = Barrier(4)
    def respond(request):
        nonlocal count
        if request.url.path == "/auth":
            with lock:
                count += 1
                return httpx.Response(200, json={"token": f"token-{count}"})
        if request.headers["Cookie"] == "token=token-1":
            barrier.wait(timeout=5)
            return httpx.Response(rejection)
        return httpx.Response(200, json={"ok": True})
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        assert api.auth.token() == "token-1"
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: api.request("PUT", "/booking/1", authenticated=True), range(4)))
        assert [r.status_code for r in results] == [200] * 4
        assert count == 2
    finally:
        api.close()


# Persistent forbidden responses must stop after one refresh and one replay.
def test_persistent_forbidden_refresh_is_bounded():
    """Have MockTransport issue valid-looking tokens but reject every protected request.

    Type: Controlled authentication resilience.

    Expected: The caller receives the second 403; exactly two auth calls and two protected
    writes occur.

    Cases: Protected PUT always returns 403.
    """
    auth_calls = []
    writes = []
    def respond(request):
        if request.url.path == "/auth":
            auth_calls.append(1)
            return httpx.Response(200, json={"token": str(len(auth_calls))})
        writes.append(1)
        return httpx.Response(403)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        assert api.request("PUT", "/booking/1", authenticated=True).status_code == 403
        assert len(auth_calls) == len(writes) == 2
    finally:
        api.close()


# A credential-denial body must not populate the token cache.
def test_authentication_failure_does_not_cache_missing_token():
    """Return HTTP 200 with Bad credentials from the mocked authentication endpoint and request
    a token twice.

    Type: Controlled authentication negative.

    Expected: Each attempt raises ValueError and reaches authentication again, proving a
    missing token was not cached as usable.

    Cases: 2 acquisition attempts without a returned token.
    """
    calls = []
    def respond(request):
        calls.append(1)
        return httpx.Response(200, json={"reason": "Bad credentials"})
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        for _ in range(2):
            with pytest.raises(ValueError, match="token"):
                api.auth.token()
        assert len(calls) == 2
    finally:
        api.close()
