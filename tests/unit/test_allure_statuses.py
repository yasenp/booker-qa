"""Exercise the adapter on intentional failures outside the real suite/report."""
import json
import os
import subprocess
import sys

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
