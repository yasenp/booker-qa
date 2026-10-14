# API discovery — 13 October 2026

## Repository and runtime

The repository initially contained only a placeholder README, .gitignore, and
the assessment PDF. No applicable AGENTS.md was found in the workspace or its
ancestor directories. The provided virtual environment runs Python 3.14.8.

## Contract sources

- Official generated documentation: https://restful-booker.herokuapp.com/apidoc/index.html
- Documentation data: https://restful-booker.herokuapp.com/apidoc/api_data.js
- Upstream project: https://github.com/mwinteringham/restful-booker

The booking contract includes firstname, lastname, totalprice, depositpaid,
bookingdates.checkin, bookingdates.checkout, and optional additionalneeds.
Dates use YYYY-MM-DD, not full timestamps. The documented contract has no room
ID, user ownership, price calculation inputs, resource version, or token expiry
metadata. PUT, PATCH, and DELETE accept a token cookie or Basic authentication.

## Observed public sandbox behavior

One bounded discovery run used a unique guest marker and four temporary records.
All four records were deleted successfully with HTTP 201. No existing public
bookings were modified. These are observations, not guarantees across deployments.

| Probe | Observed result |
| --- | --- |
| Valid POST /auth | 200 with a token; token omitted from output |
| Create booking | 200 with bookingid and booking |
| Exact duplicate from a separate HTTP client | 200, distinct booking ID |
| Checkout before checkin | 200; invalid ordering retained |
| Negative totalprice | 200; negative value retained |
| PUT with invalid token | 403 |
| Three identical PUTs | 200 each; subsequent state matched payload apart from later PATCH |
| PATCH totalprice only | 200; subsequent GET retained all other fields |
| GET nonexistent ID | 404 |
| DELETE each temporary booking | 201 |

The duplicate probe used a distinct client context, not a distinct authenticated
user: booking creation is unauthenticated and no second account was provisioned.
Concurrent updates, real token expiry, and missing-record DELETE were not probed
in initial discovery. Subsequent implementation runs cover concurrent updates and
confirm that repeated DELETE can return 405; cleanup verifies absence with GET.

## Decisions to discuss before the remaining implementation

1. Initial discovery recorded duplicate acceptance as sandbox behavior. The current
   requirement asserts rejection directly: duplicate acceptance is reported as a
   failing assessment check. Same-room ownership remains untestable without room
   inventory semantics.
2. Validate date ordering and nonnegative price as client-side business invariants;
   expose the sandbox's acceptance of invalid values separately. Do not silently
   pass a test claiming server-side rejection.
3. Validate totalprice types and persistence; a calculated-price assertion needs
   a specified rate/tax model absent from this contract.
4. For concurrent updates, require a final complete candidate payload. The winner
   may vary; deterministic winner selection requires server concurrency controls.
5. Test auth expiry and refresh with controlled responses in addition to live
   invalid-token checks. The documentation supplies no validity-check endpoint.

## Framework scope and verification

Added pytest, httpx, JSON Schema tooling, and pytest-xdist; dependencies are pinned
in pyproject.toml and the resolved environment is captured in requirements.lock.txt.
The resolver selected jsonschema 4.17.3 in this Python environment. Future contract
work must explicitly enable format checking and separately enforce date ordering.

Configuration, a thin HTTP client, client fixtures, an offline transport check,
and an opt-in health test formed the initial step 1–2 checkpoint. The subsequent
implementation adds authentication management, booking fixtures, schemas, retries,
and lifecycle/concurrency scenarios; see requirements-coverage.md and validation-results.md.

## Source findings verified on the hosted sandbox — 14 October 2026

A separate live discovery probe completed against https://restful-booker.herokuapp.com.
It created four temporary bookings and cleaned up every tracked ID. Filters were
scoped to the generated guest name; mutations touched only this probe's IDs.
Observations and sanitized HTTP evidence are in reports/hosted-findings/.

| ID | Finding | Hosted observation | Basis |
| --- | --- | --- | --- |
| API-001 | Check-in inclusive boundary excluded | A 2027-03-10 check-in appeared for threshold 2027-03-09, but not 2027-03-10 or 2027-03-11 | Documented inclusive comparison disagrees with `$gt` |
| API-002 | Checkout filter direction reversed | A 2027-03-15 checkout was excluded for threshold 2027-03-14 and included for 2027-03-16 | Documentation says on/after; query uses `$lt` |
| API-003 | Nested PATCH corrupts untouched checkout | Updating check-in alone returned checkout `0NaN-aN-aN`; an independent GET showed the same corruption | Shallow object assignment replaces bookingdates; parser formats the missing date |
| API-004 | PATCH accepts invalid field types | Strings `abc` and `false` produced HTTP 200; response and GET showed totalprice null and depositpaid true | PATCH bypasses validation; response parser coerces values |
| API-005 | Incomplete POST produces server error | POST containing only firstname returned HTTP 500 | Route maps validation failure to 500 |
| API-006 | Malformed date filter produces server error | Both checkin=not-a-date and checkout=not-a-date returned HTTP 500 | Date conversion is unchecked; live response hides the internal exception |
| API-007 | Missing-resource mutations report wrong method status | PUT, PATCH, and repeated DELETE each returned 405 after deleting an owned booking; GET remained 404 | These routes exist; absence is reported as Method Not Allowed |

Source references: [filter documentation and routes](https://github.com/mwinteringham/restful-booker/blob/main/routes/index.js#L45),
[POST validation](https://github.com/mwinteringham/restful-booker/blob/main/routes/index.js#L290),
[PATCH and DELETE handlers](https://github.com/mwinteringham/restful-booker/blob/main/routes/index.js#L545),
[update implementation](https://github.com/mwinteringham/restful-booker/blob/main/models/booking.js#L34),
and [response coercion](https://github.com/mwinteringham/restful-booker/blob/main/helpers/parser.js#L17).
The upstream main branch was inspected separately; no deployed revision identity
is assumed. Public observations establish the hosted behavior listed above.

The checkout equality case happened to include the booking in this deployment,
despite the strict source operator; date-only stored strings and ISO query strings
also affect comparison. Regression coverage proves the reversed direction using
thresholds on both sides, without assuming equality is excluded there.

Ten live regression cases cover these seven findings in tests/live/test_filters.py,
tests/live/test_validation.py, and tests/live/test_lifecycle.py. They assert the
intended contract directly: application defects fail, and corrected behavior passes.
The earlier known_defect marker, dedicated exception, and XFAIL response-signature
matching have been removed. Positive controls and cleanup still run around invalid
input checks. Validation requires a client error (400 or 422); a server error fails.

Nested PATCH verifies both the mutation response and an independent GET against a
deeply preserved expected booking. Corruption, missing records, transport
errors, and server failures remain visible. Negative PATCH
validation must leave the full booking unchanged if rejection starts working.

Duplicate acceptance is now reported as a normal failure against the requested
negative-validation rule. The absence of a room inventory or owner model remains
an explicit limit on the scope of that check. API-007 concerns HTTP status semantics: repeated DELETE
still satisfies observable-state idempotency when subsequent GET confirms absence.

## Token lifetime and session policy — 14 October 2026

The inspected upstream [authentication route](https://github.com/mwinteringham/restful-booker/blob/main/routes/index.js#L641)
adds each generated token to globalLogins with the value true. The
[protected PUT route](https://github.com/mwinteringham/restful-booker/blob/main/routes/index.js#L422)
checks that map entry, with no issue timestamp or age comparison. A new login adds
an entry without removing earlier tokens. This describes the inspected source;
the hosted deployment revision is not established.

The existing live probe confirms acceptance of both tokens after a second login.
Its policy test now asserts rejection directly, rather than expecting failure.
Three new actual-aging scenarios require an expiry-enabled target and its documented
absolute TTL. They do not assign an arbitrary expiry time to this public sandbox.
Without that configuration they explicitly skip before creating a booking; expiry
remains unverified. A finite observation window cannot establish that a token never
expires, and a local clock-model test cannot establish the hosted server's policy.

## Source-review scenarios executed on the public sandbox — 14 October 2026

The 48 new live scenarios ran against restful-booker.herokuapp.com: **18 passed
and 30 failed**. These are direct assertions, without XFAIL for application defects.
The local source checkout at commit 0046115 informed the scenarios; its identity
is not assumed to match the hosted deployment. The following observations come
from the hosted run's request/response and subsequent GET evidence.

| Scenario | Hosted observation | Result |
| --- | --- | --- |
| AUTH-01/02 Valid and invalid credentials | A valid token authorized a persisted PUT; wrong password, empty credentials, and missing credentials returned Bad credentials without a token | Four new cases passed; the existing unknown-user case also passed |
| AUTH-03 Invalid tokens | Missing, empty, unissued, and modified tokens returned 403 for PUT/PATCH/DELETE and left each booking unchanged | 12 passed |
| AUTH-04 Authentication bypass | Cookies containing toString, constructor, or __proto__ authorized protected mutations without an issued token: PUT/PATCH returned 200 and persisted the update; DELETE returned 201 followed by GET 404 | Nine failed; authentication bypass confirmed |
| AUTH-06 Independent concurrent logins | Four clients made four logical auth requests and received four distinct tokens; each updated and read back its own booking | One passed |
| BOOK-02 Invalid scalar/date types | Invalid price, boolean, check-in, and checkout values were accepted by PUT and PATCH. Null bookingdates in PATCH returned 200 with a non-JSON response, also observed on GET. Numeric firstname returned 500 for PUT and was persisted by PATCH. PUT with null bookingdates returned 400 and preserved state | One passed, 11 failed |
| BOOK-03 Internal booking ID | PATCH assigned the first booking the second owned booking's ID, returned 405, and made the original ID return 404. The second ID exposed the first booking's payload; cleanup deleted two records under that ID | One failed; resource identity corruption confirmed |
| BOOK-03 Internal metadata | PATCH containing meta returned 200 with unchanged public booking fields | One failed against the explicit rejection expectation; hidden metadata persistence is not observable through this API |
| BOOK-04 Malformed resource ID | Both a text suffix and fractional suffix resolved to the numeric prefix. GET/PUT/PATCH returned 200; DELETE returned 201 and removed the corresponding booking | Eight failed |

These failures assert rejection of invalid or internal inputs and preservation of
state. Acceptance of meta alone is weaker evidence than the observed booking-ID
corruption; the suite does not infer a hidden database change from that response.
The authorization cases use raw cookies, so automatic reauthentication cannot
mask rejection or supply a legitimate token during the attempt.

Every resource-specific request was checked against that test's owned IDs, including
the numeric prefixes and collision target. All 89 recorded cleanup outcomes
succeeded: 78 deletions and 11 confirmed absences. The new-login revocation policy
still failed separately because the old token remained usable. Actual time-based
expiry remains unverified: the three aging scenarios skipped without a documented TTL.

See reports/live/html/index.html for the report and
reports/source-scenarios-validation.json for the artifact/ownership audit.

## Duplicate rejection defect — assessment requirement 2

The duplicate-date-range requirement now uses a direct assertion. Its earlier
XFAIL classification and passing duplicate-acceptance test have been removed.
No special HTTP 200 error response is documented for this negative check; the
accepted rejection statuses are 400 and 409. An error-looking message under
HTTP 200 does not satisfy that status contract.

Reproduction on 14 October 2026: calculate check-in as today + 30 days and
checkout three days later (2026-11-13 to 2026-11-16 in this run). Log in through
context A and create a uniquely named booking. Log in independently through
context B and submit the identical payload with the second session's token.

- Expected: HTTP 400 or 409, with the original booking unchanged and no created duplicate.
- Actual: HTTP 200 with a normal booking response and a new booking ID. The original
  ID was 388 and the duplicate ID was 400. GET of the duplicate returned 200 with
  the submitted booking; the original remained unchanged. No validation error
  was present in the duplicate response.
- Test: tests/live/test_capabilities.py::test_business_duplicate_rejection.
- Result: **FAIL** in pytest, JUnit, and Allure. Both owned bookings were deleted.

The assertion also fails when 400/409 identifies a new booking that GET confirms
still exists. Hidden effects without a returned resource ID remain unmeasured.
The test uses two authenticated sessions of the sandbox account; distinct user
ownership and a same-room identifier remain outside the available API model.

Request/response attachments and subsequent GET evidence are in
reports/duplicate-rejection-20261014T194107Z/html/index.html. This is an isolated
targeted run; the previous full-suite reports and history are preserved.

## Deep contract and invariant findings — 15 October 2026

The focused public-sandbox run executed 66 cases: **13 passed and 53 failed**.
All failures were direct assertions, with no XFAIL, skip, or broken results.
Reversed/equal dates and negative prices are now ordinary negative-validation
checks in test_validation.py for POST, PUT, and PATCH. The earlier acceptance
characterizations and business-gap exceptions have been removed.

| Area | Hosted observation | Result |
| --- | --- | --- |
| Calculated totals and deposit flags | All four valid POST/PUT/PATCH/GET workflows preserved client-derived integer totals, both boolean values, and the expected nested dates; zero total was accepted | Four passed |
| PUT/PATCH invalid scalar/date types | PUT rejected null price, null deposit, and null/array/string bookingdates with 400 and preserved state. All other selected invalid updates were accepted or produced a server error | Five passed, 25 failed |
| POST invalid scalar/date types | The 15 probes returned success or a server error, never the expected 400/422 validation result | 15 failed |
| Required nested dates | PUT returned 400 for either missing nested date and preserved the original. POST returned 500 | Two passed, two failed |
| Logical date and price constraints | Reversed dates, equal dates, and negative prices were accepted by all three write methods | Nine failed |
| Existing contract/preservation checks | Valid creation and scalar PATCH passed. Combined invalid-price/boolean PATCH and nested PATCH preservation failed | Two passed, two failed |

Examples confirmed in both response and GET: totalprice 123.45 was truncated to
123, numeric depositpaid 0 became false, checkout 2027-02-30 became 2027-03-02,
and a timestamp check-in was reduced to its date portion. The strict contract
requires integer prices, genuine boolean flags, and valid YYYY-MM-DD calendar
dates; coercion does not satisfy input rejection. The valid pricing workflows
prove exact preservation of calculated test inputs, not server rate/tax arithmetic.

All 78 owned bookings were deleted. The audit checked all 277 resource-specific
requests against the owning test's IDs and resolved all 1,416 live attachment
references. Evidence and HTML reports are under
reports/deep-validation-20261014T200228Z; timestamps in directory names are UTC,
so the local execution date is 15 October. Existing history files were unchanged.
