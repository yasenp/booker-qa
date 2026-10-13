"""Sanitize structured evidence before it enters any report collector."""
from copy import deepcopy
from threading import Lock

SECRET_KEYS = {"password", "username", "token", "authorization", "cookie", "set-cookie",
               "access_token", "refresh_token", "api_key", "apikey"}


def sanitize(value):
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if str(key).lower() in SECRET_KEYS else sanitize(item)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


class EvidenceCollector:
    """One collector per test client; worker threads never call Allure directly."""
    def __init__(self):
        self._events = []
        self._lock = Lock()

    def __call__(self, event):
        with self._lock:
            self._events.append(sanitize(event))

    def snapshot(self):
        with self._lock:
            return deepcopy(self._events)
