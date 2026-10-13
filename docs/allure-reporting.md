# Allure Report 3

The report generator is the project-local npm package `allure@3.20.1`.
The pytest adapter is `allure-pytest==2.16.2`; its version is independent of the
generator's major version. Node 24 is used locally and in GitHub Actions. Java
is not required. Python remains in the existing py3148 virtual environment.

## Install

```sh
source /Users/yzp/Documents/code3000/py3148/bin/activate
source "$HOME/.nvm/nvm.sh"
nvm use
python -m pip install -r requirements.lock.txt
python -m pip install --no-deps -e '.[test]'
npm ci --ignore-scripts
```

If Node is installed without nvm, ensure Node 24 or later is on PATH instead.

## Collect and generate

```sh
python -m pytest -n 2 --alluredir=reports/offline/allure-results --clean-alluredir --junitxml=reports/offline.xml
python scripts/report_coverage.py --mode offline
npm run report:offline

python -m pytest --live -n 2 --alluredir=reports/live/allure-results --clean-alluredir --junitxml=reports/live.xml
python scripts/report_coverage.py --mode live
npm run report:live
```

`--clean-alluredir` starts each invocation with fresh results; it does not delete
`reports/history/`, where Allure 3 history is stored. Offline and live
invocations have separate directories and must not run simultaneously into the
same directory. xdist workers within one invocation use UUID-named files.

Reports are single-file HTML:

- `reports/offline/html/index.html`
- `reports/live/html/index.html`

Open either file directly in a browser. To serve it through Allure instead:

```sh
npx --no-install allure open reports/live/html
```

Report generation is a separate command so pytest's exit status remains visible.
Do not combine test and report commands in a way that discards a failing test exit.

## Reading the report

Features group tests by authentication, validation, idempotency, PATCH integrity,
concurrency, recovery, and reporting integrity. Labels record assessment requirement
IDs and distinguish live evidence from controlled simulations. Fixture steps show
prerequisite creation and cleanup; lifecycle steps show update and verification.

Allure's adapter represents pytest XFAIL as **skipped**, with an XFAIL explanation.
The three known enterprise expectations are tagged **business-gap** and attach the
requirements coverage table. Ordinary offline skips say `Enable with --live`.
Strict XPASS remains **failed** and fails pytest. Assertion failures are failed;
unexpected exceptions and teardown exceptions are broken. These mappings are
verified through isolated adapter tests, not by changing actual test outcomes.

Unsupported concepts remain entries in the attached coverage table. They are not
invented passing tests. Invalid-token simulation is additionally tagged as simulated
expiry; it is not evidence of a real server token TTL.

## Evidence and redaction

The API client accepts an optional observer and has no dependency on Allure.
One thread-safe collector per fixture receives sanitized HTTP attempts. Attachments
are emitted by the owning test/fixture thread after all request threads finish.
Secondary duplicate clients share that test's collector.

HTTP evidence contains method, endpoint path, attempt count, elapsed milliseconds,
status/error class, and JSON request/response bodies. Authentication bodies are
omitted entirely. Authentication and arbitrary headers, query strings, non-JSON bodies, and exception
messages are omitted. Only Accept, Content-Type, Content-Length, Retry-After, ETag,
and Last-Modified headers are allowed. Sensitive structured keys are recursively redacted before storage.
Automatic stdout/stderr/log attachments are disabled with `--allure-no-capture`.

Concurrent reconciliation attaches both candidates, responses, release skew, and
the final state. Owned booking IDs and prerequisite replacements are attached in
teardown even if cleanup fails. Controller-only metadata records Python, OS,
execution mode, worker count, target host, git base commit, and pytest exit code.
The commit is explicitly marked as a working-tree run because changes may be uncommitted.

## CI

GitHub Actions installs Node 24 and dependencies from both lock files. It collects
Allure alongside JUnit, generates reports with `always()`, and uploads the entire
reports directory. Live execution remains a manual workflow input. A test failure
still fails the job even if report generation succeeds. Nothing is publicly published.

## Verified integration

- Offline final run: 42 passed, 16 live tests skipped.
- Live final run with two workers: 55 passed, 3 strict XFAIL.
- Status tests cover PASS, ordinary skip, XFAIL, strict XPASS, assertion failure,
  unexpected exception, and teardown failure using isolated subprocesses.
- Sanitization and concurrent collector checks pass.
- Result counts, unique test identities, attachment references, and generated
  report summaries are checked directly.
- Browser rendering was not visually inspected: browser connections and Computer
  Use permissions were unavailable in this session. GitHub CI has not run remotely.


## History retention

`allurerc.mjs` reads the shared JSON settings and selects a history file using
`ALLURE_RUN_MODE`, which the npm scripts set automatically:

- Live: `reports/history/live.jsonl`
- Offline: `reports/history/offline.jsonl`

`appendHistory: true` retains all existing entries; no pruning limit is set.
Clean only the raw `allure-results` directory for a fresh test run. Do not delete
`reports/history`. Generating a report appends a run, so avoid regenerating the
same results repeatedly if you want one history entry per execution.

The initial integration did not enable history. Existing saved live/offline results
were used to seed one entry each before the subsequent live rerun. Previous HTML
and raw results are additionally archived under `reports/archive/20261013T143028Z`.
Runs whose results were not saved cannot be reconstructed.

GitHub Actions restores history from a branch-specific cache, then saves it under a
new run/attempt key after report generation, including when tests fail. Reports and
history are also uploaded as artifacts. Remote cache behavior has not been exercised
from this local workspace. Concurrent CI jobs on the same branch can each restore
an earlier snapshot; this cache is not an atomic shared history database.


## Request, response, and verification evidence

Each HTTP attempt has a numbered step with setup/call/teardown phase, endpoint,
attempt number, outcome, and actual duration. Open its separate **Request** and
**Response** JSON attachments to view formatted payloads and allowed headers.
A request ID ties retry attempts together. Concurrent requests are displayed in
start-time order; threads only collect evidence and never call Allure directly.
Presentation steps are emitted after execution, so use their recorded `elapsed_ms`
for HTTP timing rather than the presentation step's own duration. The complete
collector trace remains available as **Sanitized HTTP attempts**.

Comparison attachments contain expected/actual values, match status, and differences
such as `$.bookingdates.checkout`. Differences distinguish additions, removals,
missing fields, null values, array elements, and JSON value types. Sensitive values
remain redacted even when differences are displayed.

- PUT: per-iteration response/persisted comparisons and an idempotency summary.
- PATCH: patch payload, before/after states, changed fields, and untouched-field check.
- Concurrency: both writer outcomes even if one fails, final state, matching candidate,
  per-candidate differences, and client release skew. Worker exceptions retain their
  original failure classification after outcomes are attached.
- Business gaps: expected rejection codes, actual response, and known-gap context.
- Retry: triggering HTTP status or error class, next attempt, and backoff duration.
- Authentication: token acquired and refresh-trigger events; token values are omitted.
- Recovery: original/replacement IDs and bounded-recovery exhaustion events.
- Cleanup: every owned ID's DELETE result, confirming GET status when needed, and outcome.

Comparisons are attached before assertions. HTTP evidence is collected at the client
boundary and rendered after the test call and again during teardown, so setup/call/
teardown failures still retain evidence. Isolated reporting tests verify all three
failure phases without injecting failures into the real sandbox suite.


## Idempotency evidence and scope labels

`scenario_type` distinguishes identical-request idempotency, conflicting-update
integrity, and response-loss simulation. The original three-PUT test keeps its
historical identity. Additional counts and worker counts are separate new cases.
Idempotency summaries include initial state, shared payload, response outcomes,
repetition count, snapshots/final state, and differences. Repeated DELETE records
all response codes and confirming GET 404 checks; equal DELETE statuses are not
required. Set-value PATCH summaries verify full-state stability across repetition.

`docs/idempotency-coverage.md` and the current mode's `reports/<mode>/coverage.json`
are global report attachments. Run the coverage script before generating the report;
it reports catalog numerators/denominators from actual results rather than targets.
The CI workflow performs that step automatically. Simulated commit counts remain
explicitly labeled as local-model evidence, never live database measurements.
