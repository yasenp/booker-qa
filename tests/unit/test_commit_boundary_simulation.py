"""Controlled response loss: client behavior, not live server transaction evidence."""
from copy import deepcopy

import httpx
import pytest

from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.evidence import EvidenceCollector
from reporting import attach_json, render_events


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("committed", [False, True], ids=["before-commit", "after-commit"])
def test_lost_response_reports_uncertainty_without_replaying_mutation(method, committed):
    collector = EvidenceCollector()
    collector.phase = "call"
    initial = {"totalprice": 123, "firstname": "Original"}
    payload = {"totalprice": 999, "firstname": "Updated"}
    state = {"resource": deepcopy(initial), "created": [], "committed_operations": 0}
    sent = []
    def respond(request):
        sent.append(request.method)
        if committed:
            if method == "POST":
                state["created"].append(deepcopy(payload))
            elif method == "DELETE":
                state["resource"] = None
            elif method == "PATCH":
                state["resource"].update(payload)
            else:
                state["resource"] = deepcopy(payload)
            state["committed_operations"] += 1
        raise httpx.ReadTimeout("simulated lost response", request=request)
    api = BookerClient(Settings(), transport=httpx.MockTransport(respond), observer=collector,
                       sleeper=lambda _: pytest.fail("Mutation must not be retried"))
    try:
        with pytest.raises(httpx.ReadTimeout):
            api.request(method, "/booking" if method == "POST" else "/booking/1",
                        json=payload if method != "DELETE" else None)
    finally:
        attach_json("Controlled lost-response scenario", {
            "evidence_type": "simulation", "failure_point": "after commit" if committed else "before commit",
            "method": method, "initial_state": initial, "payload": payload,
            "sent_requests": sent, "simulated_authoritative_state": state,
            "client_outcome": "uncertain; exception propagated; no mutation replay",
            "live_commit_boundary_coverage": "unsupported",
        })
        render_events(collector.snapshot())
        api.close()
    assert sent == [method]
    assert state["committed_operations"] == int(committed)
    if not committed:
        assert state["resource"] == initial and state["created"] == []
    elif method == "POST":
        assert state["created"] == [payload]
    else:
        assert state["resource"] == (None if method == "DELETE" else payload)
