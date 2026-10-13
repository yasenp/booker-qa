"""Exercise the adapter on intentional failures outside the real suite/report."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("source,status,exit_code", [
    ("def test_probe(): pass", "passed", 0),
    ("@pytest.mark.skip(reason='ordinary skip')\ndef test_probe(): pass", "skipped", 0),
    ("@pytest.mark.xfail(strict=True, reason='known gap')\ndef test_probe(): assert False", "skipped", 0),
    ("@pytest.mark.xfail(strict=True, reason='known gap')\ndef test_probe(): pass", "failed", 1),
    ("def test_probe(): assert False", "failed", 1),
    ("def test_probe(): raise RuntimeError('transport simulation')", "broken", 1),
    ("@pytest.fixture\ndef resource():\n    yield\n    raise RuntimeError('cleanup failure')\ndef test_probe(resource): pass", "broken", 1),
])
def test_adapter_preserves_status_and_exit_code(tmp_path, source, status, exit_code):
    (tmp_path / "test_probe.py").write_text("import pytest\n" + source + "\n")
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "allure_pytest", "-q", "--alluredir=results", "--allure-no-capture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == exit_code, result.stdout + result.stderr
    reports = list((tmp_path / "results").glob("*-result.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report["status"] == status
    if "known gap" in source and "assert False" in source:
        assert "XFAIL" in report["statusDetails"]["message"]


@pytest.mark.parametrize("failure_phase", ["call", "setup", "teardown"])
def test_evidence_survives_real_fixture_failures(tmp_path, failure_phase):
    project = Path(__file__).parents[2]
    # Use the actual project fixtures/hooks with a deterministic mock HTTP boundary.
    conftest = (project / "tests/conftest.py").read_text()
    mock = '''
import httpx
from booker_qa.client import BookerClient as BaseClient

def respond(request):
    if request.url.path == "/auth":
        return httpx.Response(200, json={"token": "fixture-secret"})
    if request.method == "POST":
        return httpx.Response(SETUP_STATUS, json={"bookingid": 1, "booking": {"totalprice": 123}})
    if request.method == "DELETE":
        return httpx.Response(DELETE_STATUS)
    return httpx.Response(200, json={"totalprice": 123})

def BookerClient(settings, **kwargs):
    return BaseClient(settings, transport=httpx.MockTransport(respond), **kwargs)
'''.replace("SETUP_STATUS", "500" if failure_phase == "setup" else "200").replace(
        "DELETE_STATUS", "500" if failure_phase == "teardown" else "201")
    (tmp_path / "conftest.py").write_text(conftest + mock)
    source = '''from reporting import compare
def test_probe(api):
    response = api.request("GET", "/booking/1")
    differences = compare("Intentional mismatch", {"totalprice": 999}, response.json())
    assert not differences
''' if failure_phase == "call" else "def test_probe(registry):\n    registry.create()\n"
    (tmp_path / "test_probe.py").write_text(source)
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
           "PYTHONPATH": os.pathsep.join([str(project / "src"), str(project / "tests")])}
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "allure_pytest", "-q", "--alluredir=results", "--allure-no-capture"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    results = tmp_path / "results"
    report = json.loads(next(results.glob("*-result.json")).read_text())
    assert report["status"] == ("failed" if failure_phase == "call" else "broken")
    names = []
    def attachments(value):
        if isinstance(value, dict):
            for attachment in value.get("attachments", []):
                names.append(attachment["name"])
                assert (results / attachment["source"]).exists()
            for child in value.values():
                attachments(child)
        elif isinstance(value, list):
            for child in value:
                attachments(child)
    for path in results.glob("*.json"):
        attachments(json.loads(path.read_text()))
    assert "Request" in names and "Response" in names and "Sanitized HTTP attempts" in names
    if failure_phase == "call":
        assert "Intentional mismatch" in names
    else:
        assert "Booking ownership and prerequisite recovery" in names
    assert "fixture-secret" not in "".join(path.read_text() for path in results.iterdir())
