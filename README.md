# Booker QA

RESTful Booker API automation for the Space42 Senior QA assessment.

**Python 3.14+ · pytest · httpx · pytest-xdist · Allure 3**

[Setup](#setup) · [Run](#run) · [Coverage](#coverage) · [Reports](#allure-report-3) · [Docs](#documentation)

## Setup

From the repository root on macOS/Linux:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e '.[test]'
```

<details>
<summary>Windows PowerShell setup</summary>

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e '.[test]'
```

</details>

Activate the existing `.venv` in later sessions. Defaults target the public sandbox;
export overrides from [.env.example](.env.example). `.env` files are not loaded automatically.

## Run

| Mode | Command | Target |
| --- | --- | --- |
| Offline | `python -m pytest` | Controlled checks; live cases skipped |
| Live | `python -m pytest --live` | Public sandbox |
| Live, two workers | `python -m pytest --live -n 2` | Public sandbox, isolated worker state |

Add `--junitxml=reports/results.xml` for JUnit output.

**Latest offline verification:** 196 passed, 135 live cases skipped.
[Dated results](docs/validation-results.md#portable-setup-and-evidence-labels--15-october-2026)

> **Live failures are expected while known defects remain.** Application defects and
> unmet policy checks fail normally; they are not marked XFAIL. See the
> [findings](docs/api-discovery.md) and [requirement mapping](docs/requirements-coverage.md).

## Coverage

| Area | Main checks |
| --- | --- |
| Authentication | Login/rejection, shared token acquisition, bounded refresh |
| Business rules | Strict schema, dates, price/deposit values, duplicate rejection |
| Updates | Repeated PUT/DELETE, set-value PATCH, untouched-field preservation |
| Concurrency | Conflicting PUT/PATCH, independent-field updates, stable GET snapshots |
| Sandbox hygiene | Owned-record cleanup, one recreation of a missing prerequisite |

[All 88 test functions / 331 collected cases](docs/test-cases.md) — each documents
its scenario, expected behavior, parameters, and limits. Offline evidence is
**controlled**; specific modeled server behavior is identified as **simulated**.

**Scope limits:** the sandbox exposes no room/owner model, server pricing formula,
resource versions, or database/side-effect audit. Exact server overlap is unverified.
Real token-expiry cases skip without a documented TTL and suitable target;
see [expiry setup](docs/technical-defense.md#real-token-expiry) and [coverage limits](docs/requirements-coverage.md).

## Allure Report 3

Requires **Node 24+**. With the Python environment active, on macOS/Linux:

```sh
npm ci --ignore-scripts
python -m pytest -n 2 --alluredir=reports/offline/allure-results --clean-alluredir
python scripts/report_coverage.py --mode offline
npm run report:offline
npx --no-install allure open --port 8080 reports/offline/html
```

Open [localhost:8080](http://localhost:8080). For a live report, add `--live` to pytest
and replace each `offline` above with `live`.

Reports include sanitized request/response payloads, field differences, concurrency
outcomes, and recovery/cleanup evidence. **Keep `reports/history/`** to preserve runs;
`--clean-alluredir` clears only raw results. [Full reporting guide](docs/allure-reporting.md)

## Project map

```text
src/booker_qa/   HTTP client, auth, booking ownership, data and schemas
tests/unit/     Controlled framework and reporting checks
tests/live/     Sandbox API scenarios
docs/           Detailed coverage, findings and design decisions
reports/        Generated JUnit, Allure results, HTML and history (gitignored)
```

[GitHub Actions configuration](.github/workflows/tests.yml): offline tests on
push/PR; live tests via manual input; reports uploaded even after failures.

## Documentation

| Need | Read |
| --- | --- |
| Scenarios and implementing files | [Scenario/file map](docs/test-scenarios.md) · [Detailed test catalog](docs/test-cases.md) |
| Assessment requirements | [Coverage and limits](docs/requirements-coverage.md) |
| Application findings and run outcomes | [API discovery](docs/api-discovery.md) · [Validation results](docs/validation-results.md) |
| Design and assessment walkthrough | [Technical guide](docs/technical-defense.md) · [Idempotency scope](docs/idempotency-coverage.md) |
| Reporting setup and history | [Allure guide](docs/allure-reporting.md) |
