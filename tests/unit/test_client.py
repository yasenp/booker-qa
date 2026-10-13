import httpx
from booker_qa.client import BookerClient
from booker_qa.config import Settings


def test_negative_response_is_preserved_without_retry():
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
