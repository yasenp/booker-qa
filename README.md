# Booker QA

Python API automation for the Space42 Senior QA assessment. Includes token
lifecycle management, contracts and business invariants, idempotency, PATCH drift,
concurrent conflicting updates, bounded recovery, and explicit sandbox gaps.

## Setup

```sh
source /Users/yzp/Documents/code3000/py3148/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e '.[test]'
```

Python 3.14 or later is required; validation used Python 3.14.8. Configuration uses
environment variables listed in `.env.example`, which is not automatically loaded.
Defaults use the API's public sandbox credentials. Credentials are excluded from
settings repr; tokens are not logged. Requests time out after 15 seconds by default.
`BOOKER_READ_ATTEMPTS` defaults to 3 and also bounds pre-send connection retries.

## Run

```sh
python -m pytest                          # offline; live tests skipped
python -m pytest --live                   # full sequential suite
python -m pytest --live -n 2               # two isolated workers
python -m pytest --live -m 'not business_gap'
python -m pytest --live --junitxml=reports/results.xml
```

All live tests create unique temporary bookings and clean up only their tracked
IDs. Read errors retry with bounded backoff; uncertain write outcomes fail without
replaying mutations. Connection establishment failures can retry before send.
A 401/403 triggers one token refresh and one protected-request replay.

## Expected outcomes

- PASS: verified live behavior or deterministic framework behavior.
- XFAIL: a dedicated known business-gap exception, with strict XPASS handling.
- FAIL/ERROR: assertions, transport exhaustion, contract violations, or cleanup failures.
- UNSUPPORTED: explicitly listed in the coverage document; never counted as PASS.

There are three strict business-gap tests: duplicate rejection, reversed-date
rejection, and negative-price rejection. Each has a separate sandbox characterization
check. Unexpected API errors cannot satisfy the expected-failure exception filter.

## Architecture

- `src/booker_qa/config.py`: environment configuration
- `src/booker_qa/client.py`: HTTP, safe retry boundaries, protected requests
- `src/booker_qa/auth/manager.py`: locked, generation-aware token management
- `src/booker_qa/bookings.py`: owned IDs, prerequisite recovery, cleanup
- `src/booker_qa/data.py`: unique names and calculated date ranges
- `src/booker_qa/schemas/booking.py`: JSON Schema plus business invariants
- `tests/unit/`: controlled authentication, transport, recovery, and schema failures
- `tests/live/`: lifecycle, capabilities, and three conflicting-write rounds

Threaded writers share a thread-safe httpx client and one auth manager. pytest-xdist
process workers have independent state. A barrier coordinates conflicting writes;
the final record must match one complete candidate, without partial merges. The
winning request can vary. JUnit properties record client release skew, winning
payload, owned booking IDs, and prerequisite recoveries.

Prerequisite GET 404 permits one recreation. Post-operation assertions do not
recreate records. Cleanup accepts DELETE 404; sandbox DELETE 405 is accepted only
when a confirming GET returns 404. Other cleanup failures remain visible.

## Review material

- [API discovery](docs/api-discovery.md)
- [Requirements coverage and unsupported capabilities](docs/requirements-coverage.md)
- [Technical walkthrough and limits](docs/technical-defense.md)
- [Validation results](docs/validation-results.md)
- [Allure Report 3 setup and evidence](docs/allure-reporting.md)

GitHub Actions runs offline tests on push/PR and offers manual live execution.
JUnit artifacts are retained even when a job fails. The workflow is supplied but
has not been executed on GitHub. Do not use AI during the assessment's live defense.

## Allure Report 3

Use Node 24 (`nvm use` reads `.nvmrc`) and install the report generator with
`npm ci --ignore-scripts`. The pinned pytest adapter is included in test dependencies.

```sh
python -m pytest --live -n 2 --alluredir=reports/live/allure-results --clean-alluredir --junitxml=reports/live.xml
npm run report:live
```

Open `reports/live/html/index.html` directly in a browser. For an offline report,
use `reports/offline/allure-results` and `npm run report:offline`.
Allure shows known XFAIL business gaps as skipped, with labels and explanations;
pytest still enforces strict XPASS. Reports contain sanitized API evidence,
concurrency reconciliation, cleanup/recovery details, and environment metadata.
See [the reporting guide](docs/allure-reporting.md) for installation and validation.

Allure history is retained separately in `reports/history/live.jsonl` and
`reports/history/offline.jsonl`. The npm report scripts append each run automatically;
`--clean-alluredir` only clears raw results. Keep the history directory between runs.
GitHub Actions restores/saves branch-specific history caches.
