"""Bounded read retries; one auth refresh for explicitly protected requests."""
import logging
import time
from typing import Any, Callable
from uuid import uuid4

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
        self.event("auth_acquired", outcome="token issued; value omitted")
        return token

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        attempts = self.settings.read_attempts
        request_id = uuid4().hex[:12]
        for attempt in range(attempts):
            started = time.perf_counter_ns()
            try:
                response = self.http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                retry_reason = type(exc).__name__
                self._observe(method, path, kwargs, attempt, started, request_id, error=type(exc).__name__)
                # Connection establishment failures occur before a request is sent.
                # Read/write failures on mutations have ambiguous outcomes.
                retryable = method in {"GET", "HEAD"} or isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
                if not retryable or attempt == attempts - 1:
                    raise
            else:
                retry_reason = f"HTTP {response.status_code}"
                self._observe(method, path, kwargs, attempt, started, request_id, response=response)
                if method not in {"GET", "HEAD"} or response.status_code not in {429, 502, 503, 504} or attempt == attempts - 1:
                    return response
            log.warning("Retrying %s %s after transient failure (attempt %s)", method, path, attempt + 1)
            backoff = self.settings.retry_backoff_seconds * 2 ** attempt
            self.event("retry_scheduled", request_id=request_id, method=method, path=path.split("?", 1)[0],
                       next_attempt=attempt + 2, backoff_seconds=backoff,
                       reason=retry_reason)
            self._sleep(backoff)
        raise RuntimeError("Unreachable retry state")

    def _observe(self, method, path, kwargs, attempt, started, request_id, *, response=None, error=None):
        if self.observer is None:
            return
        # Only explicitly allowed headers; no query strings, exception messages, or auth bodies.
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
        request_headers = response.request.headers if response is not None else {
            **dict(self.http.headers), **dict(kwargs.get("headers", {}) or {})}
        allowed = {"accept", "content-type", "content-length", "retry-after", "etag", "last-modified"}
        self.observer({
            "kind": "http", "request_id": request_id, "timestamp_ns": started,
            "method": method, "path": endpoint, "attempt": attempt + 1,
            "elapsed_ms": round((time.perf_counter_ns() - started) / 1_000_000, 3),
            "status": response.status_code if response is not None else None,
            "error": error, "request_body": body, "response_body": result,
            "request_headers": {key.lower(): value for key, value in request_headers.items() if key.lower() in allowed},
            "response_headers": {key: value for key, value in response.headers.items() if key in allowed} if response is not None else {},
        })

    def event(self, kind, **details):
        if self.observer is not None:
            from booker_qa.evidence import sanitize
            self.observer(sanitize({"kind": kind, "timestamp_ns": time.perf_counter_ns(), **details}))

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
            self.event("auth_refresh", method=method, path=path.split("?", 1)[0],
                       trigger_status=response.status_code, retry_limit=1)
            log.warning("Refreshing rejected authentication for %s %s", method, path)
            headers["Cookie"] = "token=" + self.auth.refresh(token)
            response = self._send(method, path, headers=headers, **kwargs)
        return response

    def close(self) -> None:
        self.http.close()
