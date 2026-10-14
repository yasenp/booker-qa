# Validation results — 13 October 2026

Runtime: `/Users/yzp/Documents/code3000/py3148/bin/python`, Python 3.14.8.

| Run | Outcome | Report |
| --- | --- | --- |
| Offline, two workers, final suite | 32 passed, 16 live tests skipped | reports/offline.xml |
| Live sequential checkpoint | 44 passed, 3 XFAIL | reports/sequential.xml |
| Live, two workers, final suite | 45 passed, 3 XFAIL | reports/parallel.xml |

The final parallel suite contains one additional live concurrent token-acquisition
check added after the sequential checkpoint. All final tests were executed in the
parallel run. Both live runs include three independent two-thread collision rounds.
JUnit properties include winner, release skew, owned IDs, and recovery replacements.
All tracked booking cleanup completed without errors in the successful runs.

Expected failures are duplicate rejection, reversed-date rejection, and negative
price rejection. Their separate characterization tests passed. Unsupported rooms,
user ownership, price formulas, resource versions, true token TTL, and exact server
arrival timing remain explicitly documented in requirements-coverage.md.

Initial runs exposed TLS connection timeouts and repeated DELETE returning 405.
Pre-send connection failures now retry within the configured limit. A DELETE 405
is accepted only after GET confirms 404. Controlled tests cover those paths, plus
ambiguous write outcomes that must never be retried. The reruns passed without
hiding initial infrastructure failures as expected business gaps.

`pip check` reports no broken dependencies; `git diff --check` passes. The editable
package was successfully installed into the specified environment. GitHub Actions
configuration is included but has not been run remotely. Generated XML reports are
ignored by git; this document records the reviewable validation snapshot.


## Allure 3 integration verification

Pinned Allure Report 3.20.1 and allure-pytest 2.16.2. Added ten reporting checks:
seven adapter outcome/exit-code scenarios and three evidence/redaction/threading
checks. Final offline run: 42 passed, 16 skipped. Final live two-worker run:
55 passed, 3 strict XFAIL. All tracked booking cleanup completed successfully.
Raw result identities and attachment references match the generated report counts.
HTML was generated but not visually inspected because this session lacks browser
connections and Computer Use permission. See allure-reporting.md for report commands.


## History-preserving rerun

The live suite reran with two workers: 55 passed, 3 strict XFAIL in 18.27 seconds.
Allure history was seeded from the previous saved results before clearing raw
results. After report generation, live.jsonl contains two runs with all 58 stable
test IDs shared between them; the previous history bytes remain unchanged.
The regenerated report identifies zero new tests. Offline history retains its
separate baseline. Previous raw results and HTML are archived under
reports/archive/20261013T143028Z. History retention is configured for future local
runs and branch-specific GitHub Actions caching; remote CI has not been run.


## Improved execution evidence

Added paired request/response steps, allowed headers, typed JSON field differences,
scenario comparisons, and explicit retry/authentication/recovery/cleanup events.
Six additional checks verify nested/type-sensitive/redacted differences, retry and
refresh evidence, and retained attachments across setup/call/teardown failures.

Full two-worker offline run: 48 passed, 16 live tests skipped. Full live run:
61 passed, 3 strict XFAIL in 16.71 seconds. Final targeted failure-phase evidence
checks also pass (3 passed). The live report contains 64 distinct test identities;
all attachment references resolve. Per-test HTTP booking IDs match each fixture's
owned cleanup IDs, with no cross-test evidence mixing. All 17 tracked cleanup
outcomes succeeded. Live trace records 83 HTTP attempts, 15 token-acquisition
events, one refresh, and one prerequisite recreation. No retries were needed in
this live run; controlled checks verify retry reasons, attempt correlation, and backoff.

History retained its exact previous bytes and appended one run per mode: three
live runs and two offline runs. Previous report/history snapshots are archived at
reports/archive/20261013T181819Z. Reports were regenerated and audited directly;
visual browser inspection was unavailable. Dependency and diff checks pass.


## Idempotency coverage expansion

Added bounded sequential PUT counts (2/5 alongside the existing three-PUT test),
concurrent identical PUTs with 2/4 writers, three repeated DELETEs with confirmed
absence, and three repeated set-value PATCHes. Conflicting payloads remain a
separate integrity category. Eight local-model response-loss cases verify before/
after simulated commit behavior without blindly replaying uncertain mutations.
A coverage-accounting check ensures skips and failures are never counted as passes.

Full live two-worker run: 76 passed, 3 strict XFAIL in 29.04 seconds. Offline:
57 passed, 22 live tests skipped. The supported idempotency catalog executed and
passed 7/7 cases across 4/4 families; controlled response-loss cases passed 8/8.
These are catalog counts, not percentages of all server behavior. Server branches,
operation counts, hidden effects, and live key-based deduplication are unmeasured
or unsupported. Actual counts are in reports/live/coverage.json.

All 23 owned-ID cleanup outcomes succeeded. Report identities are distinct (79),
all attachment references resolve, and scope labels distinguish identical requests
from conflicting-write integrity. Measured coverage JSON and scope documentation
are embedded as global attachments in both generated HTML reports.

History retained its prior bytes and appended one run per mode: four live runs and
three offline runs. All 64 identities from the previous run are preserved; 15 added
cases are reported as new. Previous report/history snapshots are archived under
reports/archive/20261013T191559Z. Dependency and diff checks pass. Remote CI and
visual browser rendering were not exercised in this session.


## Authentication session checks — 14 October 2026

Added unknown-user response validation: HTTP 200 with Bad credentials and no token.
Added separate-client same-credential login probes. Both original and newly issued
tokens authorize protected PUTs; a deliberately invalid token returns 403 and
leaves the booking unchanged. Probes use explicit token cookies without automatic
refresh. Earlier-token acceptance is a passing sandbox characterization and a
strict XFAIL for the requested single-session revocation policy, not proof of
time-based token expiration.

Initial auth-file run: 2 passed, 1 XFAIL. Final session checks with the added invalid-
token state check: 1 passed, 1 XFAIL, 1 unrelated auth test deselected, in 8.19 seconds.
Owned booking cleanup succeeded. Targeted Allure evidence is saved separately in
reports/auth-session-final/allure-results; the existing full-run histories were
not changed. Diff checks pass.


## Assessment review fixes — 14 October 2026

Renamed the new live authentication module to test_auth_sessions.py so it no longer
collides with tests/unit/test_auth.py during default pytest collection. Full runs
now use the documented commands without import-mode or Python-path workarounds.

Creation checks the POST status, response envelope, positive integer booking ID,
and nested booking contract. A valid ID remains registered when later validation
fails, preserving cleanup. Successful booking assertions validate wire types and
type-sensitive equality; negative business-rule probes keep their separate scope.

Added 21 controlled regressions: eight PUT/PATCH response/persistence type-drift
cases, four malformed-create/status cases with cleanup, five invalid IDs, and four
retry/refresh warning-redaction cases. The strengthened initial-acquisition test
holds issuance open while other callers contend, uses bounded waits, and rejected
a deliberately lock-free manager in 20/20 mutation checks. The live four-thread
test observed one logical auth request, one HTTP attempt, and one successful issuance.

Default sequential offline run: **78 passed, 25 skipped in 2.20 seconds**.
Default live two-worker run: **99 passed, 4 strict XFAIL in 32.51 seconds**.
All 103 cases collected. The four expected failures remain duplicate rejection,
reversed-date rejection, negative-price rejection, and the requested new-login
revocation policy. Supported idempotency cases passed 7/7 and controlled response-
loss cases passed 8/8. All 25 tracked cleanup outcomes reported deletion or
confirmed absence. All 675 live attachment references resolve.

Both Allure HTML reports were regenerated with current coverage attachments.
The exact existing history bytes were preserved and one run appended per mode:
live has five runs; offline has four. All 79 identities from each previous historical
run remain present; new authentication and regression cases bring the total to 103.
Previous raw results, HTML, and history are archived under
reports/archive/review-fixes-20261014T131928Z. Audit results are saved in
reports/review-fixes-validation.json. Diff checks pass. Remote GitHub Actions and
visual browser inspection were not exercised during this fix.


## Hosted API defect regressions — 14 October 2026

Historical checkpoint: the expected-failure classification described in this
section was subsequently replaced by direct assertions; see the next section.

A separate bounded discovery probe reproduced all seven source findings on the
hosted sandbox: inclusive check-in filtering, reversed checkout filtering, nested
PATCH checkout corruption, invalid PATCH type acceptance, incomplete POST returning
500, malformed date filters returning 500, and missing-resource mutations returning
405. The upstream source and hosted observations were checked separately; the
deployed commit is not known. Evidence and source links are in api-discovery.md.

Added ten live cases in tests/live/test_api_defects.py, including both malformed
date filters and all three missing-resource mutation methods. Nested PATCH checks
both its response and an independent GET while preserving the full expected booking.
Known defects have separate Allure labels and identifiers from business-policy gaps.
Only their reproduced signatures after successful controls raise the exception
allowed by strict XFAIL. Fixed behavior produces strict XPASS; other failures remain
visible. Ten controlled checks exercise this classification, including unrelated
corruption, missing records, transport errors, and unsuccessful positive controls.

Full offline two-worker run: **88 passed, 35 skipped in 2.32 seconds**.
Full live two-worker run: **109 passed, 14 strict XFAIL in 54.44 seconds**.
All 123 cases collected. Ten live expected failures represent the seven API defects;
four remain the existing business-policy gaps. These results detect hosted API
defects; they do not change that service's implementation. Supported idempotency
cases still passed 7/7 and controlled response-loss cases passed 8/8. The new defect
cases are separate from that scoped idempotency catalog.

All 36 tracked cleanup outcomes succeeded: 31 deleted and five confirmed absent.
All 991 live attachment references resolve. The parallel authentication check
recorded one logical auth request, one HTTP attempt, and one successful issuance.
Both reports include the current coverage JSON and scope documentation.

Allure history retains its exact prior bytes and adds one run per mode: six live
runs and five offline runs. All 103 previous test identities remain present;
20 new cases bring the total to 123. Previous results, HTML, and history are archived
under reports/archive/api-defects-20261014T134827Z. The report audit is saved in
reports/api-defects-validation.json, and the independent probe observations and
sanitized trace are in reports/hosted-findings/. Diff checks pass. Remote CI and
visual browser inspection were not exercised during this update.


## Direct application assertions — 14 October 2026

Moved the ten application checks into their feature modules and removed the
known-defect marker, exception, signature matching, and XFAIL decorators:

- tests/live/test_filters.py: check-in/checkout before/equal/after thresholds and
  invalid date filters (four cases).
- tests/live/test_validation.py: invalid PATCH types with unchanged-state checks,
  and incomplete POST validation (two cases).
- tests/live/test_lifecycle.py: nested PATCH preservation in response and GET, and
  missing-resource PUT/PATCH/DELETE status checks (four cases).

These tests now pass on correct behavior and fail on application defects. The four
previously agreed unsupported business-policy expectations retain their separate
strict XFAIL handling. The old defect-specific test modules were removed. Controlled
checks now live beside the lifecycle and filter assertion tests; correct nested
merges and client validation responses pass, while corruption and server errors fail.

Full offline two-worker run: **88 passed, 35 skipped in 1.94 seconds**, exit code 0.
Full live two-worker run: **10 failed, 109 passed, 4 XFAIL in 52.01 seconds**, exit code 1.
All ten failures are direct assertions exposing the seven reported defects. Allure
records them as failed, with request/response and expected/actual evidence. The four
business gaps are its only skipped live results. Idempotency catalog checks remain
7/7 passed, and controlled response-loss checks remain 8/8 passed.

All 36 owned-booking cleanup outcomes succeeded despite the failing assertions:
31 deletions and five confirmed absences. All 1,001 live attachment references resolve.
Both HTML reports were regenerated with coverage attachments, and all previous
history bytes remain unchanged. One run was added per mode: seven live runs and six
offline runs. Moving/reworking tests creates 20 new history identities; 103 remain
unchanged, and all earlier runs remain available with their original identities.

Previous reports and history are archived under
reports/archive/direct-assertions-20261014T135904Z. Audit results are in
reports/direct-assertions-validation.json. Diff checks pass. Remote CI and visual
browser inspection were not exercised during this update.


## Token expiry scenarios and direct revocation assertion — 14 October 2026

Added three live actual-aging scenarios: rejection of an unchanged issued token
after its configured absolute TTL, sequential recovery, and four-caller recovery
with one shared refresh. These scenarios use explicit token cookies for expiry
probes, assert unchanged booking state on rejection, and check a fresh-token
positive control before concluding that authentication is functioning. Report
evidence records configured lifetime, grace, minimum observed age, and request counts.

The target's documented lifetime is required through --token-ttl-seconds; a grace
option defaults to one second. Invalid/nonfinite lifetimes are rejected before
execution. No arbitrary public-sandbox TTL was invented. The inspected upstream
source has no time-based token expiry check, and no expiry-enabled target with a
defined lifetime was supplied. Consequently the three live cases explicitly skipped
before fixtures ran. **Actual hosted expiry remains unverified.**

The new-login revocation check now uses a normal assertion. Its earlier acceptance
characterization was removed, allowing a revoking implementation to pass. The live
check failed because the original token still authorized PUT with HTTP 200. This
demonstrates noncompliance with the requested single-session policy, which is not
documented as a public API guarantee; it does not establish a time-based TTL.

Thirteen controlled checks passed: six expiry/recovery combinations using a clock
model, five negative workflow conditions, and two revocation-policy outcomes.
They validate the test assertions and client behavior, not the hosted server's
expiry policy. Targeted authentication checks: 18 passed in 0.26 seconds.

Full offline two-worker run: **101 passed, 37 skipped in 3.07 seconds**.
Full live two-worker run: **121 passed, 11 failed, 3 skipped, 3 XFAIL in 64.49 seconds**.
The failures are the ten existing application checks plus the direct revocation
policy assertion. The three ordinary live skips are the unconfigured expiry cases;
the three XFAILs remain duplicate, reversed-date, and negative-price business gaps.
Supported idempotency cases passed 7/7 and controlled response-loss cases passed 8/8.

All 35 tracked booking cleanup outcomes succeeded: 30 deletions and five confirmed
absences. All 1,075 live attachment references resolve. Both reports were regenerated
with current coverage attachments. Prior history bytes remain unchanged, with one
new run per mode: eight live runs and seven offline runs. Of the previous 123 test
identities, 122 remain; one characterization was removed and 16 cases added. Previous
runs retain their original identities. Archives are under
reports/archive/token-lifecycle-20261014T142258Z, and the audit is in
reports/token-lifecycle-validation.json. Diff checks pass. Remote CI and visual
browser inspection were not exercised during this update.

## Source-review scenario execution — 14 October 2026

Implemented 48 additional live cases in the authentication and input-validation
modules, with short comments above each test. Coverage includes valid/invalid login,
ordinary invalid tokens, inherited-property token bypass, independent parallel
logins, invalid update types, internal-field updates, and strict resource IDs.
The AUTH-01–11 / BOOK-01–07 mapping is in requirements-coverage.md; existing tests
cover the remaining scenarios without duplicating them.

Seven new controlled checks validate the assertions and cleanup: unauthorized
mutations must fail even if the server reports 403, and both records must be removed
after a booking-ID collision, including when the mutation returns an error.
The focused controlled run passed all seven checks in 0.02 seconds.

Full offline two-worker run: **108 passed, 85 skipped in 2.73 seconds**, exit code 0.
Full public-sandbox two-worker run: **146 passed, 41 failed, 3 skipped, 3 XFAIL
in 159.57 seconds**, exit code 1. Both invocations collected 193 cases. All 41
failures are assertion failures; no setup/teardown errors or broken results occurred.

The 48 new live cases produced **18 passes and 30 failures**:

| New scenario family | Passed | Failed |
| --- | ---: | ---: |
| Valid login and protected update | 1 | 0 |
| Wrong, empty, and missing credentials | 3 | 0 |
| Missing, empty, unissued, and modified tokens | 12 | 0 |
| Inherited-property token rejection | 0 | 9 |
| Independent parallel logins | 1 | 0 |
| Invalid PUT/PATCH field types | 1 | 11 |
| Internal bookingid/meta fields | 0 | 2 |
| Malformed resource IDs | 0 | 8 |

The other 11 failures are the ten prior application checks and the requested
new-login revocation policy. Three actual-expiry scenarios skipped because the
public sandbox has no documented TTL configured. Three strict XFAILs remain the
duplicate, reversed-date, and negative-price business-policy gaps. The supported
idempotency catalog still passed 7/7; controlled response-loss cases passed 8/8.

The four independent clients recorded four distinct usable tokens, four logical
auth requests, and four successful issuances. Invalid-token rejection passed,
while all nine inherited-property token attempts bypassed authentication and
persisted a mutation or deletion. The internal-ID case exposed two records under
one ID; its extra cleanup registration deleted both. The meta case establishes
acceptance, not proof of hidden metadata persistence. See api-discovery.md for
the per-family hosted observations.

All 89 cleanup outcomes succeeded: 78 deletions and 11 confirmed absences. The
audit checked every returned creation ID and all 373 resource-specific requests
against the owning test's registered IDs. All 2,037 live attachment references
resolve. Both HTML reports include the current coverage JSON and scope document.

Allure history preserves its exact previous bytes and adds one run per mode:
nine live runs and eight offline runs. All 138 previous test identities remain;
48 live cases and seven controlled checks add 55 identities. Prior artifacts are
archived in reports/archive/source-scenarios-20261014T144109Z. The audit is saved
in reports/source-scenarios-validation.json. No service source was changed.
Remote CI and visual browser inspection were not exercised during this update.
