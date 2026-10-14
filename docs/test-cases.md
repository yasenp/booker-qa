# Test case catalog

This catalog covers all 88 test functions and 331 collected cases:
39 live functions (135 cases) and 49 controlled functions
(196 cases). Parameterization expands a function into the cases shown below.
Counts describe collection, not executed or passing coverage. Refer to
[validation results](validation-results.md) for dated run outcomes and known failures.

Each test has a short purpose comment above its decorators and a docstring describing
the scenario, test type, expected outcome, parameter matrix, and material limits.
Allure uses a dedented copy of that docstring as its description, including for skipped
cases; pytest still supplies the individual parameter values. Names and parameter IDs
stay unchanged so existing test selections and report history remain valid.

## Running and interpreting the cases

Activate the project's Python environment as described in [setup](../README.md#setup).
Run a function by its path and name; parameterized functions run all their variants.

```sh
python -m pytest tests/unit/test_auth.py::test_parallel_initial_acquisition_is_single_flight
python -m pytest tests/live/test_lifecycle.py::test_conflicting_updates_reconcile_to_one_complete_payload --live
python -m pytest --collect-only -q
```

Live cases use the configured sandbox only with `--live`. Real-token expiry also needs
the target's documented `--token-ttl-seconds`; no TTL is inferred from the public host.
The default offline run skips live cases. Controlled tests use callbacks, MockTransport,
synthetic state/clock models, or isolated pytest subprocesses. They can pass because
an injected failure was correctly detected; that is framework evidence, not a live API pass.

Application and requested business-policy checks use ordinary assertions. Expected
behavior in this catalog is the assertion contract, not a claim that the sandbox
currently satisfies it. Auth denial can be HTTP 200 with a Bad credentials body.
New-login revocation is a requested policy distinct from elapsed-time expiry and from
the multiple-session behavior exercised by independent-login tests.

Idempotency checks cover observable booking state; hidden effects and operation counts
are unmeasured. Concurrency checks allow either complete winner and verify observed
stability, while ordered controls establish a known winner. Direct database access,
exact server arrival timing, room ownership, and server pricing inputs are unavailable.
Prerequisite GET 404 can trigger bounded recovery; post-operation assertions remain
strict. Cleanup touches tracked IDs and never creates replacement records.
See [requirement mapping and limits](requirements-coverage.md) for the full scope.

## Live API scenarios

### Auth expiry

Real-token lifetime checks; the target's absolute TTL must be explicitly supplied.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_real_token_expiry_and_reauthentication](../tests/live/test_auth_expiry.py#L105) | Live authentication lifecycle | 3 | 0, 1, or 4 recovery callers | The aged token receives 401/403 without changing the booking. Recovery modes complete all updates with exactly one new auth request and issuance. Scope: Requires --live and a documented --token-ttl-seconds; otherwise skipped. The three modes are rejection only, sequential refresh, and concurrent refresh. No sandbox TTL is inferred. |

### Auth sessions

Live login, authorization, concurrent-session, and requested revocation-policy checks.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_valid_login_authorizes_booking_update](../tests/live/test_auth_sessions.py#L16) | Live authentication positive | 1 | One valid login | PUT and GET return 200 and exactly match the intended booking, including strict field types and invariants. Scope: Explicit cookies bypass automatic refresh, so the original token itself must work. |
| [test_auth_rejects_invalid_credentials](../tests/live/test_auth_sessions.py#L44) | Live authentication negative | 3 | Wrong password, empty credentials, missing credentials | HTTP 200 contains exactly the Bad credentials reason and no token or extra fields. Scope: This endpoint reports authentication denial in its body; HTTP 200 alone is not successful login. |
| [test_protected_mutations_reject_bad_tokens](../tests/live/test_auth_sessions.py#L92) | Live authorization negative | 12 | 4 token cases x PUT/PATCH/DELETE | Every mutation returns 403 and GET returns the full unchanged booking with status 200. Scope: Automatic refresh is disabled. Invalid tokens test rejection, not elapsed-time expiration. |
| [test_inherited_property_tokens_are_rejected](../tests/live/test_auth_sessions.py#L122) | Live authorization regression | 9 | toString/constructor/__proto__ x PUT/PATCH/DELETE | HTTP 403 is accompanied by an unchanged, still-accessible booking; a denial response cannot hide a mutation. Scope: A source-review security assertion executed against the target; accepted unauthorized writes fail normally. |
| [test_parallel_independent_logins_issue_usable_tokens](../tests/live/test_auth_sessions.py#L141) | Live authentication concurrency | 1 | 4 clients and 4 owned bookings | Four logical auth requests issue four distinct tokens, and all response and persisted booking payloads match. Scope: Clients use the same sandbox account and separate bookings. This checks multiple-session behavior, not distinct-user isolation or exact simultaneous server arrival. |
| [test_auth_rejects_nonexistent_user](../tests/live/test_auth_sessions.py#L196) | Live authentication negative | 1 | One generated nonexistent username | HTTP 200 contains exactly the Bad credentials reason and no token. Scope: The response verifies failed authentication; there is no account-storage endpoint to inspect registration independently. |
| [test_new_login_invalidates_previous_token](../tests/live/test_auth_sessions.py#L287) | Live session-policy check | 1 | 2 clients using the same credentials | The old token receives 401/403 and cannot replace the state written by the new session. Scope: Automatic refresh is disabled. Revocation is an additional requested policy, not documented sandbox TTL behavior; continued old-token acceptance is an ordinary failure. |

### Capabilities

Live duplicate-rejection requirement using calculated dates and independent sandbox sessions.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_business_duplicate_rejection](../tests/live/test_capabilities.py#L68) | Live business-rule negative | 1 | 2 independently authenticated sessions | The second POST returns 400/409, the first booking remains unchanged, and any returned new ID is absent. Unexpected created IDs remain tracked for cleanup. Scope: Both clients use the sandbox account. No room inventory, distinct-user ownership, or authoritative operation count is exposed; acceptance fails the requested rejection rule. |

### Filters

Booking search boundaries and validation of date filters.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_checkin_filter_includes_boundary](../tests/live/test_filters.py#L32) | Live search boundary | 1 | Thresholds one day before, equal to, and one day after check-in | The booking appears for the earlier and equal thresholds, disappears for the later threshold, and retains its full payload. |
| [test_checkout_filter_uses_documented_direction](../tests/live/test_filters.py#L54) | Live search boundary | 1 | Thresholds one day before, equal to, and one day after checkout | The booking appears for earlier/equal thresholds and is excluded for the later threshold; unrelated guest records never appear. |
| [test_malformed_date_filter_returns_client_error](../tests/live/test_filters.py#L77) | Live search negative | 2 | checkin and checkout | The malformed filter receives 400/422 and the valid controls still succeed without changing the owned booking. Scope: A server error or failed positive control remains a failure rather than being interpreted as correct validation. |

### Idempotency

Observable state guarantees; no claims about hidden server-side effects.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_sequential_identical_put_preserves_observable_state](../tests/live/test_idempotency.py#L54) | Live idempotency | 2 | 2 and 5 consecutive PUTs | Each PUT returns 200 with its submitted payload and every persisted snapshot matches the single-request target. Scope: The original three-PUT case is retained separately. Hidden side effects, operation counts, and resource-version stability are unmeasured. |
| [test_repeated_set_value_patch_preserves_observable_state](../tests/live/test_idempotency.py#L72) | Live idempotency | 1 | 3 totalprice assignments | All writes return 200 and both responses and persisted states preserve the new price and every untouched field. Scope: Applies to set-value PATCH only; increment/append operations and hidden side effects are outside this check. |
| [test_concurrent_identical_put_preserves_observable_state](../tests/live/test_idempotency.py#L92) | Live concurrent idempotency | 2 | 2 and 4 synchronized writers | Every write returns 200 with the submitted payload and final GET matches it exactly. Client release skew and worker errors are retained. Scope: Checks API-visible state, not server operation counts, hidden effects, or exact server overlap. Conflicting payloads are tested separately. |
| [test_repeated_delete_keeps_booking_absent](../tests/live/test_idempotency.py#L145) | Live idempotency | 1 | 3 DELETE requests with a GET after each | The first DELETE returns 201; later requests return an allowed success/absence status. Every confirming GET returns 404. Scope: Sandbox 405 is accepted here only with GET 404. This checks absence idempotency; missing-resource HTTP semantics have a separate stricter test. |

### Lifecycle

Live booking contracts, state reconciliation, authentication recovery, and owned-record hygiene.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_create_contract](../tests/live/test_lifecycle.py#L30) | Live creation contract | 1 | One generated valid booking | Stored values exactly match the original payload, strict schema types hold, price is nonnegative, and checkout follows check-in. |
| [test_put_three_times_is_idempotent](../tests/live/test_lifecycle.py#L47) | Live idempotency | 1 | Exactly 3 consecutive PUTs | Every write returns 200 with the expected body; all three GET snapshots equal the same full payload. Scope: Response equality is checked as the sandbox contract. Hidden side effects, operation counts, and resource versions are unmeasured. |
| [test_patch_preserves_every_untouched_field](../tests/live/test_lifecycle.py#L82) | Live partial-update integrity | 1 | Only totalprice changes | HTTP 200 response and GET equal the baseline with only totalprice replaced; names, flags, needs, and both nested dates are preserved. |
| [test_nested_patch_preserves_checkout](../tests/live/test_lifecycle.py#L113) | Live nested-update regression | 1 | Only bookingdates.checkin changes | Both statuses are 200 and complete payloads equal the intended nested merge, with the original checkout retained. Scope: Corruption is a normal failure; post-operation reads do not recreate a missing or damaged booking. |
| [test_missing_resource_mutation_reports_absence](../tests/live/test_lifecycle.py#L147) | Live HTTP semantics negative | 3 | PUT, PATCH, and DELETE after confirmed deletion | PUT/PATCH return 404/410; repeated DELETE returns 200/204/404/410. The resource remains absent with GET 404. Scope: HTTP 405 fails this semantics check even though cleanup and DELETE-idempotency scenarios can tolerate it when absence is confirmed. |
| [test_invalid_token_is_refreshed](../tests/live/test_lifecycle.py#L180) | Live authentication recovery | 1 | Deliberately invalid cached token | The client recovers to HTTP 200 and response plus final GET match the intended full payload. Scope: Invalid-token rejection simulates expiry. Actual elapsed-time expiry and exact shared-refresh counts have separate tests. |
| [test_missing_prerequisite_is_recreated](../tests/live/test_lifecycle.py#L218) | Live sandbox recovery | 1 | Independent-client deletion followed by one recreation | The handle changes to a tracked replacement ID, one recovery is recorded, and protected PUT/GET match the updated full payload. Scope: Both clients use the sandbox account and target only owned IDs. Recovery applies to prerequisites; post-operation failures remain visible. |
| [test_sandbox_cleanup_handles_external_purge](../tests/live/test_lifecycle.py#L257) | Live sandbox hygiene | 1 | 2 owned records; first removed through a separate client | Each ID receives a successful deletion/absence outcome, both final GETs return 404, and cleanup creates no replacement booking. Scope: DELETE 405 requires GET 404. Repeated fixture cleanup is allowed; unrelated resource IDs and global reset routes are never used. |
| [test_conflicting_updates_reconcile_to_one_complete_payload](../tests/live/test_lifecycle.py#L346) | Live concurrency integrity | 3 | 3 rounds, each with 2 synchronized PUT writers | Both writes return 200 and their own payload; all three reads equal one full candidate with strict types and invariants. Partial merges and drift fail. Scope: Either writer may win. Client timing cannot reveal commit order; direct database state and optimistic locking are unverified. Unexpected 409/412 fail the configured overwrite policy. |
| [test_ordered_conflicting_put_uses_last_completed_write](../tests/live/test_lifecycle.py#L407) | Live overwrite-policy control | 2 | A_then_B and B_then_A | Both responses match their submitted payloads and every final GET equals the second writer's complete booking. Scope: This sequential control verifies overwrite behavior when order is known. It does not establish concurrent server commit order. |
| [test_conflicting_patch_preserves_one_price_and_untouched_fields](../tests/live/test_lifecycle.py#L491) | Live concurrency integrity | 1 | 2 synchronized PATCH writers: prices 250 and 850 | Both PATCHes return 200 with their own update; one price wins and the identical complete booking appears in every reconciliation GET. Scope: Client release skew is recorded, not constrained. Exact server overlap, hidden effects, and commit order are unmeasured. |
| [test_concurrent_patch_preserves_both_independent_changes](../tests/live/test_lifecycle.py#L524) | Live lost-update detection | 1 | 2 synchronized writers: totalprice and lastname | Both writes return 200. Each response includes its own change alone or both; all final reads contain both changes and preserve unrelated fields. Scope: This checks commutative partial-update integrity. A response before the other write completes is valid; exact server overlap is not guaranteed. |
| [test_parallel_setup_acquires_one_live_token](../tests/live/test_lifecycle.py#L563) | Live authentication concurrency | 1 | 4 threads sharing one AuthManager | All tokens are nonempty and identical, with one logical POST /auth request and one successful issuance. Scope: Pre-send connection retries may add HTTP attempts while retaining one logical request ID. Token values are omitted from report summaries. |

### Smoke

Live health-endpoint smoke check using the configured API client.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_api_health](../tests/live/test_smoke.py#L8) | Live smoke | 1 | GET /ping | The final response status is 201. Scope: This is a reachability/health check; it does not exercise booking CRUD or authentication. |

### Validation

Invalid booking inputs must be rejected without corrupting stored state.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_updates_reject_invalid_field_types](../tests/live/test_validation.py#L83) | Live input-validation negative | 30 | 15 invalid field cases x PUT/PATCH | HTTP 400/422 is returned and the original ID remains readable with its exact previous payload. Scope: String coercion, fractional prices, boolean-as-number values, malformed calendars, and timestamps must not silently become valid stored data. |
| [test_creates_reject_invalid_field_types](../tests/live/test_validation.py#L103) | Live input-validation negative | 15 | 15 invalid field cases sent with POST | HTTP 400/422 is returned, the control is unchanged, and any returned new booking ID is absent and tracked for cleanup. Scope: A distinct guest prevents duplicate rejection from masking field validation. Hidden creations without a returned ID cannot be counted authoritatively. |
| [test_full_requests_require_both_dates](../tests/live/test_validation.py#L124) | Live required-field negative | 4 | Missing checkin/checkout x POST/PUT | HTTP 400/422 is returned without changing the valid booking or leaving an accessible returned creation ID. Scope: Partial nested PATCH has different semantics and is tested for preservation rather than required full-object replacement. |
| [test_business_invalid_values_rejected](../tests/live/test_validation.py#L144) | Live business-invariant negative | 9 | Reversed dates/equal dates/negative price x POST/PUT/PATCH | HTTP 400/409/422 is returned, existing state stays unchanged, and any returned creation ID does not remain accessible. Scope: These are ordinary requirement assertions; known sandbox acceptance is reported as failure rather than XFAIL. |
| [test_calculated_price_and_deposit_round_trip](../tests/live/test_validation.py#L171) | Live contract and invariant positive | 4 | 4 night/rate/deposit combinations, including zero price and both flags | Responses and GETs preserve exact calculated totals, boolean values, valid dates, and every field left untouched by PATCH. Scope: The arithmetic is client-side test-data construction. The API exposes no server rate/tax formula to validate. |
| [test_patch_rejects_internal_fields](../tests/live/test_validation.py#L216) | Live internal-field negative | 2 | bookingid and meta | HTTP 400/422 is returned and both original resources retain their IDs and complete payloads. Scope: The owned collision destination is registered twice before mutation so cleanup can remove both aliased records if the application accepts the forbidden change. |
| [test_resource_ids_require_exact_integer](../tests/live/test_validation.py#L253) | Live resource-ID negative | 8 | Text/fractional suffixes x GET/PUT/PATCH/DELETE | The malformed route returns 400/404/422 and the original booking remains accessible and unchanged. |
| [test_patch_rejects_invalid_types_without_mutation](../tests/live/test_validation.py#L280) | Live combined-input regression | 1 | totalprice='abc' and depositpaid='false' | HTTP 400/422 is returned and every original value and type remains unchanged. |
| [test_incomplete_post_returns_client_error](../tests/live/test_validation.py#L309) | Live required-field regression | 1 | POST containing only firstname | The invalid POST returns 400/422 and both positive controls work; any unexpected returned ID is retained for cleanup. Scope: HTTP 500 is an application error and fails this check. Positive controls distinguish invalid-input behavior from general unavailability. |

## Controlled framework scenarios

### Allure statuses

Exercise the adapter on intentional failures outside the real suite/report.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_adapter_preserves_status_and_exit_code](../tests/unit/test_allure_statuses.py#L21) | Controlled reporting integration | 7 | PASS, SKIP, XFAIL, XPASS, assertion, exception, teardown failure | Exactly one report has the expected status and process exit code; expected failures retain their XFAIL explanation. Scope: Intentional failures are confined to temporary subprocess suites. Their statuses do not describe the live API. |
| [test_evidence_survives_real_fixture_failures](../tests/unit/test_allure_statuses.py#L53) | Controlled reporting integration | 3 | Failure during call, setup, or teardown | Pytest exits with failure; Allure classifies the phase correctly, all attachment references resolve, and request/response plus applicable ownership evidence survive. Scope: The controlled authentication secret must be absent from every result artifact. No public sandbox is contacted. |

### Auth

Controlled AuthManager and client-refresh tests; no public sandbox or real token expiry.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_parallel_initial_acquisition_is_single_flight](../tests/unit/test_auth.py#L17) | Controlled authentication concurrency | 1 | 8 threads and one blocked issuer callback | The issuer runs exactly once, every caller receives the same token, and no thread remains alive. Scope: This exercises AuthManager locking without HTTP. The separate live setup test counts real POST /auth requests. |
| [test_concurrent_rejection_refreshes_once](../tests/unit/test_auth.py#L73) | Controlled authentication concurrency | 2 | 401 and 403; 4 callers each | All four protected calls finish with 200 and only two tokens are issued overall: initial acquisition plus one refresh. Scope: Verifies client coordination under modeled rejection, not a hosted token lifetime. |
| [test_persistent_forbidden_refresh_is_bounded](../tests/unit/test_auth.py#L112) | Controlled authentication resilience | 1 | Protected PUT always returns 403 | The caller receives the second 403; exactly two auth calls and two protected writes occur. |
| [test_authentication_failure_does_not_cache_missing_token](../tests/unit/test_auth.py#L139) | Controlled authentication negative | 1 | 2 acquisition attempts without a returned token | Each attempt raises ValueError and reaches authentication again, proving a missing token was not cached as usable. |

### Auth lifecycle

Validate lifecycle assertions against controlled models; these do not prove hosted token expiry.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_token_expiry_workflow_with_controlled_clock](../tests/unit/test_auth_lifecycle.py#L82) | Controlled lifecycle assertion check | 6 | 401/403 x 0/1/4 recovery callers | The workflow advances eleven simulated seconds, rejects the aged token, accepts a fresh control, and issues exactly one recovery token when callers are enabled. Scope: Clock advancement and token validity are simulated; these passes do not establish expiry in the hosted sandbox. |
| [test_token_expiry_workflow_detects_failures](../tests/unit/test_auth_lifecycle.py#L102) | Controlled lifecycle regression | 5 | Never expires, server error, rejection mutates, fresh failure, recovery rejection | The actual scenario raises AssertionError rather than treating the injected failure as successful expiry enforcement. Scope: This verifies the test oracle with deterministic models, not live server fault handling. |
| [test_new_login_policy_assertion_without_automatic_refresh](../tests/unit/test_auth_lifecycle.py#L123) | Controlled session-policy regression | 2 | Revoking and non-revoking token models | The revoking model passes; continued old-token acceptance raises the policy assertion. Exactly two logins occur, so a silent refresh cannot hide revocation. Scope: Validates the requested single-session test policy; it is not hosted revocation or TTL evidence. |

### Client

Controlled HTTP client behavior with MockTransport; no network calls.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_negative_response_is_preserved_without_retry](../tests/unit/test_client.py#L9) | Controlled HTTP client contract | 1 | One PUT returning 403 | The caller receives 403 after one attempt and the default Accept header is application/json. Scope: Automatic refresh applies only to requests explicitly marked authenticated; this case does not enter that path. |

### Commit boundary simulation

Controlled response loss: client behavior, not live server transaction evidence.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_lost_response_reports_uncertainty_without_replaying_mutation](../tests/unit/test_commit_boundary_simulation.py#L16) | Controlled fault simulation | 8 | POST/PUT/PATCH/DELETE x before/after simulated commit | Only one request is sent, the timeout reaches the caller, and simulated committed-operation count and state match the selected boundary. Scope: Allure identifies this as a simulation. It does not prove hosted transaction boundaries, rollback, deduplication, or exactly-once effects. |

### Contract

Offline schema, calendar, business-invariant, and comparison-assertion checks.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_generated_payload_has_valid_contract_and_business_invariants](../tests/unit/test_contract.py#L11) | Controlled data/schema positive | 1 | One generated payload | Validation succeeds with complete nested dates, strict field types, nonnegative price, and checkout after check-in. |
| [test_contract_rejects_malformed_wire_values](../tests/unit/test_contract.py#L39) | Controlled schema negative | 19 | 19 malformed scalar, nested, date, or extra-field changes | ValidationError is raised for wrong types, missing dates, extra fields, impossible calendars, non-padded dates, or timestamps. Scope: Integer representation is deliberately strict: booleans and floats, including 123.0, do not satisfy the framework's integer policy. |
| [test_date_order_is_a_separate_business_invariant](../tests/unit/test_contract.py#L62) | Controlled invariant negative | 2 | Equal and reversed dates | The wire schema passes, then validate_invariants raises a checkout-related ValueError. |
| [test_negative_price_is_a_separate_business_invariant](../tests/unit/test_contract.py#L80) | Controlled invariant negative | 1 | totalprice = -1 | Schema validation succeeds, while the business validator raises a nonnegative-price ValueError. |
| [test_contract_accepts_valid_calendar_and_value_boundaries](../tests/unit/test_contract.py#L103) | Controlled contract boundary positive | 3 | 3 leap-day/year-end/price/deposit combinations | Strict contract, logical invariants, and equality checks all succeed. |
| [test_matching_payloads_still_require_contract_and_invariants](../tests/unit/test_contract.py#L125) | Controlled assertion regression | 6 | 6 invalid price, flag, date-format, or date-order changes | The comparison still raises AssertionError through schema or invariant validation, even though the values match. |

### Coverage reporting

Coverage denominators must distinguish collection, execution, and success.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_scoped_coverage_never_counts_skips_or_failures_as_passes](../tests/unit/test_coverage_reporting.py#L7) | Controlled reporting calculation | 1 | Synthetic passed/skipped/broken/failed results plus an excluded conflict test | Family/case denominators remain correct, skips do not count as execution, failures do not count as passes, and conflicting-write results are excluded from idempotency coverage. Scope: Server branch coverage remains unmeasured; these counters describe the explicit scenario catalog. |

### Duplicate context

Verify cross-session duplicate assertions without treating model results as hosted evidence.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_duplicate_context_and_failure_classification](../tests/unit/test_duplicate_context.py#L30) | Controlled cross-session regression | 9 | 9 duplicate response/state outcomes | Only clean 400/409 rejection passes. Both sessions use their own issued cookie, identical calculated dates are submitted, failures raise ordinary assertions, and every created record is cleaned up. Scope: The model verifies request construction and assertion behavior, not hosted overlap enforcement or distinct-user authorization. |

### Evidence

Offline checks for evidence sanitization, thread safety, precise differences, and recovery events.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_warning_logs_exclude_url_secrets](../tests/unit/test_evidence.py#L17) | Controlled logging security | 4 | Connect failure, 503, 401, and 403 | The recovered request succeeds with two attempts and one warning; endpoint path remains visible while credential, token, fragment, and raw exception secrets are absent. |
| [test_auth_bodies_headers_and_query_secrets_never_enter_evidence](../tests/unit/test_evidence.py#L60) | Controlled evidence security | 1 | Secrets in auth, request JSON, response JSON, and query | No planted secret appears, authentication bodies are omitted, and non-sensitive response fields remain available. |
| [test_collector_keeps_all_thread_events_and_snapshot_is_detached](../tests/unit/test_evidence.py#L92) | Controlled collector concurrency | 1 | 100 events from 8 worker threads | Every index appears exactly once and a later snapshot still contains the original redacted nested value. |
| [test_sanitizer_handles_case_and_nested_sequences](../tests/unit/test_evidence.py#L112) | Controlled sanitization unit | 1 | Mixed-case Authorization and Cookie keys inside a list | Both sensitive values are replaced with the redaction marker while the surrounding structure is preserved. |
| [test_diffs_distinguish_nested_changes_types_missing_and_null_without_leaking_secrets](../tests/unit/test_evidence.py#L127) | Controlled comparison unit | 1 | Nested date, bool/int, missing/null, list addition, and token changes | Each difference identifies the correct path and change; secrets are redacted, and identical valid values produce no differences. |
| [test_retry_and_refresh_events_correlate_attempts_and_exclude_sensitive_headers](../tests/unit/test_evidence.py#L156) | Controlled retry reporting | 1 | ConnectTimeout, then 503, then 200 | One logical request spans attempts 1/2/3 with 0.25/0.5-second backoffs; safe headers remain while cookies and raw exception text are absent. Scope: This scenario exercises retry evidence. Authentication-refresh event fields are verified by the separate refresh-event test. |
| [test_auth_refresh_event_records_trigger_and_never_the_token](../tests/unit/test_evidence.py#L199) | Controlled authentication reporting | 1 | One 403 followed by a successful refreshed PUT | The request succeeds and exactly one auth_refresh event records status 403; neither issued token appears in serialized evidence. |

### Filter assertions

Exercise live filter assertions with controlled validation and infrastructure responses.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_malformed_filter_requires_client_error](../tests/unit/test_filter_assertions.py#L25) | Controlled search assertion check | 3 | HTTP 400, 422, and 500 | 400/422 pass the scenario; 500 raises an ordinary assertion with the actual status. |
| [test_date_filter_control_failure_is_visible](../tests/unit/test_filter_assertions.py#L57) | Controlled search resilience | 1 | Positive control always returns 503 | The control failure raises AssertionError and no date-filter request is sent. Scope: A general outage must not be mistaken for successful rejection of malformed input. |

### Lifecycle assertions

Run the live assertions against controlled contract regressions, without network access.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_nested_patch_detects_corruption](../tests/unit/test_lifecycle_assertions.py#L29) | Controlled update assertion check | 6 | Correct merge, lost checkout, other corruption, missing record, 500, timeout | Only the correct nested merge passes; corruption, disappearance, or server errors raise assertions and response loss propagates ReadTimeout. Scope: This checks the scenario's ability to find defects; it does not reproduce them on a live server. |
| [test_live_update_checks_reject_type_drift](../tests/unit/test_lifecycle_assertions.py#L82) | Controlled contract regression | 8 | PUT/PATCH x response/persisted x depositpaid/totalprice | Response corruption raises AssertionError; malformed persisted state raises ValidationError, and execution stops after one write. |
| [test_create_contract_failure_keeps_id_available_for_cleanup](../tests/unit/test_lifecycle_assertions.py#L120) | Controlled creation resilience | 4 | Bad booking shape, missing booking, extra envelope field, wrong success status | Creation raises the appropriate contract/status error, registers the ID before failing, and cleanup deletes it without relying on a corrective GET. |
| [test_create_rejects_invalid_ids_without_registering_them](../tests/unit/test_lifecycle_assertions.py#L165) | Controlled identifier validation | 5 | True, zero, negative integer, numeric string, and null | BookingRegistry.create raises ValueError and leaves the ownership list empty. |
| [test_parallel_patch_scenarios_detect_regressions](../tests/unit/test_lifecycle_assertions.py#L195) | Controlled concurrency assertion check | 16 | 2 live PATCH scenarios x 8 modeled outcomes | Valid orders pass; application regressions raise AssertionError and lost responses raise ReadTimeout. Two distinct writer threads and measured release skew are verified. Scope: Transport overlap is controlled locally. These cases validate assertion logic rather than hosted race behavior. |
| [test_conflicting_put_reconciliation_rejects_invalid_outcomes](../tests/unit/test_lifecycle_assertions.py#L281) | Controlled concurrency assertion check | 11 | 11 winner, corruption, absence, drift, or status outcomes | Winner A and B each pass. Partial merges, missing dates, invalid types, unchanged state, drift, missing reads, and 409/412/500 fail with the intended assertion; outcome classification is checked. Scope: All three snapshots are collected before assertions. Conflict status alone is not proof of optimistic locking. |
| [test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes](../tests/unit/test_lifecycle_assertions.py#L360) | Controlled overwrite-policy assertion check | 8 | 2 write orders x correct/ignored/mixed/drifting state | Correct behavior selects the second writer; each injected defect raises the intended assertion after three final snapshots are captured. Scope: These are sequential control models, not concurrent server executions. |

### Resilience

Controlled retry, prerequisite recovery, and cleanup behavior without public sandbox access.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_get_retries_transient_failure_then_returns_response](../tests/unit/test_resilience.py#L14) | Controlled transport recovery | 1 | ConnectTimeout, then 503, then 200 | The third response returns 200 after exactly three attempts and delays of 0.25 and 0.5 seconds. |
| [test_get_retry_exhaustion_is_visible](../tests/unit/test_resilience.py#L40) | Controlled transport exhaustion | 1 | 3 consecutive ReadTimeout responses | ReadTimeout reaches the caller after exactly three attempts rather than being converted into a passing result. |
| [test_uncertain_writes_are_never_transport_retried](../tests/unit/test_resilience.py#L65) | Controlled safe-retry negative | 4 | POST, PUT, PATCH, and DELETE | The exception propagates after one request, with no automatic transport replay. Scope: The model does not establish whether a server committed the write; uncertainty is intentionally preserved. |
| [test_missing_prerequisite_recovery_is_bounded](../tests/unit/test_resilience.py#L93) | Controlled sandbox recovery | 2 | Replacement survives or remains missing | A surviving replacement is returned; repeated absence raises RuntimeError. Exactly two IDs are tracked, one recovery is recorded, and both IDs are attempted during cleanup. |
| [test_cleanup_attempts_all_owned_ids_and_reports_failure](../tests/unit/test_resilience.py#L135) | Controlled cleanup resilience | 1 | First DELETE returns 500; second returns 201 | Both DELETE requests are attempted in order and cleanup raises RuntimeError identifying the first ID and HTTP 500. |
| [test_connect_failure_before_send_can_be_retried](../tests/unit/test_resilience.py#L164) | Controlled safe-retry positive | 4 | POST, PUT, PATCH, and DELETE | The selected mutation returns 200 after exactly two attempts. Scope: This covers pre-send connection failure; response-loss retries remain prohibited by separate tests. |
| [test_delete_405_requires_confirmed_absence](../tests/unit/test_resilience.py#L192) | Controlled cleanup status handling | 3 | Confirming GET returns 404, 200, or 500 | Only GET 404 permits successful cleanup; a present record or failed confirmation raises RuntimeError. |
| [test_available_prerequisite_is_reused](../tests/unit/test_resilience.py#L220) | Controlled sandbox recovery positive | 1 | One available owned booking | The payload and ID are unchanged, no recovery is recorded, and the only calls are the initial POST and one GET. |
| [test_prerequisite_recovery_requires_confirmed_404](../tests/unit/test_resilience.py#L253) | Controlled sandbox recovery negative | 4 | 403, 500, ReadTimeout, and malformed JSON | The appropriate exception propagates; ID and recovery history stay unchanged and no POST occurs. ReadTimeout uses only the bounded three read attempts. |
| [test_cleanup_404_is_terminal_without_recreation](../tests/unit/test_resilience.py#L290) | Controlled cleanup positive | 1 | One already-absent owned ID | Only authentication and deletion occur, no recovery is recorded, and one cleanup event reports the ID as already absent. |
| [test_cleanup_transport_failure_still_attempts_remaining_ids](../tests/unit/test_resilience.py#L326) | Controlled cleanup resilience | 1 | First DELETE loses its response; second succeeds | Each ID is attempted once, cleanup raises an error naming the timeout, and evidence records failed then deleted outcomes. Scope: No ambiguous DELETE replay is attempted; subsequent cleanup work is still performed. |

### Security assertions

Security assertions must detect unauthorized changes and clean up test-owned ID collisions.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_unauthorized_mutation_checks_status_and_state](../tests/unit/test_security_assertions.py#L31) | Controlled security assertion check | 5 | 5 denial/success and none/update/delete combinations | Only HTTP 403 with unchanged state passes. A success response, hidden update, or deletion raises the authorization/state-preservation assertion. |
| [test_internal_id_collision_is_reported_and_cleaned](../tests/unit/test_security_assertions.py#L66) | Controlled security cleanup regression | 2 | PATCH 405 or 400 after mutating the internal ID | The live assertion fails, the cleanup registry retains the duplicate destination ID, and cleanup deletes both records sharing that ID. Scope: Only test-owned IDs are modeled; this checks failure cleanup without targeting another user's booking. |

### Validation assertions

Verify invalid-input assertions and cleanup against controlled server behavior.

| Test | Type | Cases | Parameters / setup | Expected behavior and scope |
| --- | --- | ---: | --- | --- |
| [test_invalid_input_status_state_and_cleanup](../tests/unit/test_validation_assertions.py#L28) | Controlled validation assertion check | 15 | POST/PUT/PATCH x 5 response/state behaviors | Only clean rejection passes. Other cases raise AssertionError, POST uses a distinct guest, and all returned IDs remain registered and are cleaned up. Scope: This validates the test oracle and ownership handling; it does not claim hosted validation behavior. |

## Maintaining test documentation

Keep the purpose comment short. Describe the trigger and observable pass condition
in the docstring; include meaningful parameter differences and distinguish controlled
models from live evidence. State policy assumptions where the API contract lacks a
capability. Explain non-obvious coordination, recovery, or cleanup choices inline;
avoid comments that merely repeat the next statement.

When a scenario changes, update its docstring and catalog row, including case count
and source link. Keep dated execution results in validation-results.md rather than
promising a permanent pass/fail outcome in a test description. Changes to names or
parameter IDs require review because they affect test selection and Allure history.
