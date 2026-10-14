"""Controlled HTTP client behavior with MockTransport; no network calls."""

import httpx
from booker_qa.client import BookerClient
from booker_qa.config import Settings


# An explicitly unauthenticated request must return its negative response unchanged.
def test_negative_response_is_preserved_without_retry():
    """Send a PUT without authenticated=True through MockTransport and inspect the recorded
    request.

    Type: Controlled HTTP client contract.

    Expected: The caller receives 403 after one attempt and the default Accept header is
    application/json.

    Cases: One PUT returning 403.

    Scope: Automatic refresh applies only to requests explicitly marked authenticated; this
    case does not enter that path.
    """
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(403, text="Forbidden")
    client = BookerClient(Settings(), transport=httpx.MockTransport(respond))
    try:
        assert client.request("PUT", "/booking/1", json={"totalprice": 123}).status_code == 403
        assert len(calls) == 1
        assert calls[0].headers["Accept"] == "application/json"
    finally:
        client.close()
