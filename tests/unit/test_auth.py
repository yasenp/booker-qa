from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import httpx
import pytest

from booker_qa.auth.manager import AuthManager
from booker_qa.client import BookerClient
from booker_qa.config import Settings


def test_parallel_initial_acquisition_is_single_flight():
    issued = []
    barrier = Barrier(8)
    def issue():
        issued.append("token")
        return "token"
    manager = AuthManager(issue)
    def acquire(_):
        barrier.wait()
        return manager.token()
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(acquire, range(8))) == ["token"] * 8
    assert issued == ["token"]


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
