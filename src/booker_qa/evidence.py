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
        self.phase = "setup"

    def __call__(self, event):
        with self._lock:
            self._events.append(sanitize({"phase": self.phase, **event}))

    def snapshot(self):
        with self._lock:
            return deepcopy(self._events)


def json_diff(expected, actual, path="$", *, protected=False):
    """Type-sensitive JSON differences, preserving missing vs null and redacting secrets."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(expected.keys() | actual.keys()):
            hidden = protected or str(key).lower() in SECRET_KEYS
            child_path = f"{path}.{key}"
            if key not in expected or key not in actual:
                differences.append({
                    "path": child_path, "change": "added" if key not in expected else "removed",
                    "expected_present": key in expected, "actual_present": key in actual,
                    "expected": "[REDACTED]" if hidden else sanitize(expected.get(key)),
                    "actual": "[REDACTED]" if hidden else sanitize(actual.get(key)),
                })
            else:
                differences.extend(json_diff(expected[key], actual[key], child_path, protected=hidden))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            if index >= len(expected) or index >= len(actual):
                differences.append({
                    "path": f"{path}[{index}]", "change": "added" if index >= len(expected) else "removed",
                    "expected_present": index < len(expected), "actual_present": index < len(actual),
                    "expected": "[REDACTED]" if protected else sanitize(expected[index]) if index < len(expected) else None,
                    "actual": "[REDACTED]" if protected else sanitize(actual[index]) if index < len(actual) else None,
                })
            else:
                differences.extend(json_diff(expected[index], actual[index], f"{path}[{index}]", protected=protected))
        return differences
    if type(expected) is not type(actual) or expected != actual:
        return [{"path": path, "change": "changed", "expected": "[REDACTED]" if protected else sanitize(expected),
                 "actual": "[REDACTED]" if protected else sanitize(actual)}]
    return []
