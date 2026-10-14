import json
import math
import platform
import subprocess
from inspect import getdoc
from urllib.parse import urlsplit
from pathlib import Path

import allure
import pytest
from booker_qa.evidence import EvidenceCollector
from reporting import assert_booking_matches, attach_json, render_events
from booker_qa.bookings import BookingRegistry
from booker_qa.client import BookerClient
from booker_qa.config import Settings
from booker_qa.schemas.booking import validate_invariants


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Enable public sandbox tests")
    parser.addoption("--token-ttl-seconds", type=float, default=None,
                     help="Documented absolute server token lifetime; enables real expiry tests")
    parser.addoption("--token-expiry-grace-seconds", type=float, default=1.0,
                     help="Additional wait after the configured token lifetime (default: 1 second)")


def pytest_configure(config):
    ttl = config.getoption("--token-ttl-seconds")
    grace = config.getoption("--token-expiry-grace-seconds")
    if ttl is not None and (not math.isfinite(ttl) or ttl <= 0):
        raise pytest.UsageError("--token-ttl-seconds must be finite and greater than zero")
    if not math.isfinite(grace) or grace < 0:
        raise pytest.UsageError("--token-expiry-grace-seconds must be finite and nonnegative")
    if ttl is not None and not config.getoption("--live"):
        raise pytest.UsageError("--token-ttl-seconds requires --live")


def pytest_collection_modifyitems(config, items):
    for item in items:
        # Collection-time descriptions also reach cases skipped before fixture setup.
        description = getdoc(item.obj)
        if description:
            item.add_marker(allure.description(description))
        feature, requirement = feature_for(item)
        live = "live" in item.keywords
        if "test_idempotency" in str(item.path) or "put_three" in item.name:
            item.add_marker(allure.label("scenario_type", "identical-request-idempotency"))
            item.add_marker(allure.label("observability", "API-visible booking state"))
        elif "ordered_conflicting" in item.name:
            item.add_marker(allure.label("scenario_type", "ordered-overwrite-control"))
        elif "conflicting" in item.name:
            item.add_marker(allure.label("scenario_type", "conflicting-update-integrity"))
        elif "concurrent_patch" in item.name:
            item.add_marker(allure.label("scenario_type", "concurrent-partial-update-integrity"))
        elif "commit_boundary_simulation" in str(item.path):
            item.add_marker(allure.label("scenario_type", "response-loss-simulation"))
        elif "requires_token_ttl" in item.keywords:
            item.add_marker(allure.label("scenario_type", "real-token-expiry"))
        for name, value in [("epic", "Space42 API Assessment"), ("feature", feature),
                            ("requirement", requirement), ("parentSuite", "Live API" if live else "Controlled tests"),
                            ("suite", feature), ("evidence_type", "live" if live else "controlled"),
                            ("tag", "behavior-verification")]:
            item.add_marker(allure.label(name, value))
    if not config.getoption("--live"):
        for item in items:
            if "live" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Enable with --live"))
    elif config.getoption("--token-ttl-seconds") is None:
        for item in items:
            if "requires_token_ttl" in item.keywords:
                item.add_marker(pytest.mark.skip(
                    reason="Real expiry not executed: provide the target's documented --token-ttl-seconds; sandbox TTL is undefined"))


@pytest.fixture
def token_lifetime(request):
    return (request.config.getoption("--token-ttl-seconds"),
            request.config.getoption("--token-expiry-grace-seconds"))


@pytest.fixture(scope="session")
def settings():
    return Settings.from_env()


@pytest.fixture
def api(settings, request):
    collector = EvidenceCollector()
    state = {"collector": collector, "cursor": 0}
    request.node._http_evidence = state
    client = BookerClient(settings, observer=collector)
    try:
        yield client
    finally:
        try:
            events = collector.snapshot()
            if events:
                with allure.step("Remaining HTTP and lifecycle evidence (including teardown)"):
                    state["cursor"] = render_events(events, state["cursor"])
                attach_json("Sanitized HTTP attempts", sorted(events, key=lambda event: event.get("timestamp_ns", 0)))
        finally:
            client.close()


@pytest.fixture
def independent_api(api, settings):
    """A separate sandbox session sharing only the owning test's sanitized evidence."""
    client = BookerClient(settings, observer=api.observer)
    try:
        yield client
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
        handle, body = registry.create()
        assert_booking_matches("Created POST booking", handle.payload, body)
        validate_invariants(body)
        actual = registry.ensure(handle)
        assert_booking_matches("Available booking prerequisite", handle.payload, actual)
        validate_invariants(actual)
    return handle



def feature_for(item):
    name = item.originalname or item.name
    if "test_idempotency" in str(item.path):
        return "Idempotency", "REQ-3"
    if "commit_boundary_simulation" in str(item.path):
        return "Safe Retry", "REQ-3"
    if any(name in str(item.path) for name in ["test_evidence", "test_allure", "test_coverage_reporting"]):
        return "Reporting Integrity", "FRAMEWORK-REPORTING"
    if "auth" in str(item.path) or "token" in name:
        return "Authentication", "REQ-1"
    if "conflicting" in name or "concurrent_patch" in name:
        return "Concurrency", "REQ-4"
    if "missing_resource_mutation" in name:
        return "HTTP Error Semantics", "REQ-5"
    if "test_filters" in str(item.path):
        return "Booking Search", "REQ-2"
    if "test_validation" in str(item.path):
        return "Input Validation", "REQ-2"
    if "patch" in name:
        return "PATCH Integrity", "REQ-3"
    if "put_three" in name:
        return "Idempotency", "REQ-3"
    if "resilience" in str(item.path) or "prerequisite" in name or "health" in name or "sandbox_cleanup" in name:
        return "Recovery and Isolation", "REQ-5"
    return "Validation and Sandbox Capabilities", "REQ-2"


@pytest.fixture(autouse=True)
def report_context(request):
    """Set readable report titles and tags; descriptions come from test docstrings."""
    name = (request.node.originalname or request.node.name).removeprefix("test_").replace("_", " ").capitalize()
    allure.dynamic.title(name + (" [" + request.node.name.split("[", 1)[1] if "[" in request.node.name else ""))
    if "invalid_token" in request.node.name:
        allure.dynamic.tag("simulated-expiry")

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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    state = getattr(item, "_http_evidence", None)
    if state:
        state["collector"].phase = "call"
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    state = getattr(item, "_http_evidence", None)
    if state:
        state["collector"].phase = "teardown"
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    yield
    state = getattr(item, "_http_evidence", None)
    if call.when == "call" and state:
        with allure.step("Recorded request → response evidence (actual timings attached)"):
            state["cursor"] = render_events(state["collector"].snapshot(), state["cursor"])
