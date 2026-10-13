import json
from concurrent.futures import ThreadPoolExecutor

import httpx

from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.evidence import EvidenceCollector, sanitize


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
        assert collector.snapshot()[1]["response_body"]["totalprice"] == 123
        assert collector.snapshot()[0]["response_body"] == "[authentication body omitted]"
    finally:
        api.close()


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
