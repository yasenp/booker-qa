# Idempotency: scope, evidence, and production extensions

HTTP idempotency means repeating an identical request has the same intended effect
as performing it once. It does not require identical responses or forbid extra
request logs and revision history. Resource-version stability is an additional
assessment expectation, and hidden business-effect deduplication needs its own
contract and observability. See [RFC 9110 section 9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2).

## Executable catalog

| Scenario family | Identified cases | Tests | Evidence |
| --- | --- | --- | --- |
| Sequential identical PUT | 3: repetitions 2, 3, 5 | Original three-PUT test plus parameterized sequential test | Initial state, identical payload, response contract, each persisted snapshot, differences |
| Concurrent identical PUT | 2: workers 2, 4 | Concurrent identical PUT test | Shared payload, each outcome, release skew, final-state equality |
| Repeated DELETE | 1: three attempts | Repeated DELETE test | DELETE codes and confirming GET 404 after each operation |
| Repeated set-value PATCH | 1: three attempts | Repeated set-value PATCH test | Full expected state and snapshots; untouched fields preserved |

These are **4 supported live scenario families and 7 parameterized cases**.
They establish observable booking-state behavior. Response assertions verify the
separate sandbox contract; equal responses are not the definition of idempotency.
Repeated DELETE can return 405 here; it is accepted only with a confirming GET 404.
Set-value PATCH conclusions do not extend to increment or append operations.

The existing conflicting-update tests have **different payloads**, so they measure
collision integrity and are excluded from this idempotency denominator.

## Controlled response loss

Eight cases cover POST/PUT/PATCH/DELETE crossed with before/after a **simulated**
commit. A MockTransport callback optionally changes a local model, then loses the
response. Assertions verify one request was sent, the timeout propagated, and the
client did not replay a mutation. Model operation counts are attached for diagnosis.

These checks measure client uncertainty handling. They do not prove the live API's
rollback, transactions, exactly-once processing, or commit-boundary resilience.
The conservative retry policy remains in place: bounded reads and pre-send
connection retries, one explicit authentication refresh, no blind replay after an
ambiguous mutation outcome. HTTP semantics can permit retrying PUT/DELETE; this
framework deliberately does not enable that policy against a shared sandbox where
intervening writes can occur.

## Measuring coverage

Run `python scripts/report_coverage.py --mode live` after collecting Allure results.
It creates `reports/live/coverage.json` with actual outcomes and explicit denominators:

- Executed supported live families / 4 identified families.
- Executed and passed supported live cases / 7 identified cases.
- Executed and passed controlled response-loss cases / 8 identified cases.

Offline runs correctly report zero executed live cases, despite collecting skipped
test entries. Failed/broken attempts count as executed but never as passed.
The measured JSON and this scope document are attached globally to Allure reports.
Do not combine these figures into an overall API coverage percentage. Server branch
coverage, hidden effects, and live key-based deduplication remain unmeasured or
unsupported. These denominators describe the declared catalog, not every conceivable
idempotency behavior.

## Production extensions requiring another target

Before implementing key-based tests, obtain a published contract covering header
syntax, required/optional keys, maximum size, scope (account/tenant/endpoint), TTL,
payload fingerprint equivalence, in-progress handling, replay statuses/bodies,
and whether failures reserve or release a key. Sending a header alone does not
establish server support.

The referenced IETF [Idempotency-Key document](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
was an expired Internet-Draft when reviewed on 13 October 2026, not a published RFC.
Its proposals distinguish 422 for payload mismatch from 409 for an outstanding
operation, and use a quoted structured string header value. Follow the target's
actual contract rather than treating those proposals as universally implemented.

Future scenarios include identical keys/payloads, different keys, payload mismatch,
semantic JSON equivalence, missing/malformed/oversized keys, concurrent requests,
expiry, cross-tenant isolation, restart persistence, and different replicas.
All are unsupported live coverage for this sandbox until relevant facilities exist.

Authoritative checks need a unique test correlation ID and scoped database/audit
queries: one logical operation, one intended balance change, and no duplicated
external submission. Logs and delivery attempts can legitimately be repeated.
For asynchronous events, use bounded polling with a defined observation window
and terminal condition. Distinguish message redelivery from duplicate business
effects; exactly-once message delivery is not assumed.

Commit-boundary tests need deterministic server-side injection points before key
reservation, between reservation and business mutation, immediately before/after
commit, and around event publication/acknowledgment. A lost-response-after-commit
test must independently confirm commitment before the response is dropped.
Verify atomic key/business-state handling and recovery across replicas. These
extensions are documented prerequisites, not passing simulations of production.
