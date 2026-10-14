# Walkthrough and design decisions

1. Start with the coverage table. Rooms, ownership, server-calculated prices, versions,
   real token TTL, and exact server arrival time cannot be proven with this API.
2. Follow configuration into BookerClient. Negative HTTP responses stay available
   to tests. Reads retry bounded transport failures and 429/502/503/504 responses.
   Mutation connection establishment failures may retry before send; response
   loss and write failures do not replay mutations.
3. AuthManager serializes initial issuance. Refresh takes the rejected token so
   a thread reuses a replacement already issued by another thread. The retry
   ceiling prevents a permanent 403 from causing a refresh loop. No invented TTL
   is used: protected endpoints are the authoritative validity check. Optional real
   aging tests require the target's documented absolute TTL and wait beyond it before
   probing the unchanged token without automatic refresh. Missing TTL means an
   explicit skip, not a passing expiry result. New-login revocation is a separate
   requested policy with a direct assertion.
4. BookingRegistry tracks only created IDs. It deep-copies payloads, records a
   prerequisite's replacement ID, and permits one recreation by default. Never
   recover a post-operation assertion: doing so would conceal a failed update.
   A live independent-client purge verifies recovery followed by a successful
   protected PUT and confirming GET. A second live case mixes an already-deleted
   ID with a remaining booking and checks cleanup continues without recreation.
   DELETE 404 succeeds directly; this sandbox's 405 succeeds only after GET 404.
   Controlled cases keep non-404 errors, exhaustion, and cleanup failures visible
   while ensuring cleanup still attempts every owned ID.
5. Schema validation checks types and explicit date formats. Business invariants
   enforce ordering and nonnegative price separately, because the server accepts
   values violating them. JSON Schema format checks are explicitly enabled.
   POST creation also validates the response envelope and ID. Successful response
   and persisted-state comparisons distinguish booleans from numbers and preserve
   JSON type differences; ordinary Python equality would accept `True == 1`.
   The integer checker also rejects 123.0, and every successful comparison enforces
   date order and nonnegative total even when the two bodies are identical.
   POST/PUT/PATCH negative cases directly assert rejection; no business XFAIL
   masks acceptance. Positive workflows calculate duration times a test rate and
   verify exact persistence, without claiming a server pricing formula exists.
6. The original PUT test retains its three persisted snapshots and historical ID.
   Additional sequential counts (2/5), concurrent identical PUTs (2/4 writers),
   repeated DELETE, and set-value PATCH verify observable state. Response equality
   is a separate contract assertion. These checks do not claim hidden effects are
   absent or that resource versions cannot advance; those need extra contracts.
7. Conflicting writers test collision integrity, separately from identical-request
   concurrency idempotency. Concurrent writers share a thread-safe client and token manager. A barrier
   coordinates release. Every distinguishing field, including nested dates,
   differs between candidates. Final membership detects partial payload merges.
   Client start skew and the winning payload are attached to JUnit results.
   Each PUT returning its submitted payload is checked as a separate sandbox
   response contract. It is stronger than the final-state integrity predicate and
   must be revisited for a backend that returns the latest concurrent writer's state.
   Two additional PATCH scenarios check same-field conflict integrity and separate-field
   lost updates. The former accepts either final price and requires own-update responses;
   the latter requires both changes in the final GET while allowing intermediate response
   snapshots. Untouched fields must survive both scenarios. Sixteen controlled cases
   exercise either write order and verify that injected failures are detected.
   Shared reconciliation now requires both successes and three identical final GETs.
   The expected policy and observed statuses are explicit; a 409/412 fails instead
   of being reclassified automatically as successful optimistic locking. Ordered
   A-to-B/B-to-A PUT controls verify the last write wins when the ordering is known.
   Nineteen further controlled cases detect partial merges, rejected/ignored writes,
   missing state, type corruption, and read-to-read drift. True-race commit order
   and direct database state remain unmeasured; GET stability has a bounded scope.
8. pytest-xdist workers have independent clients, tokens, IDs, and fixtures.
   No filesystem token cache or global lock is required between processes.
9. Controlled fault tests verify retry exhaustion, single-flight refresh, bad
   credentials, missing prerequisites, and cleanup failures deterministically.
10. CI runs offline tests on pushes/PRs; a manual input enables live tests to avoid
    depending on a public shared sandbox for every commit. Reports upload even
    after failures. This workflow has not been run on GitHub from this workspace.

## Remaining operational limits

The sandbox can mutate/delete records immediately after any prerequisite check.
An unknown-outcome POST can create an untracked booking if its response is lost;
it fails visibly and is never blindly retried. Unique guest markers aid diagnosis,
but automated sweeping by guest name could delete another user's records and is
not performed. Cleanup attempts every tracked ID and reports failures explicitly.

Reauth repeats an explicitly rejected protected request once. This relies on
401/403 meaning the operation was not authorized; it does not replay requests
after ambiguous transport failures. Credentials/tokens are excluded from logs
and token values are never written to reports.

The offline preparation can use AI; the assessment requires an unaided live
walkthrough. Practice explaining these tradeoffs and running individual tests.


## Idempotency coverage and production discussion

The supported live catalog has four families/seven cases. Controlled response-loss
coverage has eight cases (four mutation methods crossed with before/after simulated
commit). Counts come from the actual Allure run, with skipped, executed, and passed
results separated. Neither catalog is a percentage of all API behaviors. Server
branch coverage and hidden effects remain unmeasured.

Explain why our client does not replay an ambiguous mutation even when PUT/DELETE
semantics can permit a retry: conservative shared-sandbox behavior, no version
preconditions, and intervening writes. The local model demonstrates the client
policy, not server rollback or deduplication. A production lost-response test must
confirm commitment independently before dropping the response.

Key-based POST deduplication would require documented key syntax, tenant/endpoint
scope, fingerprint rules, replay behavior, failure policy, and retention. Use scoped
operation/audit counts and unique correlation IDs. Async effects need bounded polling;
message delivery counts are distinct from completed business effects. Deterministic
server failpoints and multi-replica/restart controls are absent from this target.
See idempotency-coverage.md for the complete prerequisites and standards caveat.
