# Requirements coverage and sandbox gaps

PASS describes actual verified behavior. Strict XFAIL captures a specific known
business violation; unrelated assertions and infrastructure failures remain FAIL.
UNSUPPORTED below means the API lacks the required concept, not a passing test.

| Assessment requirement | Evidence / test | Representation |
| --- | --- | --- |
| Dynamic reauthentication after 401/403 | Unit concurrent rejection tests; live invalid-token PUT | Implemented; one refresh then return final result |
| Concurrent token generation | Unit eight-thread single-flight; live four-thread setup | Implemented within each worker process |
| Token expiry / validity check | Controlled rejection responses; live invalid token | Real expiry TTL and introspection unsupported; invalidation is simulated |
| Duplicate date-range attempt, second context | Live duplicate test uses a separate HTTP client | PASS for observed acceptance; strict rejection XFAIL |
| Same room, second owner | No room or owner fields / account provisioning contract | UNSUPPORTED |
| Nested JSON, price type, deposit boolean, date format | Contract tests and live create validation | Implemented; YYYY-MM-DD matches API contract |
| Checkout greater than checkin | Generated data and invariant validator; live negative probe | Local invariant PASS; server rejection strict XFAIL |
| Price calculations | Integer/nonnegative invariant, PUT/PATCH persistence | Rate/tax calculation UNSUPPORTED; negative-price rejection XFAIL |
| Three identical PUTs | Original three-PUT test retained; additional repetition counts 2 and 5 | Observable state idempotency; responses checked as a separate contract |
| Concurrent identical PUT | Two/four synchronized writers submit the same payload | Observable state idempotency; excluded from conflicting-write conclusions |
| Repeated DELETE | Three deletions, GET 404 after each | Resource stays absent; identical status codes not required |
| Repeated set-value PATCH | Three totalprice assignments with full-state comparisons | Scoped to set-value PATCH; not a general PATCH guarantee |
| Resource-version escalation / hidden side effects | No exposed resource version, history, or side-effect API | UNSUPPORTED; version stability is additional to HTTP idempotency |
| PATCH field preservation | Full before/after comparison including nested dates | Implemented |
| Simultaneous conflicting updates | Two-thread barrier, three independent rounds | Implemented; actual client start skew reported |
| Collision reconciliation | Both PUT outcomes and final full-payload membership | Last-write-wins-compatible observation; final winner may vary |
| Exact same-millisecond server arrival | Network scheduling and server timestamps unavailable | UNSUPPORTED as a guarantee; barrier approximates concurrent release |
| Optimistic locking / deterministic winner | No documented version preconditions | UNSUPPORTED; deterministic integrity predicate instead |
| Dirty-state GET recovery | One prerequisite recreation; controlled exhaustion test | Implemented; recovery IDs recorded |
| Dirty-state DELETE handling | 404 accepted; 405 accepted only with confirming GET 404 | Implemented; no creation during teardown |
| Safe retry | Bounded read retries and pre-send connection retries | No ambiguous read/write retries for mutations |
| Lost response before/after commit | Eight method/failure-point combinations using a local model | Client behavior SIMULATED; live commit-boundary coverage unsupported |
| Idempotency-Key deduplication | No documented key semantics or authoritative operation-count endpoint | UNSUPPORTED; production prerequisites documented |

Known business-gap tests live in `tests/live/test_capabilities.py` and raise a
dedicated exception only after verifying the accepted booking matches the input.
`xfail(strict=True)` produces a failing XPASS if rejection starts working; update
the capability baseline deliberately when that happens.

No mock result is evidence that the live API enforces an enterprise business rule.

The measurable idempotency catalog has four supported live families/seven cases
and eight controlled response-loss cases. Actual executed/passed counts are generated
from Allure results by `scripts/report_coverage.py` and attached to the report.
See [scope and production extensions](idempotency-coverage.md). Conflicting writes
are integrity tests, not identical-request idempotency tests; hidden business effects
and server branch coverage are unmeasured.
