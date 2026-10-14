# Requirements coverage and sandbox gaps

PASS describes actual verified behavior. Application defects produce ordinary
assertion failures. Strict XFAIL is reserved for the previously agreed unsupported
business-policy expectations; infrastructure failures remain visible.
UNSUPPORTED below means the API lacks the required concept, not a passing test.

| Assessment requirement | Evidence / test | Representation |
| --- | --- | --- |
| Dynamic reauthentication after 401/403 | Unit concurrent rejection tests; live invalid-token PUT | Implemented; one refresh then return final result |
| Concurrent token generation | Unit eight-thread single-flight with a blocked issuer and bounded waits; live four-thread setup counts logical auth requests and successful issuance | Implemented within each worker process; pre-send retries retain one logical request ID |
| Token expiry / validity check | Controlled rejection responses; live invalid token; three real-token aging scenarios in test_auth_expiry.py | Actual expiry scenarios require a documented --token-ttl-seconds and expiry-enabled target; explicitly skipped without that contract, so hosted expiry is not claimed |
| Previous token after another client logs in | Two independent clients, same credentials, raw-cookie protected PUT checks | Direct assertion for the user-requested single-session revocation policy; fails when old token is accepted; not a time-based expiry test |
| Duplicate date-range attempt, second context | Live duplicate test uses a separate HTTP client | PASS for observed acceptance; strict rejection XFAIL |
| Same room, second owner | No room or owner fields / account provisioning contract | UNSUPPORTED |
| Nested JSON, price type, deposit boolean, date format | POST envelope/ID validation, successful booking response and GET schemas, type-sensitive comparisons, controlled type-drift regressions | Implemented; YYYY-MM-DD matches API contract; business invariants checked separately |
| Checkout greater than checkin | Generated data and invariant validator; live negative probe | Local invariant PASS; server rejection strict XFAIL |
| Price calculations | Integer/nonnegative invariant, PUT/PATCH persistence | Rate/tax calculation UNSUPPORTED; negative-price rejection XFAIL |
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
| Simultaneous conflicting updates | Two-thread barrier, three independent rounds | Implemented; actual client start skew reported |
| Collision reconciliation | Both PUT outcomes and type-sensitive final full-payload membership | Final winner may vary; per-writer response equality is a separate sandbox response-contract assumption |
| Exact same-millisecond server arrival | Network scheduling and server timestamps unavailable | UNSUPPORTED as a guarantee; barrier approximates concurrent release |
| Optimistic locking / deterministic winner | No documented version preconditions | UNSUPPORTED; deterministic integrity predicate instead |
| Dirty-state GET recovery | One prerequisite recreation; controlled exhaustion test | Implemented; recovery IDs recorded |
| Dirty-state DELETE handling | 404 accepted; 405 accepted only with confirming GET 404 | Implemented; no creation during teardown |
| Safe retry | Bounded read retries and pre-send connection retries | No ambiguous read/write retries for mutations |
| Lost response before/after commit | Eight method/failure-point combinations using a local model | Client behavior SIMULATED; live commit-boundary coverage unsupported |
| Idempotency-Key deduplication | No documented key semantics or authoritative operation-count endpoint | UNSUPPORTED; production prerequisites documented |

Known business-gap tests live in `tests/live/test_capabilities.py`. They raise
dedicated exceptions only after verifying the specific unsupported behavior.
New-login revocation in `tests/live/test_auth_sessions.py` is an additional requested
policy with a normal assertion, not a requirement for time-based expiry or assessment reauthentication.
`xfail(strict=True)` produces a failing XPASS if rejection starts working; update
the capability baseline deliberately when that happens.

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
| BOOK-02 Invalid field types | test_validation.py::test_updates_reject_invalid_field_types and test_patch_rejects_invalid_types_without_mutation | Six invalid scalar/date cases crossed with PUT/PATCH, plus existing combined PATCH case |
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
