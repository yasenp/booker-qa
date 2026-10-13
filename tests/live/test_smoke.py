import pytest


@pytest.mark.live
def test_api_health(api):
    assert api.request("GET", "/ping").status_code == 201
