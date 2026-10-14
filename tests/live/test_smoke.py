"""Live health-endpoint smoke check using the configured API client."""

import pytest


# The sandbox health endpoint must return its documented healthy status.
@pytest.mark.live
def test_api_health(api):
    """Call the public health endpoint through the configured HTTP client.

    Type: Live smoke.

    Expected: The final response status is 201.

    Cases: GET /ping.

    Scope: This is a reachability/health check; it does not exercise booking CRUD or
    authentication.
    """
    assert api.request("GET", "/ping").status_code == 201
