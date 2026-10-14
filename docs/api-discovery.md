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

1. Treat duplicate acceptance as an explicit sandbox capability result. A strict
   enterprise overlap-rejection test needs a target with room inventory semantics.
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

Duplicate acceptance remains a business-policy gap because the API has no room
inventory or owner model. API-007 concerns HTTP status semantics: repeated DELETE
still satisfies observable-state idempotency when subsequent GET confirms absence.
