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
python -m pytest --live --junitxml=reports/results.xml
```

All live tests create unique temporary bookings and clean up only their tracked
IDs. Read errors retry with bounded backoff; uncertain write outcomes fail without
replaying mutations. Connection establishment failures can retry before send.
A 401/403 triggers one token refresh and one protected-request replay.

## Expected outcomes

- PASS: verified live behavior or deterministic framework behavior.
- SKIP: live execution disabled, or real token expiry has no documented TTL configured.
- FAIL/ERROR: assertions, transport exhaustion, contract violations, or cleanup failures.
- UNSUPPORTED: explicitly listed in the coverage document; never counted as PASS.

All live application and business-rule checks use normal assertions. Duplicate
acceptance, reversed/equal dates, and negative prices fail when the required
validation is absent. The previous XFAIL handling and acceptance characterizations
have been removed. New-login revocation is an additional requested policy with a
normal assertion, separate from the assessment's reauthentication simulation.

Duplicate date-range rejection is a normal assertion in
`test_capabilities.py::test_business_duplicate_rejection`: the second independently
logged-in client must receive HTTP 400 or 409, and the original booking must remain
unchanged. HTTP 200/201 acceptance fails pytest and appears as **failed** in Allure.
A returned duplicate ID is tracked for cleanup and checked through GET, including
when a rejection response also identifies a created record. The previous passing
duplicate-acceptance characterization has been removed. Dates are calculated as
today + 30 days, with checkout three days later. Both sessions use the sandbox
account; the API has no room identifier or distinct-user booking ownership.

Seven source-backed API defects have also been reproduced on the hosted sandbox.
The original ten live regression cases cover date filters, nested PATCH preservation, invalid
PATCH types, invalid-input HTTP errors, and missing-resource status codes. They live
in the filter, validation, and lifecycle modules and assert the intended behavior
directly. Application defects fail these tests; corrected behavior passes normally.
The full live suite therefore fails while these defects remain in the application.
See [the discovery evidence](docs/api-discovery.md).

```sh
python -m pytest tests/live/test_filters.py tests/live/test_validation.py tests/live/test_lifecycle.py --live
```

Source-review scenarios additionally cover missing/invalid credentials and tokens,
inherited-property token bypass, four independent simultaneous logins, invalid
PUT/PATCH field types, internal identifier/metadata protection, and strict resource
ID parsing. All checks use ordinary assertions and only test-created booking IDs.
The identifier-collision case registers the owned destination ID twice before the
mutation so both records can be cleaned up if the API accepts the forbidden change.
The AUTH-01 through AUTH-11 and BOOK-01 through BOOK-07 mapping is in
[requirements coverage](docs/requirements-coverage.md).

Deep validation in `test_validation.py` covers POST, PUT, and PATCH with invalid
integer prices, boolean flags, nested objects, and calendar/date formats. POST and
PUT require both dates; partial nested PATCH is checked separately for preservation.
Successful response/GET comparisons also enforce `checkout > checkin` and a
nonnegative integer total. Zero price and both boolean values are valid controls.
Four complete write/read workflows calculate `stay nights * test nightly rate`
and verify that the API preserves the expected total and deposit flag. This checks
client-calculated test data and persistence: the API exposes no rate/tax inputs
or server pricing formula. The supported wire date format is `YYYY-MM-DD`, not
a timestamp. Malformed calendar dates and timestamps fail strict validation.

## Architecture

- `src/booker_qa/config.py`: environment configuration
- `src/booker_qa/client.py`: HTTP, safe retry boundaries, protected requests
- `src/booker_qa/auth/manager.py`: locked, generation-aware token management
- `src/booker_qa/bookings.py`: owned IDs, prerequisite recovery, cleanup
- `src/booker_qa/data.py`: unique names and calculated date ranges
- `src/booker_qa/schemas/booking.py`: JSON Schema plus business invariants
- `tests/unit/`: controlled authentication, transport, recovery, and schema failures
- `tests/live/`: authentication, lifecycle, search filters, input validation, idempotency, and sandbox capabilities

Threaded writers share a thread-safe httpx client and one auth manager. pytest-xdist
process workers have independent state. A barrier coordinates conflicting writes;
conflicting PUTs and same-field PATCHes must leave one complete candidate without
corrupting other fields. Separate-field PATCHes must preserve both changes, detecting
lost updates. The winning conflicting request can vary. JUnit properties record
client release skew, winning payload, owned booking IDs, and prerequisite recoveries.
The new PATCH scenarios also record distinct thread IDs and both outcomes in Allure;
client release timing does not establish exact server arrival or execution overlap.
All three concurrent-write scenarios reconcile three subsequent GETs and require
the same complete state on every read. Reports record the expected policy and both
write statuses; unexpected 409/412 responses fail. Ordered A→B and B→A PUT controls
verify that the second write wins when order is known, consistent with the sandbox's
last-write-wins behavior. Concurrent commit order, direct database state, and
optimistic locking remain unverified; no version precondition contract is exposed.

Creation validates the POST status, envelope, positive integer ID, and nested
booking before returning the handle. IDs are registered before response validation
so malformed responses can still be cleaned up. Successful booking comparisons
enforce schema and type-sensitive equality: `true` and `1` are different values.
Business invariants remain separate from wire validation for negative scenarios.

The conflicting-write test separately asserts the sandbox response contract:
each successful PUT returns its submitted booking. Final-state integrity allows
either complete candidate to win. A backend that returns another writer's latest
record needs a different response-contract assertion, even if its final state is valid.

Prerequisite GET 404 permits one recreation. Post-operation assertions do not
recreate records. Cleanup accepts DELETE 404; sandbox DELETE 405 is accepted only
when a confirming GET returns 404. Other cleanup failures remain visible.
Live hygiene tests use an independent HTTP client to remove an owned prerequisite,
verify that recreation permits a successful PUT/GET, and clean up a mixture of
already-absent and remaining records. Cleanup never creates replacements and
continues through all tracked IDs. Recovery/cleanup evidence includes original
and replacement IDs, response statuses, and confirmed absence.

## Review material

- [Every test: scenario, type, expected behavior, parameters, and limits](docs/test-cases.md)
- [API discovery](docs/api-discovery.md)
- [Requirements coverage and unsupported capabilities](docs/requirements-coverage.md)
- [Idempotency catalog and production extensions](docs/idempotency-coverage.md)
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
Allure shows application and business-rule assertion failures as failed. Current
live tests have no XFAIL classification. Reports contain numbered request/response steps with sanitized payloads and headers,
field-level expected/actual differences, PUT/PATCH summaries, concurrency reconciliation,
retry/authentication events, cleanup/recovery details, and environment metadata.
See [the reporting guide](docs/allure-reporting.md) for installation and validation.

Allure history is retained separately in `reports/history/live.jsonl` and
`reports/history/offline.jsonl`. The npm report scripts append each run automatically;
`--clean-alluredir` only clears raw results. Keep the history directory between runs.
GitHub Actions restores/saves branch-specific history caches.

## Idempotency scope

Live tests cover sequential identical PUTs (2/3/5), concurrent identical PUTs
(2/4 writers), repeated DELETE, and repeated set-value PATCH. These verify
observable booking state. Conflicting updates are a separate integrity scenario.
Resource versions, hidden effects, key-based POST deduplication, and live server
commit boundaries are not claimed. Eight controlled response-loss simulations
verify that uncertain mutation outcomes are reported without blind replay.

Generate measured catalog coverage after collecting each run:

```sh
python scripts/report_coverage.py --mode live
npm run report:live
```

Use `--mode offline` for offline results. Allure includes this measured JSON and
the scope document as global attachments. Coverage reports executed and passed
cases separately; collected skips do not count as execution. Existing test history
identities are retained, and additional cases appear as new tests.


## Token validity after another login

`tests/live/test_auth_sessions.py` uses two independent clients with the same credentials.
It verifies the first token, logs in on the second client, verifies the new token,
and probes the original token through a protected PUT. Explicit token cookies
bypass automatic reauthentication so revocation cannot be hidden by a refresh.
An invalid-token control must return 403 and leave the booking unchanged.

The requested single-session policy now asserts that the earlier token is rejected.
The sandbox's continued acceptance therefore produces an ordinary failure. This is
an explicit user-requested policy check; the API does not document session revocation.
The previous acceptance-characterization test was removed so a corrected implementation
can pass the policy test. New-login revocation is distinct from time-based expiration.

```sh
python -m pytest tests/live/test_auth_sessions.py --live
```

## Actual token lifetime

`tests/live/test_auth_expiry.py` adds three live scenarios: expired-token rejection,
sequential recovery, and four-caller recovery with one shared refresh. They retain
an unchanged server-issued token, prove it works initially, wait past the configured
absolute TTL plus grace, then assert 401/403 without automatic refresh and unchanged
booking state. A fresh-token positive control checks that authentication still works.

Supply the target's documented absolute lifetime; the option does not change server
behavior. Configure `BOOKER_BASE_URL` and credentials for that expiry-enabled target,
then use its actual TTL, for example through a shell variable:

```sh
python -m pytest tests/live/test_auth_expiry.py --live \
  --token-ttl-seconds "$TARGET_TOKEN_TTL_SECONDS" --token-expiry-grace-seconds 1
```

The public sandbox's inspected upstream source stores tokens without a time-based
expiry check. No TTL is assumed for it: these three cases skip explicitly when the
option is absent. A skipped case does not verify expiry. The TTL must be long enough
to complete the initial authenticated control. Controlled clock-model tests validate
the test logic separately; they are not hosted expiry evidence. The actual hosted
expiry limitation remains until a suitable target and its lifetime are supplied.
