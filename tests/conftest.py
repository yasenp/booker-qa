import json
import platform
import subprocess
from urllib.parse import urlsplit
from pathlib import Path

import allure
import pytest
from booker_qa.evidence import EvidenceCollector
from booker_qa.bookings import BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Enable public sandbox tests")


def pytest_collection_modifyitems(config, items):
    for item in items:
        feature, requirement = feature_for(item)
        live = "live" in item.keywords
        gap = "business_gap" in item.keywords
        for name, value in [("epic", "Space42 API Assessment"), ("feature", feature),
                            ("requirement", requirement), ("parentSuite", "Live API" if live else "Controlled tests"),
                            ("suite", feature), ("evidence_type", "live" if live else "simulated"),
                            ("tag", "business-gap" if gap else "behavior-verification")]:
            item.add_marker(allure.label(name, value))
    if not config.getoption("--live"):
        for item in items:
            if "live" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Enable with --live"))


@pytest.fixture(scope="session")
def settings():
    return Settings.from_env()


@pytest.fixture
def api(settings):
    collector = EvidenceCollector()
    client = BookerClient(settings, observer=collector)
    try:
        yield client
    finally:
        try:
            events = collector.snapshot()
            if events:
                allure.attach(json.dumps(events, indent=2), "Sanitized HTTP attempts", allure.attachment_type.JSON)
        finally:
            client.close()


@pytest.fixture
def registry(api, record_property):
    registry = BookingRegistry(api)
    try:
        yield registry
    finally:
        record_property("owned_booking_ids", str(registry.ids))
        record_property("prerequisite_recoveries", str(registry.recoveries))
        try:
            with allure.step("Clean up every owned booking; confirm absence when needed"):
                registry.cleanup()
        finally:
            allure.attach(json.dumps({"owned_ids": registry.ids, "recoveries": registry.recoveries}, indent=2),
                          "Booking ownership and prerequisite recovery", allure.attachment_type.JSON)


@pytest.fixture
def booking(registry):
    with allure.step("Create unique booking prerequisite and verify availability"):
        handle, _ = registry.create()
        registry.ensure(handle)
    return handle



def feature_for(item):
    name = item.originalname or item.name
    if "test_evidence" in str(item.path) or "test_allure" in str(item.path):
        return "Reporting Integrity", "FRAMEWORK-REPORTING"
    if "auth" in str(item.path) or "token" in name:
        return "Authentication", "REQ-1"
    if "conflicting" in name:
        return "Concurrency", "REQ-4"
    if "patch" in name:
        return "PATCH Integrity", "REQ-3"
    if "put_three" in name:
        return "Idempotency", "REQ-3"
    if "resilience" in str(item.path) or "prerequisite" in name or "health" in name:
        return "Recovery and Isolation", "REQ-5"
    return "Validation and Sandbox Capabilities", "REQ-2"


@pytest.fixture(autouse=True)
def report_context(request):
    name = (request.node.originalname or request.node.name).removeprefix("test_").replace("_", " ").capitalize()
    allure.dynamic.title(name + (" [" + request.node.name.split("[", 1)[1] if "[" in request.node.name else ""))
    if "invalid_token" in request.node.name:
        allure.dynamic.tag("simulated-expiry")
        allure.dynamic.description("Live protected request with a deliberately invalid token simulates expiry. "
                                   "This does not prove a real server-side token expiration time.")
    if "business_gap" in request.node.keywords:
        allure.dynamic.description("Strict enterprise expectation. A known sandbox acceptance is XFAIL, "
                                   "which Allure displays as skipped. Infrastructure failures remain failures. "
                                   "An unexpected pass fails pytest and requires capability-baseline review.")
        coverage = Path(__file__).parents[1] / "docs" / "requirements-coverage.md"
        allure.attach(coverage.read_text(), "Unsupported capabilities and requirement coverage", allure.attachment_type.TEXT)


def pytest_sessionfinish(session, exitstatus):
    # Only the controller writes run metadata; workers share UUID-named result files.
    if hasattr(session.config, "workerinput"):
        return
    directory = session.config.getoption("allure_report_dir", default=None)
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        workers = session.config.getoption("numprocesses", default=0) or 1
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        hostname = urlsplit(Settings.from_env().base_url).hostname or "unknown"
        (target / "environment.properties").write_text(
            f"Python={platform.python_version()}\nOS={platform.system()}\n"
            f"Execution={'live' if session.config.getoption('live') else 'offline'}\nWorkers={workers}\n"
            f"Pytest.exit_code={int(exitstatus)}\nTarget.host={hostname}\nGit.commit={commit} (working tree)\n"
        )
