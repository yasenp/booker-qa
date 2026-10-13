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
