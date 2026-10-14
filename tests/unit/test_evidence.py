"""Offline checks for evidence sanitization, thread safety, precise differences, and recovery events."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.evidence import EvidenceCollector, json_diff, sanitize


# Retry and refresh warnings must retain useful paths without leaking URL or token secrets.
@pytest.mark.parametrize("failure", ["connect", "503", "401", "403"])
def test_warning_logs_exclude_url_secrets(caplog, failure):
    """Trigger recovery using a URL containing user-info, query, and fragment secrets; inspect
    both warnings and collected HTTP evidence.

    Type: Controlled logging security.

    Expected: The recovered request succeeds with two attempts and one warning; endpoint
    path remains visible while credential, token, fragment, and raw exception secrets are
    absent.

    Cases: Connect failure, 503, 401, and 403.
    """
    caplog.set_level(logging.WARNING, logger="booker_qa.client")
    collector = EvidenceCollector()
    calls = []

    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "issued-secret"})
        calls.append(1)
        if len(calls) == 1:
            if failure == "connect":
                raise httpx.ConnectTimeout("exception-secret", request=request)
            return httpx.Response(int(failure))
        return httpx.Response(200)

    api = BookerClient(Settings(), transport=httpx.MockTransport(respond),
                       observer=collector, sleeper=lambda _: None)
    try:
        path = "https://url-user:url-password@example.test/booking/1?token=query-secret#fragment-secret"
        response = api.request("GET", path, authenticated=failure in {"401", "403"})
        assert response.status_code == 200
        assert len(calls) == 2
        assert len(caplog.records) == 1
        assert "/booking/1" in caplog.text
        evidence = caplog.text + json.dumps(collector.snapshot())
        for secret in ["url-user", "url-password", "query-secret", "fragment-secret", "issued-secret", "exception-secret"]:
            assert secret not in evidence
    finally:
        api.close()


# Collected HTTP evidence must redact secrets while preserving useful booking data.
def test_auth_bodies_headers_and_query_secrets_never_enter_evidence():
    """Perform a mocked authenticated PUT with secrets placed in multiple request/response
    locations and serialize the resulting collector snapshot.

    Type: Controlled evidence security.

    Expected: No planted secret appears, authentication bodies are omitted, and
    non-sensitive response fields remain available.

    Cases: Secrets in auth, request JSON, response JSON, and query.
    """
    collector = EvidenceCollector()
    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "secret-issued-token"})
        return httpx.Response(200, json={"nested": {"password": "response-secret"}, "totalprice": 123})
    api = BookerClient(Settings(password="credential-secret"),
                       transport=httpx.MockTransport(respond), observer=collector)
    try:
        api.request("PUT", "/booking/1?token=query-secret", authenticated=True,
                    json={"totalprice": 123, "access_token": "request-secret"})
        serialized = json.dumps(collector.snapshot())
        for secret in ["secret-issued-token", "credential-secret", "response-secret", "request-secret", "query-secret"]:
            assert secret not in serialized
        http_events = [e for e in collector.snapshot() if e["kind"] == "http"]
        assert http_events[1]["response_body"]["totalprice"] == 123
        assert http_events[0]["response_body"] == "[authentication body omitted]"
    finally:
        api.close()


# Concurrent evidence collection must retain every event and isolate returned snapshots.
def test_collector_keeps_all_thread_events_and_snapshot_is_detached():
    """Collect indexed events concurrently, then mutate a nested field in a returned snapshot.

    Type: Controlled collector concurrency.

    Expected: Every index appears exactly once and a later snapshot still contains the
    original redacted nested value.

    Cases: 100 events from 8 worker threads.
    """
    collector = EvidenceCollector()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: collector({"index": index, "body": {"token": "secret"}}), range(100)))
    snapshot = collector.snapshot()
    assert sorted(event["index"] for event in snapshot) == list(range(100))
    snapshot[0]["body"]["token"] = "changed"
    assert collector.snapshot()[0]["body"]["token"] == "[REDACTED]"


# Secret-key matching must work inside nested sequences regardless of key casing.
def test_sanitizer_handles_case_and_nested_sequences():
    """Sanitize a nested dictionary/list structure containing authentication headers.

    Type: Controlled sanitization unit.

    Expected: Both sensitive values are replaced with the redaction marker while the
    surrounding structure is preserved.

    Cases: Mixed-case Authorization and Cookie keys inside a list.
    """
    assert sanitize({"items": [{"Authorization": "secret", "Cookie": "secret"}]}) == {
        "items": [{"Authorization": "[REDACTED]", "Cookie": "[REDACTED]"}]}


# JSON differences must preserve paths, types, and presence without exposing secret values.
def test_diffs_distinguish_nested_changes_types_missing_and_null_without_leaking_secrets():
    """Compare two structured payloads containing independent value, type, presence, and
    sequence differences.

    Type: Controlled comparison unit.

    Expected: Each difference identifies the correct path and change; secrets are redacted,
    and identical valid values produce no differences.

    Cases: Nested date, bool/int, missing/null, list addition, and token changes.
    """
    differences = json_diff(
        {"bookingdates": {"checkout": "2027-01-02"}, "depositpaid": True, "removed": None,
         "token": "old-secret", "items": [1]},
        {"bookingdates": {"checkout": "2027-01-03"}, "depositpaid": 1, "added": None,
         "token": "new-secret", "items": [1, 2]},
    )
    by_path = {d["path"]: d for d in differences}
    assert by_path["$.bookingdates.checkout"]["actual"] == "2027-01-03"
    assert by_path["$.depositpaid"]["change"] == "changed"
    assert not by_path["$.removed"]["actual_present"]
    assert not by_path["$.added"]["expected_present"]
    assert by_path["$.items[1]"]["change"] == "added"
    assert by_path["$.token"]["actual"] == "[REDACTED]"
    assert "secret" not in json.dumps(differences)
    assert json_diff({"depositpaid": True}, {"depositpaid": True}) == []


# Retry evidence must correlate attempts and expose only allowed response headers.
def test_retry_and_refresh_events_correlate_attempts_and_exclude_sensitive_headers():
    """Run a mocked GET through three attempts and inspect request IDs, attempt numbers,
    scheduled delays, reasons, and headers.

    Type: Controlled retry reporting.

    Expected: One logical request spans attempts 1/2/3 with 0.25/0.5-second backoffs; safe
    headers remain while cookies and raw exception text are absent.

    Cases: ConnectTimeout, then 503, then 200.

    Scope: This scenario exercises retry evidence. Authentication-refresh event fields are
    verified by the separate refresh-event test.
    """
    collector = EvidenceCollector()
    reads = []
    def respond(request):
        if request.url.path == "/auth":
            return httpx.Response(200, json={"token": "secret"})
        reads.append(1)
        if len(reads) == 1:
            raise httpx.ConnectTimeout("raw secret message", request=request)
        return httpx.Response(503 if len(reads) == 2 else 200, json={"ok": True},
                              headers={"Retry-After": "1", "Set-Cookie": "hidden"})
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond),
                       observer=collector, sleeper=lambda _: None)
    try:
        assert api.request("GET", "/booking/1", headers={"Cookie": "hidden"}).status_code == 200
        events = collector.snapshot()
        attempts = [e for e in events if e["kind"] == "http"]
        retries = [e for e in events if e["kind"] == "retry_scheduled"]
        assert len({e["request_id"] for e in attempts}) == 1
        assert [e["attempt"] for e in attempts] == [1, 2, 3]
        assert [e["reason"] for e in retries] == ["ConnectTimeout", "HTTP 503"]
        assert [e["backoff_seconds"] for e in retries] == [0.25, 0.5]
        assert attempts[-1]["response_headers"] == {"retry-after": "1", "content-length": "11", "content-type": "application/json"}
        assert "hidden" not in json.dumps(events)
        assert "raw secret message" not in json.dumps(events)
    finally:
        api.close()


# Refresh evidence must record the rejection trigger while omitting issued tokens.
def test_auth_refresh_event_records_trigger_and_never_the_token():
    """Have the mocked endpoint reject the initial cookie and accept the replacement, then
    inspect the collected lifecycle events.

    Type: Controlled authentication reporting.

    Expected: The request succeeds and exactly one auth_refresh event records status 403;
    neither issued token appears in serialized evidence.

    Cases: One 403 followed by a successful refreshed PUT.
    """
    collector = EvidenceCollector()
    auth_calls = []
    def respond(request):
        if request.url.path == "/auth":
            auth_calls.append(1)
            return httpx.Response(200, json={"token": f"secret-{len(auth_calls)}"})
        return httpx.Response(403 if request.headers["Cookie"] == "token=secret-1" else 200)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), observer=collector)
    try:
        assert api.request("PUT", "/booking/1", authenticated=True).status_code == 200
        refresh = [e for e in collector.snapshot() if e["kind"] == "auth_refresh"]
        assert len(refresh) == 1 and refresh[0]["trigger_status"] == 403
        assert "secret-" not in json.dumps(collector.snapshot())
    finally:
        api.close()
