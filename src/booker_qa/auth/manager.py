"""Single-flight token acquisition and generation-aware refresh within a process."""
from threading import Lock
from typing import Callable


class AuthManager:
    def __init__(self, issue_token: Callable[[], str]):
        self._issue_token = issue_token
        self._token = None
        self._lock = Lock()

    def token(self) -> str:
        with self._lock:
            if self._token is None:
                self._token = self._issue_token()
            return self._token

    def refresh(self, rejected_token: str) -> str:
        with self._lock:
            # Another thread may already have replaced the rejected token.
            if self._token == rejected_token or self._token is None:
                self._token = self._issue_token()
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
