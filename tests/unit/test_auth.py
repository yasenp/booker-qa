from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Barrier, Event, Lock, Thread
from time import monotonic

import httpx
import pytest

from booker_qa.auth.manager import AuthManager
from booker_qa.client import BookerClient
from booker_qa.config import Settings


# Eight simultaneous token requests must invoke the token issuer only once.
def test_parallel_initial_acquisition_is_single_flight():
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


# Concurrent rejection of one token must trigger only one shared refresh.
@pytest.mark.parametrize("rejection", [401, 403])
def test_concurrent_rejection_refreshes_once(rejection):
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


def test_persistent_forbidden_refresh_is_bounded():
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


def test_authentication_failure_does_not_cache_missing_token():
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
