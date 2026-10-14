import json
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.evidence import EvidenceCollector, json_diff, sanitize


# Retry and refresh warnings must omit URL credentials, query strings, and fragments.
@pytest.mark.parametrize("failure", ["connect", "503", "401", "403"])
def test_warning_logs_exclude_url_secrets(caplog, failure):
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


def test_auth_bodies_headers_and_query_secrets_never_enter_evidence():
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


# Concurrent event collection must lose no events and return an independent snapshot.
def test_collector_keeps_all_thread_events_and_snapshot_is_detached():
    collector = EvidenceCollector()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: collector({"index": index, "body": {"token": "secret"}}), range(100)))
    snapshot = collector.snapshot()
    assert sorted(event["index"] for event in snapshot) == list(range(100))
    snapshot[0]["body"]["token"] = "changed"
    assert collector.snapshot()[0]["body"]["token"] == "[REDACTED]"


def test_sanitizer_handles_case_and_nested_sequences():
    assert sanitize({"items": [{"Authorization": "secret", "Cookie": "secret"}]}) == {
        "items": [{"Authorization": "[REDACTED]", "Cookie": "[REDACTED]"}]}


def test_diffs_distinguish_nested_changes_types_missing_and_null_without_leaking_secrets():
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


def test_retry_and_refresh_events_correlate_attempts_and_exclude_sensitive_headers():
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


def test_auth_refresh_event_records_trigger_and_never_the_token():
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
