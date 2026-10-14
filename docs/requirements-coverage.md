# Requirements coverage and sandbox gaps

PASS describes actual verified behavior. Application defects produce ordinary
assertion failures. Business-rule rejection checks also use ordinary assertions;
no live tests retain XFAIL handling. Infrastructure failures remain visible.
UNSUPPORTED below means the API lacks the required concept, not a passing test.

The [test case catalog](test-cases.md) links all 88 test functions (331 parameterized
cases) to their source and explains each scenario's type, expected behavior, and
limits. Counts describe collected cases; dated outcomes are in
[validation results](validation-results.md).

| Assessment requirement | Evidence / test | Representation |
| --- | --- | --- |
| Dynamic reauthentication after 401/403 | Unit concurrent rejection tests; live invalid-token PUT | Implemented; one refresh then return final result |
| Concurrent token generation | Unit eight-thread single-flight with a blocked issuer and bounded waits; live four-thread setup counts logical auth requests and successful issuance | Implemented within each worker process; pre-send retries retain one logical request ID |
| Token expiry / validity check | Controlled rejection responses; live invalid token; three real-token aging scenarios in test_auth_expiry.py | Actual expiry scenarios require a documented --token-ttl-seconds and expiry-enabled target; explicitly skipped without that contract, so hosted expiry is not claimed |
| Previous token after another client logs in | Two independent clients, same credentials, raw-cookie protected PUT checks | Direct assertion for the user-requested single-session revocation policy; fails when old token is accepted; not a time-based expiry test |
| Duplicate date-range attempt, second context | test_business_duplicate_rejection calculates dates and uses two HTTP clients with independent logins/token cookies; checks original state and any returned duplicate ID through GET | Direct 400/409 assertion; acceptance FAILS and rejection passes; same sandbox account, not distinct users |
| Same room, second owner | No room or owner fields / account provisioning contract | UNSUPPORTED |
| Nested JSON, price type, deposit boolean, date format | Strict integer/boolean schema, required nested dates, calendar format checks, successful response/GET invariants; negative POST/PUT/PATCH matrix | Implemented; YYYY-MM-DD matches API contract; type coercion and malformed calendar values are rejected by the assertions |
| Checkout greater than checkin | Generated data, common comparison invariant, and reversed/equal date cases for POST/PUT/PATCH | Direct negative assertions; acceptance FAILS without XFAIL |
| Price calculations | Nonnegative strict integer total; four client-derived totals across POST/PUT/PATCH/GET, plus negative-price/type probes | Client arithmetic and exact persistence verified; server rate/tax calculation UNSUPPORTED because no formula/inputs exist |
| Three identical PUTs | Original three-PUT test retained; additional repetition counts 2 and 5 | Observable state idempotency; responses checked as a separate contract |
| Concurrent identical PUT | Two/four synchronized writers submit the same payload | Observable state idempotency; excluded from conflicting-write conclusions |
| Repeated DELETE | Three deletions, GET 404 after each | Resource stays absent; identical status codes not required |
| Repeated set-value PATCH | Three totalprice assignments with full-state comparisons | Scoped to set-value PATCH; not a general PATCH guarantee |
| Resource-version escalation / hidden side effects | No exposed resource version, history, or side-effect API | UNSUPPORTED; version stability is additional to HTTP idempotency |
| PATCH field preservation | Full before/after comparison including nested dates | Implemented |
| Nested PATCH field preservation | test_lifecycle.py patches only bookingdates.checkin; verifies checkout and every other field in response and GET | API-003: direct preservation assertion fails on corruption |
| Date search boundaries/direction | test_filters.py uses unique guest-scoped before/equal/after thresholds | API-001/002: direct membership assertions fail on documentation mismatches |
| Invalid-input validation | test_validation.py checks invalid PATCH types and incomplete POST; test_filters.py checks malformed dates, with positive controls | API-004/005/006: direct client-error and state-preservation assertions |
| Missing-resource mutation status | test_lifecycle.py checks PUT/PATCH/DELETE after controlled deletion, each followed by GET 404 | API-007: direct status assertion fails on 405; resource-state DELETE idempotency still holds |
| Simultaneous conflicting updates | Two-thread barrier: three PUT rounds plus a conflicting totalprice PATCH scenario | Implemented; actual client start skew reported |
| Collision reconciliation | Both writes must return 200; three GETs must match the same complete candidate with strict types/invariants | Explicit overwrite-policy expectation; rejects partial merges, unchanged state, drift, and unexpected 409/412; per-writer response equality remains a separate contract assertion |
| Concurrent same-field PATCH | test_conflicting_patch_preserves_one_price_and_untouched_fields | Both responses succeed and reflect their submitted price; final full record matches either candidate, preserving untouched fields |
| Concurrent separate-field PATCH | test_concurrent_patch_preserves_both_independent_changes | Price and lastname changes both persist; each response may contain its own change alone or both; unrelated fields remain unchanged |
| Exact same-millisecond server arrival | Network scheduling and server timestamps unavailable | UNSUPPORTED as a guarantee; barrier approximates concurrent release |
| Ordered overwrite policy | test_ordered_conflicting_put_uses_last_completed_write, A_then_B / B_then_A | First response and confirming GET precede the second write; all three final GETs must equal the second payload |
| Optimistic locking | No documented version preconditions; tests send unconditional writes | UNVERIFIED; a 409/412 alone is not evidence of version-based conflict detection and fails the configured overwrite expectation |
| Predetermined winner during a true collision | Server commit order is not exposed | UNSUPPORTED as a guarantee; either writer may win but three observations must preserve that complete result |
| Direct final database state | No sandbox database/audit access | UNVERIFIED; reconciliation checks API-visible persisted state during a bounded observation window |
| Dirty-state GET recovery | test_missing_prerequisite_is_recreated: independent client deletes an owned ID; ensure recreates once; protected PUT and GET succeed on the replacement | Implemented; original/replacement IDs tracked and cleaned up; repeated missing state exhausts the bounded recovery visibly |
| Dirty-state DELETE handling | test_sandbox_cleanup_handles_external_purge plus controlled 404/405 cases | Missing cleanup records are successful absence; 405 requires GET 404; remaining IDs are attempted and cleanup never creates replacements |
| Safe retry | Bounded read retries and pre-send connection retries | No ambiguous read/write retries for mutations |
| Lost response before/after commit | Eight method/failure-point combinations using a local model | Client behavior SIMULATED; live commit-boundary coverage unsupported |
| Idempotency-Key deduplication | No documented key semantics or authoritative operation-count endpoint | UNSUPPORTED; production prerequisites documented |

Duplicate, reversed/equal-date, and negative-price rejection checks have no XFAIL
markers. Their passing acceptance characterizations and business-gap marker/hooks
have been removed so correct rejection passes normally. Date and price invariants
now live in `tests/live/test_validation.py`, parametrized across all three writes.
The duplicate scenario uses a cross-session workflow: calculate check-in as
today + 30 days and checkout as check-in + 3 days, create through context A, then
submit the identical payload through independently logged-in context B. Each
client sends its own token cookie. Reports record the dates, distinct-session
check, booking IDs, responses, and scope without token values. Original state
must remain unchanged and the response must be 400 or 409. A returned new ID is
registered before assertions; GET records whether a duplicate exists. A 400/409
response that identifies a still-accessible duplicate also fails. The API exposes
no authoritative operation count; this does not prove the absence of hidden effects.
The sandbox exposes one account and no room field, and POST does not enforce
booking ownership. These sessions therefore cannot establish different-user or
same-room overlap enforcement. No synthetic room field is added to the payload.
New-login revocation in `tests/live/test_auth_sessions.py` is an additional requested
policy with a normal assertion, not a requirement for time-based expiry or assessment reauthentication.

No mock result is evidence that the live API enforces an enterprise business rule.
Real-token aging tests use a genuine issued token and wall-clock waiting when enabled.
They check rejection without mutation, a fresh-token control, and sequential/concurrent
reauthentication. Controlled clock-model tests verify their assertions, including
nonexpiring tokens, server failures, unauthorized mutations, and failed recovery;
they do not establish expiration in the hosted deployment.
Application checks use normal assertions without expected-failure exceptions or
defect-specific response matching. API-001 through API-007 remain documentation
references in api-discovery.md. The ten cases live with their corresponding features
and are not counted as supported idempotency passes.

The measurable idempotency catalog has four supported live families/seven cases
and eight controlled response-loss cases. Actual executed/passed counts are generated
from Allure results by `scripts/report_coverage.py` and attached to the report.
See [scope and production extensions](idempotency-coverage.md). Conflicting writes
are integrity tests, not identical-request idempotency tests; hidden business effects
and server branch coverage are unmeasured.

The two additional PATCH concurrency scenarios live in `tests/live/test_lifecycle.py`
and report under REQ-4. Authentication completes before a bounded two-thread barrier.
Thread IDs, payloads, both responses, client release skew, and final GET state are
attached. Sixteen controlled cases run the actual assertions with both write orders
and injected lost updates, response/persisted corruption, invalid persisted types,
HTTP 500, and response loss. These controls verify defect detection; they do not
establish server-side scheduling or a guaranteed same-millisecond collision.

Shared reconciliation now records the expected write policy, actual statuses,
and three final GET snapshots before validating them. Conflicting PUT/PATCH expects
unconditional overwrite; separate-field PATCH expects both changes to survive.
All three snapshots must match the same complete valid candidate. The first GET
cannot be corrupt or stale and then silently replaced by a later successful read.
The ordered PUT control establishes a known winner in both directions without
pretending it is a simultaneous collision. Nineteen additional controlled cases
exercise either race winner, partial merges, missing dates, type drift, ignored
writes, unstable reads, HTTP 409/412/500, and both ordered overwrite directions.
Repeated GETs establish observed stability, not direct database consistency or
unbounded future stability. No winner is inferred from client response timing.

Shared sandbox hygiene is tested using only records created by the current test.
An independent HTTP client simulates an external actor with the sandbox account;
no global reset or unrelated-resource deletion is used. Prerequisite recovery
reuses a present record, recreates only after GET 404, updates the existing handle,
and allows one recreation per ensure call. Recovery exhaustion remains visible.
The live continuation check verifies a protected update and full persisted payload
after recovery. The cleanup check mixes absent and remaining IDs, then verifies
all are absent and that cleanup issued no booking-creation requests. Fixture
teardown repeats cleanup safely. DELETE 404 is directly covered by a controlled
transport; the live host returned 405, which required confirming GET 404.
Eight added controlled cases cover present-record reuse, non-404 errors/malformed
responses, terminal DELETE 404, unsuccessful absence confirmation, and continuing
cleanup after a transport error. Post-operation GET assertions remain strict:
an unexplained missing result cannot be attributed to another user without evidence,
and auto-recreating it would conceal a possible application data-loss defect.

## Implemented source-review scenarios

All application checks below assert the desired behavior directly. The public
sandbox's behavior may fail those assertions. Tests use only IDs created by their
own fixtures; independent concurrent clients each have their own booking.

| Scenario | Implementation | Cases / scope |
| --- | --- | --- |
| AUTH-01 Valid login | test_auth_sessions.py::test_valid_login_authorizes_booking_update | Token authorizes PUT; response and independent GET match |
| AUTH-02 Invalid credentials | test_auth_rejects_nonexistent_user and test_auth_rejects_invalid_credentials | Unknown user, wrong password, empty credentials, missing credentials |
| AUTH-03 Invalid tokens | test_protected_mutations_reject_bad_tokens | Missing/empty/unissued/modified token crossed with PUT/PATCH/DELETE; assert 403 and unchanged state |
| AUTH-04 Inherited-property bypass | test_inherited_property_tokens_are_rejected | toString/constructor/__proto__ crossed with PUT/PATCH/DELETE; direct rejection and state assertions |
| AUTH-05 Shared initial acquisition | Unit test_parallel_initial_acquisition_is_single_flight and live test_parallel_setup_acquires_one_live_token | Eight controlled callers/four live callers; one shared issuance |
| AUTH-06 Independent parallel logins | test_parallel_independent_logins_issue_usable_tokens | Four clients, four logical auth requests, four distinct usable tokens, four owned records |
| AUTH-07 Concurrent refresh | Unit test_concurrent_rejection_refreshes_once | 401/403; one shared refresh across four callers |
| AUTH-08 Persistent rejection | Unit test_persistent_forbidden_refresh_is_bounded | One refresh/replay, then return 403 |
| AUTH-09 New-login revocation | test_new_login_invalidates_previous_token | Requested single-session policy; direct assertion, automatic refresh disabled |
| AUTH-10 Actual expiry | test_real_token_expiry_and_reauthentication[reject-expired] | Requires documented absolute TTL; skipped without configuration |
| AUTH-11 Expiry recovery | test_real_token_expiry_and_reauthentication[refresh-sequential/refresh-concurrent] | Requires documented absolute TTL; one/four callers and one refresh |
| BOOK-01 Nested PATCH | test_lifecycle.py::test_nested_patch_preserves_checkout | Full response/GET preservation checks |
| BOOK-02 Invalid field types | test_validation.py::test_updates_reject_invalid_field_types, test_creates_reject_invalid_field_types, and test_patch_rejects_invalid_types_without_mutation | 15 scalar/date cases crossed with POST/PUT/PATCH, plus combined PATCH case |
| BOOK-03 Internal fields | test_patch_rejects_internal_fields | bookingid collision with another owned record; meta replacement; expect rejection and unchanged records |
| BOOK-04 Exact resource IDs | test_resource_ids_require_exact_integer | Text/fractional suffixes crossed with GET/PUT/PATCH/DELETE; no numeric-prefix access or mutation |
| BOOK-05 Date filters | test_filters.py inclusive check-in/checkout checks | Before/equal/after thresholds, unique guest filter controls |
| BOOK-06 Invalid requests | test_incomplete_post_returns_client_error and test_malformed_date_filter_returns_client_error | Incomplete POST and both malformed date filters, with positive controls |
| BOOK-07 Missing resources | test_lifecycle.py::test_missing_resource_mutation_reports_absence | PUT/PATCH/DELETE after owned deletion, then GET confirms absence |

AUTH-06 exercises the sandbox's multiple-session behavior. AUTH-09 is a separately
requested single-session policy and currently conflicts with that behavior; both
cannot be treated as guarantees of the same authentication policy. No claim of
time-based expiry is made when AUTH-10/11 are skipped.

The collision test adds only its second owned ID as an extra cleanup target.
Controlled regressions verify that both aliased records are deleted even if PATCH
returns an error after mutating the ID. Security-assertion regressions also verify
that HTTP 403 alone cannot hide a successful update or deletion. Token values and
authentication request/response bodies are excluded from reporting evidence.

## Deep schema and invariant validation — requirement 2

| Test | Scope |
| --- | --- |
| test_updates_reject_invalid_field_types | 30 PUT/PATCH cases: price string/bool/fraction/null, deposit string/number/null, malformed nested date object, invalid date/timestamp, and existing invalid-name check |
| test_creates_reject_invalid_field_types | The same 15 cases at creation; unique guest data prevents duplicate rejection from masking input validation |
| test_full_requests_require_both_dates | Four POST/PUT cases for missing checkin or checkout; a partial nested PATCH remains a preservation scenario |
| test_business_invalid_values_rejected | Nine cases: reversed dates, equal dates, and negative price across POST/PUT/PATCH |
| test_calculated_price_and_deposit_round_trip | Four complete POST/PUT/PATCH/GET workflows: calculate total from stay duration and a test rate, verify zero/positive totals, toggle both boolean values, preserve dates and total during flag-only PATCH |
| test_create_contract / test_patch_preserves_every_untouched_field / test_nested_patch_preserves_checkout | Existing full contract and scalar/nested preservation checks |
| Unit test_contract.py | Reject malformed representations even when expected/actual bodies match; valid leap-day/year-end dates, zero price, and both boolean values pass |
| Unit test_validation_assertions.py | 15 controlled cases verify status plus state and cleanup, including rejection responses that still create or mutate records |

Schema validation uses strict Python integer types, an explicit date format checker,
and the YYYY-MM-DD pattern. Booleans and floats, including 123.0, cannot satisfy
the integer constraint. Both nested dates are required on complete resources.
All successful booking comparisons enforce checkout strictly after checkin and
a nonnegative total, even if expected and actual values happen to be identical.
Comparison failures attach contract/invariant details and raise AssertionError.
Negative cases collect response and subsequent GET evidence before asserting;
returned creation IDs are registered before validation and cleaned up on failure.
No hidden operation count or server-side rate/tax calculation is claimed.
