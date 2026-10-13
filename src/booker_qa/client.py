"""Bounded read retries; one auth refresh for explicitly protected requests."""
import logging
import time
from typing import Any, Callable

import httpx

from booker_qa.auth.manager import AuthManager
from booker_qa.config import Settings

log = logging.getLogger(__name__)


class BookerClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None,
                 sleeper=time.sleep, observer: Callable[[dict], None] | None = None):
        self.settings = settings
        self._sleep = sleeper
        self.observer = observer
        self.http = httpx.Client(
            base_url=settings.base_url, timeout=settings.timeout_seconds,
            headers={"Accept": "application/json"}, transport=transport,
        )
        self.auth = AuthManager(self._issue_token)

    def _issue_token(self) -> str:
        response = self._send("POST", "/auth", json={
            "username": self.settings.username, "password": self.settings.password,
        })
        response.raise_for_status()
        token = response.json().get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("Authentication response did not contain a token")
        return token

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempts = self.settings.read_attempts
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = self.http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                self._observe(method, path, kwargs, attempt, started, error=type(exc).__name__)
                # Connection establishment failures occur before a request is sent.
                # Read/write failures on mutations have ambiguous outcomes.
                retryable = method in {"GET", "HEAD"} or isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
                if not retryable or attempt == attempts - 1:
                    raise
            else:
                self._observe(method, path, kwargs, attempt, started, response=response)
                if method not in {"GET", "HEAD"} or response.status_code not in {429, 502, 503, 504} or attempt == attempts - 1:
                    return response
            log.warning("Retrying %s %s after transient failure (attempt %s)", method, path, attempt + 1)
            self._sleep(self.settings.retry_backoff_seconds * 2 ** attempt)
        raise RuntimeError("Unreachable retry state")

    def _observe(self, method, path, kwargs, attempt, started, *, response=None, error=None):
        if self.observer is None:
            return
        # Do not emit headers, query strings, raw exception messages, or auth bodies.
        from booker_qa.evidence import sanitize
        endpoint = path.split("?", 1)[0]
        body = "[authentication body omitted]" if endpoint == "/auth" else sanitize(kwargs.get("json"))
        result = None
        if response is not None:
            if endpoint == "/auth":
                result = "[authentication body omitted]"
            else:
                try:
                    result = sanitize(response.json())
                except ValueError:
                    result = "[non-JSON body omitted]"
        self.observer({
            "method": method, "path": endpoint, "attempt": attempt + 1,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "status": response.status_code if response is not None else None,
            "error": error, "request_body": body, "response_body": result,
        })

    def request(self, method: str, path: str, *, authenticated: bool = False,
                **kwargs: Any) -> httpx.Response:
        method = method.upper()
        if not authenticated:
            return self._send(method, path, **kwargs)
        headers = dict(kwargs.pop("headers", {}) or {})
        token = self.auth.token()
        headers["Cookie"] = "token=" + token
        response = self._send(method, path, headers=headers, **kwargs)
        if response.status_code in {401, 403}:
            log.warning("Refreshing rejected authentication for %s %s", method, path)
            headers["Cookie"] = "token=" + self.auth.refresh(token)
            response = self._send(method, path, headers=headers, **kwargs)
        return response

    def close(self) -> None:
        self.http.close()
