# Validation results — 13 October 2026

Runtime: Python 3.14.8 in a virtual environment. See [setup](../README.md#setup)
for commands that create a local environment in any checkout.

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

## Duplicate booking through a second login context — 14 October 2026

Both duplicate-booking tests now share the same workflow. The payload factory
calculates check-in as today + 30 days and checkout three days later. Context A
logs in and creates the booking; a separate HTTP client logs in independently
and submits the identical payload with its own token cookie. Both sessions use
the sandbox account. The API has no room identifier or distinct-user ownership,
so this does not claim same-room enforcement across different business users.

The workflow verifies that the original booking remains unchanged. When a duplicate
is accepted, it must have a separate ID and its response and independent GET must
match the original payload. Its ID is registered before response assertions to
preserve cleanup even if the response is malformed. Server errors, corrupted
original state, and invalid responses cannot count as the known business-policy XFAIL.

Focused controlled validation: **17 passed in 0.03 seconds** (six new cross-session
workflow cases and 11 existing contract cases). The new checks cover 400/409
rejection, accepted duplicates, server errors, malformed acceptance, rejection
that mutates the original, cookie separation, and calculated dates crossing year-end.

Targeted public-sandbox run: **1 passed, 1 XFAIL in 7.51 seconds**. Each scenario
recorded two successful independent logins with distinct tokens and identical
booking submissions. The sandbox returned HTTP 200 for both duplicate attempts,
so acceptance passed and the strict rejection-policy check remained XFAIL.
All four owned bookings were deleted; all 55 attachment references resolve.

The isolated report is reports/duplicate-context-20261014T193314Z/html/index.html;
its raw results and validation audit are beside it. The previous full-suite reports
and both history files remain unchanged. This targeted run does not replace the
last full-suite results above.

## Duplicate acceptance reported as a defect — 14 October 2026

Removed the duplicate-rejection business_gap/XFAIL markers and the passing
duplicate-acceptance characterization. The existing test identity remains
test_business_duplicate_rejection. It asserts HTTP 400/409 directly; HTTP 200,
HTTP 201, and server errors produce ordinary assertion failures. Error text
under HTTP 200 does not establish a documented alternative rejection contract.
The two remaining strict business-gap cases concern reversed dates and negative prices.

The test retains calculated dates, independently authenticated client sessions,
original-state verification, and sanitized response evidence. Returned duplicate
IDs are registered before assertions, and GET records the duplicate's persisted
state. Even 400/409 fails if the response identifies an accessible new booking.
Hidden effects without a returned ID remain unmeasured.

Focused controlled and reporting checks: **30 passed in 2.31 seconds**. Nine
cross-session cases cover ordinary 400/409 rejection, 200/201 acceptance, an
HTTP 200 error message, malformed acceptance, server errors, mutation of the
original on rejection, and a 409 that still creates a duplicate. The other
21 checks cover the schema/invariants and Allure status/evidence behavior.

Targeted public-sandbox run: **1 failed in 5.41 seconds**, pytest exit code 1.
The failure states: expected HTTP 400 or 409, got HTTP 200. Both independent
logins succeeded; the same payload created booking IDs 388 and 400. GET confirmed
the second booking was persisted and the original remained unchanged. Allure
records failed, and JUnit records one failure with zero errors and zero skips.
Both cleanup deletions succeeded, and all 26 attachment references resolve.

The report, raw results, JUnit output, and audit are under
reports/duplicate-rejection-20261014T194107Z. Previous full-suite reports and both
history files remain unchanged. The targeted report was generated with the base
Allure config to avoid adding a partial run to the full-suite histories. Diff
checks pass. Remote CI and visual browser inspection were not exercised.

## Deep schema contract and invariant validation — 15 October 2026

The schema now enforces strict integer representations: strings, booleans,
fractional values, and even integer-valued floats cannot satisfy totalprice's
integer type. Deposit flags remain genuine booleans, nested dates are required,
and the explicit calendar checker and YYYY-MM-DD pattern reject invalid dates
and timestamps. Every successful booking comparison now validates logical
invariants as well as exact values, so identical invalid expected/actual bodies
cannot conceal a negative total or checkout <= checkin. Comparison contract and
invariant violations attach details and raise AssertionError.

Expanded live checks in test_validation.py cover 45 invalid-field combinations
across POST/PUT/PATCH, four required-date POST/PUT cases, nine reversed/equal-date
and negative-price cases, and four valid price/deposit round-trip workflows.
Partial nested PATCH remains covered as an update-preservation requirement;
missing checkout in a partial date patch is not incorrectly treated as missing
data in a complete replacement. The former invalid-business-value acceptance
tests, XFAIL decorators, business-gap exception, marker, and report hooks were
removed. The duplicate rejection work from the preceding entries is retained.

Negative checks collect the response and subsequent GET evidence before asserting
the rejection code. They verify that the original booking is unchanged and any
returned creation ID does not identify a newly persisted record on rejection.
Unexpected created IDs are registered before assertions. Invalid POST probes
use a different generated guest name from their valid control, preventing a
future duplicate rule from masking a missing field validator.

The four valid workflows compute expected totalprice from stay duration times a
test nightly rate, check POST and GET, extend the stay and toggle the deposit via
PUT, then change only the deposit via PATCH and verify that total/date values are
preserved. Zero total and true/false flags are exercised. No nightly-rate/tax
inputs or server pricing formula exist in this API, so these are tests of client
calculation and exact API persistence, not evidence of server-side price arithmetic.

Initial focused controlled checks: **79 passed in 0.16 seconds**. Full offline
two-worker validation: **153 passed, 130 skipped in 2.59 seconds**, exit code 0.
All 283 cases collected. Controlled checks include leap-day and year-end dates,
matching-but-invalid payloads, strict numeric types, and 15 POST/PUT/PATCH models
where rejection can incorrectly create or mutate a resource. Cleanup succeeds
after those intentionally failing scenario assertions.

Focused public-sandbox two-worker run: **13 passed, 53 failed in 87.26 seconds**,
exit code 1. All 66 selected cases executed; there were no XFAILs, skips, setup/
teardown errors, or broken Allure results. The selected cases included the new
matrix plus existing create, scalar/nested PATCH, and combined invalid PATCH checks.

| Selected family | Passed | Failed |
| --- | ---: | ---: |
| Invalid PUT/PATCH field types | 5 | 25 |
| Invalid POST field types | 0 | 15 |
| Required nested dates in POST/PUT | 2 | 2 |
| Date order and nonnegative price across all writes | 0 | 9 |
| Calculated price/deposit round trips | 4 | 0 |
| Existing creation and scalar PATCH contract checks | 2 | 0 |
| Existing nested/invalid-type PATCH checks | 0 | 2 |

All 78 tracked cleanup deletions succeeded. The audit verified ownership of every
returned creation ID and all 277 resource-specific requests. All 1,416 live and
295 offline attachment references resolve. Request/response and persisted-state
examples are summarized in api-discovery.md.

Reports, raw results, JUnit files, and the validation audit are under
reports/deep-validation-20261014T200228Z (UTC directory timestamp; local date
15 October). Both isolated reports were generated with the base Allure config;
the previous full-suite reports and both history files remain unchanged. The
full live suite was not rerun; the 66 selected live results are scoped to this
requirement. Diff checks pass. Remote CI and visual browser inspection were not
exercised during this update.

## Additional concurrent PATCH scenarios — 15 October 2026

Added two live tests in test_lifecycle.py:

- test_conflicting_patch_preserves_one_price_and_untouched_fields: two synchronized
  threads submit different totalprice values. Both responses must succeed and reflect
  their own update; final GET must match one complete candidate, preserving every
  untouched field.
- test_concurrent_patch_preserves_both_independent_changes: two synchronized threads
  change totalprice and lastname separately. Both changes must survive in final GET.
  A response may contain its own change alone or both changes, so legitimate ordering
  does not cause a false failure. Every unrelated field remains unchanged.

Authentication completes before the barrier. Allure records both thread identities,
payloads, outcomes, final-state comparisons, and client release skew under REQ-4.
No exact server arrival or execution overlap is claimed. Infrastructure exceptions
remain visible and owned bookings are cleaned up by the existing registry fixture.

Sixteen controlled cases exercise both write orders and inject lost updates,
corrupted responses/persisted state, invalid persisted types, HTTP 500, and response
loss. Full offline validation: **169 passed, 132 skipped in 2.71 seconds** (301
collected), exit code 0. This includes all 16 new controlled cases.

Focused public-sandbox validation: **5 passed in 8.31 seconds**, exit code 0.
Both new PATCH scenarios and all three existing conflicting PUT rounds passed.
Client release skew was 0.244542 ms for conflicting PATCH and 0.263458 ms for
separate-field PATCH. Both use two distinct threads; neither asserts a timing
threshold that network or scheduler jitter could make flaky.

All five owned bookings were deleted successfully. The audit verified all 27
resource-specific requests targeted owned IDs and all 143 live / 424 offline
attachment references resolve. Reports, JUnit results, and validation.json are under
reports/concurrent-patch-20261014T202146Z. Reports use the base Allure config;
the nine-run live history and eight-run offline history remain byte-for-byte unchanged.
Only the five concurrency cases were rerun live; unrelated application findings
from the previous validation remain open.

## State reconciliation and overwrite policy — 15 October 2026

The three concurrent-write scenarios now share explicit policy and state checks.
Conflicting PUT/PATCH expects unconditional last-write-wins behavior: both writes
return HTTP 200 and the final state matches one complete candidate. Independent
PATCHes expect both changes to survive. Every case collects three GET snapshots
before asserting, requires HTTP 200 for each, and checks the same complete state
with strict types and business invariants on all three reads. Mixed fields, lost
updates, or later drift fail. Reports record policy, observed statuses, snapshots,
candidate membership, and differences. A 409/412 is reported as an unexpected
conflict rejection, not silently accepted as proof of optimistic locking.

Added test_ordered_conflicting_put_uses_last_completed_write with A_then_B and
B_then_A cases. The first response and a confirming GET complete before the
second request begins. All three final GETs must equal the second payload. These
are sequential overwrite-policy controls; the existing barrier tests remain the
concurrent collision evidence. Nineteen new controlled cases exercise both valid
race winners, partial merges, missing dates, invalid types, unchanged/missing
state, drift, HTTP 409/412/500, and ignored or unstable ordered writes.

Full offline run: **188 passed, 134 skipped in 2.61 seconds**, 322 collected,
exit code 0. Focused public-sandbox run: **7 passed in 13.41 seconds**, exit code 0.

| Family | Cases | Result |
| --- | ---: | --- |
| Conflicting concurrent PUT | 3 | Both writes accepted; one complete stable winner |
| Conflicting price PATCH | 1 | Both writes accepted; one stable price, untouched fields preserved |
| Independent-field PATCH | 1 | Both changes persisted in one stable complete record |
| Ordered A→B / B→A PUT controls | 2 | WinnerB / WinnerA respectively; all final reads matched |

All 21 reconciliation snapshots passed. All seven owned bookings were deleted,
and all 53 resource-specific requests targeted owned IDs. All 239 live and 478
offline attachment references resolve. Reports, JUnit, and validation.json are
under reports/state-reconciliation-20261014T202926Z. Base-config report generation
preserves both full-suite histories byte-for-byte (nine live, eight offline runs).

The observed behavior is consistent with last-write-wins and with the reviewed
source's unconditional update. Client start/response timing does not identify
concurrent server commit order. Either race winner is valid; the expected complete
state and its stability are checked deterministically. No version precondition
contract or direct database access is exposed. These tests verify API-visible
state during three reads, not direct database consistency or absence of later
drift. Unrelated live application findings were not rerun and remain open.

## Shared sandbox hygiene — 15 October 2026

Existing BookingRegistry behavior already limits prerequisite GET 404 recovery
to one recreation by default and treats DELETE 404 as successful cleanup. A
sandbox DELETE 405 is accepted only after GET confirms 404. The implementation
continues through every tracked ID and reports genuine cleanup failures.

Strengthened test_missing_prerequisite_is_recreated to use a separate HTTP client
for the controlled deletion, preserve original/replacement ownership, and execute
a protected PUT plus full-state GET after recreation. Its test identity remains
unchanged. Added test_sandbox_cleanup_handles_external_purge: create two owned
records, remove one through the independent client, clean up both, verify no
replacement POST occurred, and confirm both records remain absent. Fixture
teardown repeats cleanup successfully. The setup purge also accepts already-absent
records with a confirming GET, so an earlier external deletion is harmless.
Both clients use the sandbox account; this simulates external interference without
claiming different-user authorization or invoking a global reset.

Eight new controlled cases verify that present prerequisites are reused, recovery
does not reinterpret 403/500/timeouts/invalid JSON as absence, DELETE 404 needs no
recreation, failed 405 absence confirmation stays visible, and cleanup continues
after a DELETE response-loss error. Existing bounded-recreation and exhaustion
checks remain in place. Post-operation GET assertions are never auto-recreated,
because that could hide an application data-loss defect.

Full offline validation: **196 passed, 135 skipped in 2.56 seconds**, 331 collected,
exit code 0. Focused public-sandbox validation: **2 passed in 5.26 seconds**, exit
code 0, with zero skipped, XFAIL, failed, or broken live results.

The original prerequisite 3279 was replaced by 3292; both the subsequent PUT and
GET returned 200 and matched the updated full payload. The second test owned 3280
and 3282. All four IDs were deleted or confirmed absent. Six registry cleanup
attempts succeeded: two DELETE 201 results and four DELETE 405 results, each of
the latter confirmed by GET 404. Repeated fixture cleanup accounts for two of
those absence checks. Direct DELETE 404 behavior passed in the controlled suite.

The audit verified all 20 resource-specific requests targeted owned IDs and all
81 live / 478 offline attachment references resolve. Reports, JUnit, and
validation.json are under reports/sandbox-hygiene-20261014T203702Z. Base-config
Allure generation preserves both full-suite histories byte-for-byte (nine live,
eight offline runs). Only these two cases were rerun live; unrelated application
findings remain open.

## Test documentation and report descriptions — 15 October 2026

All 88 collected test functions now have a short purpose comment and a docstring
covering scenario, type, expected behavior, parameter cases, and material limits.
The [test case catalog](test-cases.md) links every function: 39 live functions
cover 135 cases and 49 controlled functions cover 196 cases. These are collection
counts; the catalog does not imply that live application checks currently pass.

Allure descriptions now use the dedented test docstrings, including when a case
is skipped before fixture setup. This replaces the generic descriptions selected
by test-name patterns. Test names, parameter IDs, assertions, API fixture behavior,
and test logic are unchanged. An AST comparison verified that the only changes inside the
22 test modules are comments and docstrings; the shared hook changes only report
descriptions.

Full offline verification: **196 passed, 135 skipped in 3.00 seconds**, exit code 0.
All 331 collected node IDs and Allure history IDs match the previous suite. All
331 result descriptions match their test docstrings, all 88 catalog source links
and case counts are correct, and all 478 attachment references resolve.

Results, JUnit, the generated Allure HTML, and validation.json are under
`reports/test-documentation-20261014T205107Z/`. Isolated report generation preserved
both full-suite histories byte-for-byte: nine live and eight offline runs.
The public sandbox was not rerun for this documentation change; previous live
findings and coverage limits remain unchanged.

## Portable setup and evidence labels — 15 October 2026

README and Allure installation instructions now create a checkout-local `.venv`
using `python3.14 -m venv .venv`, with shell activation and a Windows PowerShell
alternative. Personal interpreter paths have been removed from the documentation.
Creation and activation passed in a temporary directory using Python 3.14.8;
dependency installation and Windows activation were not rerun.

All offline results now use `evidence_type=controlled`, covering actual schema
validation, real Allure subprocess integration, and tests with modeled server
behavior. Simulation descriptions remain scoped to those models. Commit-boundary
attachments separately identify `server_behavior=simulated` while retaining the
broad controlled evidence type.

Full offline run in the existing environment: **196 passed, 135 skipped in 2.71
seconds**, exit code 0. All 196 offline labels are controlled, including 32 contract
cases and 10 Allure integration cases. All eight modeled commit-failure attachments
retain their explicit simulation field. The 135 skipped live cases retain the
live label, without counting as executed live evidence.

All 331 test history IDs and descriptions, 88 catalog source links, and 478
attachment references were verified. Results, JUnit, generated HTML, and the audit
are under `reports/review-portability-20261014T212412Z/`. Full-suite history bytes
remain unchanged (nine live and eight offline runs). The sandbox was not rerun.
