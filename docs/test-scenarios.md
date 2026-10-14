# Test scenarios and implementation map

Find a scenario below, then open its implementing file or test function.
Each row describes one test function; **Cases** counts its collected parameter
variants. The expandable appendix lists every exact pytest case ID.

| Execution type | Test files | Test functions | Collected cases |
| --- | ---: | ---: | ---: |
| Live API | 8 | 39 | 135 |
| Controlled / offline | 14 | 49 | 196 |
| Total | 22 | 88 | 331 |

Verified against `python -m pytest --collect-only -q` on 15 October 2026.
Collection confirms implemented cases, not passing behavior. See the
[detailed test catalog](test-cases.md) for expected codes, assertions, and scope;
[validation results](validation-results.md) records executed outcomes.

Live cases require `--live`; real token-expiry cases additionally require a
documented TTL and suitable target ([expiry setup](technical-defense.md#real-token-expiry)).
Controlled cases include actual schema checks and Allure subprocess integrations,
as well as modeled server behavior. A controlled pass does not establish live
API behavior. [Requirement mapping and limits](requirements-coverage.md)

## File index

Select a file name to jump to its scenarios. Each section links to the source file.

| Test file | Functions | Cases |
| --- | ---: | ---: |
| [tests/live/test_auth_expiry.py](#live-token-expiry) | 1 | 3 |
| [tests/live/test_auth_sessions.py](#live-authentication-sessions) | 7 | 28 |
| [tests/live/test_capabilities.py](#live-duplicate-booking-rejection) | 1 | 1 |
| [tests/live/test_filters.py](#live-booking-filters) | 3 | 4 |
| [tests/live/test_idempotency.py](#live-idempotency) | 4 | 6 |
| [tests/live/test_lifecycle.py](#live-booking-lifecycle-and-concurrency) | 13 | 18 |
| [tests/live/test_smoke.py](#live-api-health) | 1 | 1 |
| [tests/live/test_validation.py](#live-booking-validation) | 9 | 74 |
| [tests/unit/test_allure_statuses.py](#controlled-allure-integration) | 2 | 10 |
| [tests/unit/test_auth.py](#controlled-authentication) | 4 | 5 |
| [tests/unit/test_auth_lifecycle.py](#controlled-token-lifecycle) | 3 | 13 |
| [tests/unit/test_client.py](#controlled-http-client) | 1 | 1 |
| [tests/unit/test_commit_boundary_simulation.py](#controlled-commit-failures) | 1 | 8 |
| [tests/unit/test_contract.py](#controlled-schema-and-invariants) | 6 | 32 |
| [tests/unit/test_coverage_reporting.py](#controlled-coverage-accounting) | 1 | 1 |
| [tests/unit/test_duplicate_context.py](#controlled-duplicate-checks) | 1 | 9 |
| [tests/unit/test_evidence.py](#controlled-evidence-and-redaction) | 7 | 10 |
| [tests/unit/test_filter_assertions.py](#controlled-filter-assertions) | 2 | 4 |
| [tests/unit/test_lifecycle_assertions.py](#controlled-lifecycle-assertions) | 7 | 58 |
| [tests/unit/test_resilience.py](#controlled-retry-and-cleanup) | 11 | 23 |
| [tests/unit/test_security_assertions.py](#controlled-security-assertions) | 2 | 7 |
| [tests/unit/test_validation_assertions.py](#controlled-validation-assertions) | 1 | 15 |

## Live API scenarios

### Live token expiry

**Implemented in:** [tests/live/test_auth_expiry.py](../tests/live/test_auth_expiry.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| An aged server-issued token must be rejected, with bounded recovery when requested. | [test_real_token_expiry_and_reauthentication](../tests/live/test_auth_expiry.py#L105) | 3 | 0, 1, or 4 recovery callers. |

### Live authentication sessions

**Implemented in:** [tests/live/test_auth_sessions.py](../tests/live/test_auth_sessions.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| A newly issued token must authorize a complete, persisted booking update. | [test_valid_login_authorizes_booking_update](../tests/live/test_auth_sessions.py#L16) | 1 | One valid login. |
| Invalid credential combinations must return the documented denial body without a token. | [test_auth_rejects_invalid_credentials](../tests/live/test_auth_sessions.py#L44) | 3 | Wrong password, empty credentials, missing credentials. |
| Unusable token cookies must not authorize mutations or change the stored booking. | [test_protected_mutations_reject_bad_tokens](../tests/live/test_auth_sessions.py#L92) | 12 | 4 token cases x PUT/PATCH/DELETE. |
| JavaScript prototype-property names must not be accepted as authentication tokens. | [test_inherited_property_tokens_are_rejected](../tests/live/test_auth_sessions.py#L122) | 9 | toString/constructor/__proto__ x PUT/PATCH/DELETE. |
| Four independent sessions must each receive a usable token for their own booking. | [test_parallel_independent_logins_issue_usable_tokens](../tests/live/test_auth_sessions.py#L141) | 1 | 4 clients and 4 owned bookings. |
| A unique unknown username must receive a credential denial without a token. | [test_auth_rejects_nonexistent_user](../tests/live/test_auth_sessions.py#L196) | 1 | One generated nonexistent username. |
| The requested single-session policy must reject the previous token after a new login. | [test_new_login_invalidates_previous_token](../tests/live/test_auth_sessions.py#L287) | 1 | 2 clients using the same credentials. |

### Live duplicate booking rejection

**Implemented in:** [tests/live/test_capabilities.py](../tests/live/test_capabilities.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| An identical calculated date-range booking must be rejected in the second session. | [test_business_duplicate_rejection](../tests/live/test_capabilities.py#L68) | 1 | 2 independently authenticated sessions. |

### Live booking filters

**Implemented in:** [tests/live/test_filters.py](../tests/live/test_filters.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Check-in filtering must include the exact date boundary and exclude later thresholds. | [test_checkin_filter_includes_boundary](../tests/live/test_filters.py#L32) | 1 | Thresholds one day before, equal to, and one day after check-in. |
| Checkout filtering must apply the documented inclusive lower-bound comparison. | [test_checkout_filter_uses_documented_direction](../tests/live/test_filters.py#L54) | 1 | Thresholds one day before, equal to, and one day after checkout. |
| Malformed date filters must fail validation while valid searches remain available. | [test_malformed_date_filter_returns_client_error](../tests/live/test_filters.py#L77) | 2 | checkin and checkout. |

### Live idempotency

**Implemented in:** [tests/live/test_idempotency.py](../tests/live/test_idempotency.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Repeated identical full updates must preserve the same observable booking state. | [test_sequential_identical_put_preserves_observable_state](../tests/live/test_idempotency.py#L54) | 2 | 2 and 5 consecutive PUTs. |
| Assigning the same price three times must preserve the full expected booking. | [test_repeated_set_value_patch_preserves_observable_state](../tests/live/test_idempotency.py#L72) | 1 | 3 totalprice assignments. |
| Identical concurrent writers must converge on the single-request target payload. | [test_concurrent_identical_put_preserves_observable_state](../tests/live/test_idempotency.py#L92) | 2 | 2 and 4 synchronized writers. |
| Repeated deletion must leave the booking absent even when response codes differ. | [test_repeated_delete_keeps_booking_absent](../tests/live/test_idempotency.py#L145) | 1 | 3 DELETE requests with a GET after each. |

### Live booking lifecycle and concurrency

**Implemented in:** [tests/live/test_lifecycle.py](../tests/live/test_lifecycle.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| A created booking must round-trip with its complete contract and valid business values. | [test_create_contract](../tests/live/test_lifecycle.py#L30) | 1 | One generated valid booking. |
| Three identical PUTs must produce three identical valid persisted snapshots. | [test_put_three_times_is_idempotent](../tests/live/test_lifecycle.py#L47) | 1 | Exactly 3 consecutive PUTs. |
| A price-only PATCH must leave all unreferenced booking fields unchanged. | [test_patch_preserves_every_untouched_field](../tests/live/test_lifecycle.py#L82) | 1 | Only totalprice changes. |
| A check-in-only nested PATCH must preserve checkout and all unrelated fields. | [test_nested_patch_preserves_checkout](../tests/live/test_lifecycle.py#L113) | 1 | Only bookingdates.checkin changes. |
| Supported mutation routes must report missing resources and keep them absent. | [test_missing_resource_mutation_reports_absence](../tests/live/test_lifecycle.py#L147) | 3 | PUT, PATCH, and DELETE after confirmed deletion. |
| A rejected cached token must allow the protected update to recover successfully. | [test_invalid_token_is_refreshed](../tests/live/test_lifecycle.py#L180) | 1 | Deliberately invalid cached token. |
| A purged prerequisite must be recreated once so the protected scenario can continue. | [test_missing_prerequisite_is_recreated](../tests/live/test_lifecycle.py#L218) | 1 | Independent-client deletion followed by one recreation. |
| Cleanup must handle an already-absent booking and continue through every owned ID. | [test_sandbox_cleanup_handles_external_purge](../tests/live/test_lifecycle.py#L257) | 1 | 2 owned records; first removed through a separate client. |
| Conflicting full updates must settle on one complete payload that stays stable. | [test_conflicting_updates_reconcile_to_one_complete_payload](../tests/live/test_lifecycle.py#L346) | 3 | 3 rounds, each with 2 synchronized PUT writers. |
| With a known write order, the second complete PUT must be the stable winner. | [test_ordered_conflicting_put_uses_last_completed_write](../tests/live/test_lifecycle.py#L407) | 2 | A_then_B and B_then_A. |
| Conflicting price PATCHes must preserve one submitted value and every untouched field. | [test_conflicting_patch_preserves_one_price_and_untouched_fields](../tests/live/test_lifecycle.py#L491) | 1 | 2 synchronized PATCH writers: prices 250 and 850. |
| Concurrent PATCHes to separate fields must preserve both changes without drift. | [test_concurrent_patch_preserves_both_independent_changes](../tests/live/test_lifecycle.py#L524) | 1 | 2 synchronized writers: totalprice and lastname. |
| Four simultaneous setup callers must share one successful live token issuance. | [test_parallel_setup_acquires_one_live_token](../tests/live/test_lifecycle.py#L563) | 1 | 4 threads sharing one AuthManager. |

### Live API health

**Implemented in:** [tests/live/test_smoke.py](../tests/live/test_smoke.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| The sandbox health endpoint must return its documented healthy status. | [test_api_health](../tests/live/test_smoke.py#L8) | 1 | GET /ping. |

### Live booking validation

**Implemented in:** [tests/live/test_validation.py](../tests/live/test_validation.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Invalid scalar and nested values must be rejected without altering the owned booking. | [test_updates_reject_invalid_field_types](../tests/live/test_validation.py#L83) | 30 | 15 invalid field cases x PUT/PATCH. |
| Creation must reject invalid field representations without producing a booking. | [test_creates_reject_invalid_field_types](../tests/live/test_validation.py#L103) | 15 | 15 invalid field cases sent with POST. |
| Complete create and replace requests must include both nested booking dates. | [test_full_requests_require_both_dates](../tests/live/test_validation.py#L124) | 4 | Missing checkin/checkout x POST/PUT. |
| Every write operation must reject invalid date order and negative prices. | [test_business_invalid_values_rejected](../tests/live/test_validation.py#L144) | 9 | Reversed dates/equal dates/negative price x POST/PUT/PATCH. |
| Calculated totals and boolean deposit flags must survive complete write/read workflows. | [test_calculated_price_and_deposit_round_trip](../tests/live/test_validation.py#L171) | 4 | 4 night/rate/deposit combinations, including zero price and both flags. |
| Client PATCHes must not replace internal identity or storage metadata. | [test_patch_rejects_internal_fields](../tests/live/test_validation.py#L216) | 2 | bookingid and meta. |
| Malformed IDs must not resolve to or mutate their valid numeric prefix. | [test_resource_ids_require_exact_integer](../tests/live/test_validation.py#L253) | 8 | Text/fractional suffixes x GET/PUT/PATCH/DELETE. |
| Invalid price and boolean strings must be rejected together without coercing stored values. | [test_patch_rejects_invalid_types_without_mutation](../tests/live/test_validation.py#L280) | 1 | totalprice='abc' and depositpaid='false'. |
| An incomplete POST must produce a validation error while valid creation still works. | [test_incomplete_post_returns_client_error](../tests/live/test_validation.py#L309) | 1 | POST containing only firstname. |

## Controlled framework scenarios

### Controlled Allure integration

**Implemented in:** [tests/unit/test_allure_statuses.py](../tests/unit/test_allure_statuses.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Allure status and pytest exit codes must preserve every intentional test outcome. | [test_adapter_preserves_status_and_exit_code](../tests/unit/test_allure_statuses.py#L21) | 7 | PASS, SKIP, XFAIL, XPASS, assertion, exception, teardown failure. |
| Fixture and assertion failures must retain sanitized HTTP and lifecycle evidence. | [test_evidence_survives_real_fixture_failures](../tests/unit/test_allure_statuses.py#L53) | 3 | Failure during call, setup, or teardown. |

### Controlled authentication

**Implemented in:** [tests/unit/test_auth.py](../tests/unit/test_auth.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Eight simultaneous callers must share one token issuance while the issuer is blocked. | [test_parallel_initial_acquisition_is_single_flight](../tests/unit/test_auth.py#L17) | 1 | 8 threads and one blocked issuer callback. |
| Concurrent rejection of one cached token must trigger one shared replacement. | [test_concurrent_rejection_refreshes_once](../tests/unit/test_auth.py#L73) | 2 | 401 and 403; 4 callers each. |
| Persistent forbidden responses must stop after one refresh and one replay. | [test_persistent_forbidden_refresh_is_bounded](../tests/unit/test_auth.py#L112) | 1 | Protected PUT always returns 403. |
| A credential-denial body must not populate the token cache. | [test_authentication_failure_does_not_cache_missing_token](../tests/unit/test_auth.py#L139) | 1 | 2 acquisition attempts without a returned token. |

### Controlled token lifecycle

**Implemented in:** [tests/unit/test_auth_lifecycle.py](../tests/unit/test_auth_lifecycle.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| The expiry workflow must handle both rejection codes and each recovery mode. | [test_token_expiry_workflow_with_controlled_clock](../tests/unit/test_auth_lifecycle.py#L82) | 6 | 401/403 x 0/1/4 recovery callers. |
| The expiry assertions must reject non-expiration, outages, unauthorized mutation, and failed recovery. | [test_token_expiry_workflow_detects_failures](../tests/unit/test_auth_lifecycle.py#L102) | 5 | Never expires, server error, rejection mutates, fresh failure, recovery rejection. |
| Revocation assertions must distinguish rejected old tokens from still-valid sessions. | [test_new_login_policy_assertion_without_automatic_refresh](../tests/unit/test_auth_lifecycle.py#L123) | 2 | Revoking and non-revoking token models. |

### Controlled HTTP client

**Implemented in:** [tests/unit/test_client.py](../tests/unit/test_client.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| An explicitly unauthenticated request must return its negative response unchanged. | [test_negative_response_is_preserved_without_retry](../tests/unit/test_client.py#L9) | 1 | One PUT returning 403. |

### Controlled commit failures

**Implemented in:** [tests/unit/test_commit_boundary_simulation.py](../tests/unit/test_commit_boundary_simulation.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| A lost mutation response must propagate uncertainty without replaying the write. | [test_lost_response_reports_uncertainty_without_replaying_mutation](../tests/unit/test_commit_boundary_simulation.py#L16) | 8 | POST/PUT/PATCH/DELETE x before/after simulated commit. |

### Controlled schema and invariants

**Implemented in:** [tests/unit/test_contract.py](../tests/unit/test_contract.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Generated test data must satisfy the schema and booking invariants before use. | [test_generated_payload_has_valid_contract_and_business_invariants](../tests/unit/test_contract.py#L11) | 1 | One generated payload. |
| Strict schema validation must reject coercible values and malformed booking structures. | [test_contract_rejects_malformed_wire_values](../tests/unit/test_contract.py#L39) | 19 | 19 malformed scalar, nested, date, or extra-field changes. |
| Valid date strings must still fail the booking rule when checkout is not later. | [test_date_order_is_a_separate_business_invariant](../tests/unit/test_contract.py#L62) | 2 | Equal and reversed dates. |
| A negative integer price must fail the business rule despite a valid wire type. | [test_negative_price_is_a_separate_business_invariant](../tests/unit/test_contract.py#L80) | 1 | totalprice = -1. |
| Valid calendar boundaries, zero price, and both deposit flags must remain accepted. | [test_contract_accepts_valid_calendar_and_value_boundaries](../tests/unit/test_contract.py#L103) | 3 | 3 leap-day/year-end/price/deposit combinations. |
| Identical expected and actual JSON must not allow invalid bookings to pass. | [test_matching_payloads_still_require_contract_and_invariants](../tests/unit/test_contract.py#L125) | 6 | 6 invalid price, flag, date-format, or date-order changes. |

### Controlled coverage accounting

**Implemented in:** [tests/unit/test_coverage_reporting.py](../tests/unit/test_coverage_reporting.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Coverage totals must distinguish collected cases, executed cases, and passing cases. | [test_scoped_coverage_never_counts_skips_or_failures_as_passes](../tests/unit/test_coverage_reporting.py#L7) | 1 | Synthetic passed/skipped/broken/failed results plus an excluded conflict test. |

### Controlled duplicate checks

**Implemented in:** [tests/unit/test_duplicate_context.py](../tests/unit/test_duplicate_context.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Duplicate assertions must distinguish real rejection from acceptance or hidden mutation. | [test_duplicate_context_and_failure_classification](../tests/unit/test_duplicate_context.py#L30) | 9 | 9 duplicate response/state outcomes. |

### Controlled evidence and redaction

**Implemented in:** [tests/unit/test_evidence.py](../tests/unit/test_evidence.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Retry and refresh warnings must retain useful paths without leaking URL or token secrets. | [test_warning_logs_exclude_url_secrets](../tests/unit/test_evidence.py#L17) | 4 | Connect failure, 503, 401, and 403. |
| Collected HTTP evidence must redact secrets while preserving useful booking data. | [test_auth_bodies_headers_and_query_secrets_never_enter_evidence](../tests/unit/test_evidence.py#L60) | 1 | Secrets in auth, request JSON, response JSON, and query. |
| Concurrent evidence collection must retain every event and isolate returned snapshots. | [test_collector_keeps_all_thread_events_and_snapshot_is_detached](../tests/unit/test_evidence.py#L92) | 1 | 100 events from 8 worker threads. |
| Secret-key matching must work inside nested sequences regardless of key casing. | [test_sanitizer_handles_case_and_nested_sequences](../tests/unit/test_evidence.py#L112) | 1 | Mixed-case Authorization and Cookie keys inside a list. |
| JSON differences must preserve paths, types, and presence without exposing secret values. | [test_diffs_distinguish_nested_changes_types_missing_and_null_without_leaking_secrets](../tests/unit/test_evidence.py#L127) | 1 | Nested date, bool/int, missing/null, list addition, and token changes. |
| Retry evidence must correlate attempts and expose only allowed response headers. | [test_retry_and_refresh_events_correlate_attempts_and_exclude_sensitive_headers](../tests/unit/test_evidence.py#L156) | 1 | ConnectTimeout, then 503, then 200. |
| Refresh evidence must record the rejection trigger while omitting issued tokens. | [test_auth_refresh_event_records_trigger_and_never_the_token](../tests/unit/test_evidence.py#L199) | 1 | One 403 followed by a successful refreshed PUT. |

### Controlled filter assertions

**Implemented in:** [tests/unit/test_filter_assertions.py](../tests/unit/test_filter_assertions.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Malformed-filter assertions must accept validation errors and reject server failures. | [test_malformed_filter_requires_client_error](../tests/unit/test_filter_assertions.py#L25) | 3 | HTTP 400, 422, and 500. |
| A failed positive search control must stop malformed-filter validation immediately. | [test_date_filter_control_failure_is_visible](../tests/unit/test_filter_assertions.py#L57) | 1 | Positive control always returns 503. |

### Controlled lifecycle assertions

**Implemented in:** [tests/unit/test_lifecycle_assertions.py](../tests/unit/test_lifecycle_assertions.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Nested-PATCH assertions must detect damaged state and request failures. | [test_nested_patch_detects_corruption](../tests/unit/test_lifecycle_assertions.py#L29) | 6 | Correct merge, lost checkout, other corruption, missing record, 500, timeout. |
| PUT and PATCH assertions must reject numeric coercion in responses or persisted state. | [test_live_update_checks_reject_type_drift](../tests/unit/test_lifecycle_assertions.py#L82) | 8 | PUT/PATCH x response/persisted x depositpaid/totalprice. |
| A malformed creation result must fail while preserving its returned ID for cleanup. | [test_create_contract_failure_keeps_id_available_for_cleanup](../tests/unit/test_lifecycle_assertions.py#L120) | 4 | Bad booking shape, missing booking, extra envelope field, wrong success status. |
| Invalid returned booking IDs must never become cleanup targets. | [test_create_rejects_invalid_ids_without_registering_them](../tests/unit/test_lifecycle_assertions.py#L165) | 5 | True, zero, negative integer, numeric string, and null. |
| Concurrent PATCH assertions must allow either write order and expose lost or corrupt updates. | [test_parallel_patch_scenarios_detect_regressions](../tests/unit/test_lifecycle_assertions.py#L195) | 16 | 2 live PATCH scenarios x 8 modeled outcomes. |
| Reconciliation must accept either complete winner and reject mixed, unstable, or rejected outcomes. | [test_conflicting_put_reconciliation_rejects_invalid_outcomes](../tests/unit/test_lifecycle_assertions.py#L281) | 11 | 11 winner, corruption, absence, drift, or status outcomes. |
| Ordered overwrite controls must detect ignored second writes, mixed payloads, and drift. | [test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes](../tests/unit/test_lifecycle_assertions.py#L360) | 8 | 2 write orders x correct/ignored/mixed/drifting state. |

### Controlled retry and cleanup

**Implemented in:** [tests/unit/test_resilience.py](../tests/unit/test_resilience.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| A transient read failure must retry with bounded exponential backoff. | [test_get_retries_transient_failure_then_returns_response](../tests/unit/test_resilience.py#L14) | 1 | ConnectTimeout, then 503, then 200. |
| Repeated read timeouts must stop at the configured attempt limit. | [test_get_retry_exhaustion_is_visible](../tests/unit/test_resilience.py#L40) | 1 | 3 consecutive ReadTimeout responses. |
| A mutation with an unknown outcome must not be blindly replayed. | [test_uncertain_writes_are_never_transport_retried](../tests/unit/test_resilience.py#L65) | 4 | POST, PUT, PATCH, and DELETE. |
| Missing prerequisites must be recreated once, with exhaustion remaining visible. | [test_missing_prerequisite_recovery_is_bounded](../tests/unit/test_resilience.py#L93) | 2 | Replacement survives or remains missing. |
| Cleanup must continue after one HTTP failure and report the failed owned ID. | [test_cleanup_attempts_all_owned_ids_and_reports_failure](../tests/unit/test_resilience.py#L135) | 1 | First DELETE returns 500; second returns 201. |
| A confirmed connection-establishment failure may retry a mutation before it is sent. | [test_connect_failure_before_send_can_be_retried](../tests/unit/test_resilience.py#L164) | 4 | POST, PUT, PATCH, and DELETE. |
| Cleanup may tolerate DELETE 405 only when GET confirms that the record is absent. | [test_delete_405_requires_confirmed_absence](../tests/unit/test_resilience.py#L192) | 3 | Confirming GET returns 404, 200, or 500. |
| A present prerequisite must retain its ID and payload without extra creation. | [test_available_prerequisite_is_reused](../tests/unit/test_resilience.py#L220) | 1 | One available owned booking. |
| Recovery must not mistake authorization, server, transport, or JSON failures for a purge. | [test_prerequisite_recovery_requires_confirmed_404](../tests/unit/test_resilience.py#L253) | 4 | 403, 500, ReadTimeout, and malformed JSON. |
| DELETE 404 must finish cleanup without a confirmation GET or replacement POST. | [test_cleanup_404_is_terminal_without_recreation](../tests/unit/test_resilience.py#L290) | 1 | One already-absent owned ID. |
| An uncertain deletion must remain visible while cleanup proceeds to the next owned ID. | [test_cleanup_transport_failure_still_attempts_remaining_ids](../tests/unit/test_resilience.py#L326) | 1 | First DELETE loses its response; second succeeds. |

### Controlled security assertions

**Implemented in:** [tests/unit/test_security_assertions.py](../tests/unit/test_security_assertions.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| An authorization denial must pass only when the protected record is unchanged. | [test_unauthorized_mutation_checks_status_and_state](../tests/unit/test_security_assertions.py#L31) | 5 | 5 denial/success and none/update/delete combinations. |
| An internal-ID collision must fail validation while leaving both aliased records cleanable. | [test_internal_id_collision_is_reported_and_cleaned](../tests/unit/test_security_assertions.py#L66) | 2 | PATCH 405 or 400 after mutating the internal ID. |

### Controlled validation assertions

**Implemented in:** [tests/unit/test_validation_assertions.py](../tests/unit/test_validation_assertions.py)

| Scenario / pass condition | Test function | Cases | Parameters / setup |
| --- | --- | ---: | --- |
| Invalid-input assertions must require both correct rejection and preserved state. | [test_invalid_input_status_state_and_cleanup](../tests/unit/test_validation_assertions.py#L28) | 15 | POST/PUT/PATCH x 5 response/state behaviors. |

## Run a mapped scenario

After [environment setup](../README.md#setup), run a file, a function, or one exact
parameterized case. A function selector runs all variants of that function.

```sh
python -m pytest tests/unit/test_auth.py
python -m pytest tests/live/test_lifecycle.py::test_put_three_times_is_idempotent --live
python -m pytest 'tests/live/test_idempotency.py::test_concurrent_identical_put_preserves_observable_state[2]' --live
```

## Exact collected cases

These selectors expand every function above into its collected cases. Quote a
selector when running one variant. Automatically numbered IDs such as `change0`
refer to the parameter values in the linked source function.

<details>
<summary>Show all 331 pytest case IDs</summary>

```text
tests/live/test_auth_expiry.py::test_real_token_expiry_and_reauthentication[reject-expired]
tests/live/test_auth_expiry.py::test_real_token_expiry_and_reauthentication[refresh-sequential]
tests/live/test_auth_expiry.py::test_real_token_expiry_and_reauthentication[refresh-concurrent]
tests/live/test_auth_sessions.py::test_valid_login_authorizes_booking_update
tests/live/test_auth_sessions.py::test_auth_rejects_invalid_credentials[wrong_password]
tests/live/test_auth_sessions.py::test_auth_rejects_invalid_credentials[empty_credentials]
tests/live/test_auth_sessions.py::test_auth_rejects_invalid_credentials[missing_credentials]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[missing-PUT]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[missing-PATCH]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[missing-DELETE]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[empty-PUT]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[empty-PATCH]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[empty-DELETE]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[unissued-PUT]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[unissued-PATCH]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[unissued-DELETE]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[modified-PUT]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[modified-PATCH]
tests/live/test_auth_sessions.py::test_protected_mutations_reject_bad_tokens[modified-DELETE]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[toString-PUT]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[toString-PATCH]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[toString-DELETE]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[constructor-PUT]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[constructor-PATCH]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[constructor-DELETE]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[__proto__-PUT]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[__proto__-PATCH]
tests/live/test_auth_sessions.py::test_inherited_property_tokens_are_rejected[__proto__-DELETE]
tests/live/test_auth_sessions.py::test_parallel_independent_logins_issue_usable_tokens
tests/live/test_auth_sessions.py::test_auth_rejects_nonexistent_user
tests/live/test_auth_sessions.py::test_new_login_invalidates_previous_token
tests/live/test_capabilities.py::test_business_duplicate_rejection
tests/live/test_filters.py::test_checkin_filter_includes_boundary
tests/live/test_filters.py::test_checkout_filter_uses_documented_direction
tests/live/test_filters.py::test_malformed_date_filter_returns_client_error[checkin]
tests/live/test_filters.py::test_malformed_date_filter_returns_client_error[checkout]
tests/live/test_idempotency.py::test_sequential_identical_put_preserves_observable_state[2]
tests/live/test_idempotency.py::test_sequential_identical_put_preserves_observable_state[5]
tests/live/test_idempotency.py::test_repeated_set_value_patch_preserves_observable_state
tests/live/test_idempotency.py::test_concurrent_identical_put_preserves_observable_state[2]
tests/live/test_idempotency.py::test_concurrent_identical_put_preserves_observable_state[4]
tests/live/test_idempotency.py::test_repeated_delete_keeps_booking_absent
tests/live/test_lifecycle.py::test_create_contract
tests/live/test_lifecycle.py::test_put_three_times_is_idempotent
tests/live/test_lifecycle.py::test_patch_preserves_every_untouched_field
tests/live/test_lifecycle.py::test_nested_patch_preserves_checkout
tests/live/test_lifecycle.py::test_missing_resource_mutation_reports_absence[PUT]
tests/live/test_lifecycle.py::test_missing_resource_mutation_reports_absence[PATCH]
tests/live/test_lifecycle.py::test_missing_resource_mutation_reports_absence[DELETE]
tests/live/test_lifecycle.py::test_invalid_token_is_refreshed
tests/live/test_lifecycle.py::test_missing_prerequisite_is_recreated
tests/live/test_lifecycle.py::test_sandbox_cleanup_handles_external_purge
tests/live/test_lifecycle.py::test_conflicting_updates_reconcile_to_one_complete_payload[0]
tests/live/test_lifecycle.py::test_conflicting_updates_reconcile_to_one_complete_payload[1]
tests/live/test_lifecycle.py::test_conflicting_updates_reconcile_to_one_complete_payload[2]
tests/live/test_lifecycle.py::test_ordered_conflicting_put_uses_last_completed_write[A_then_B]
tests/live/test_lifecycle.py::test_ordered_conflicting_put_uses_last_completed_write[B_then_A]
tests/live/test_lifecycle.py::test_conflicting_patch_preserves_one_price_and_untouched_fields
tests/live/test_lifecycle.py::test_concurrent_patch_preserves_both_independent_changes
tests/live/test_lifecycle.py::test_parallel_setup_acquires_one_live_token
tests/live/test_smoke.py::test_api_health
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_string-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_string-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_boolean-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_boolean-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_fractional-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_fractional-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_null-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[price_null-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_string-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_string-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_number-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_number-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_null-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[boolean_null-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_null-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_null-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_array-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_array-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_string-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[dates_string-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkin_invalid-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkin_invalid-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkin_timestamp-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkin_timestamp-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkout_number-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkout_number-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkout_impossible-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[checkout_impossible-PATCH]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[firstname_number-PUT]
tests/live/test_validation.py::test_updates_reject_invalid_field_types[firstname_number-PATCH]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[price_string]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[price_boolean]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[price_fractional]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[price_null]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[boolean_string]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[boolean_number]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[boolean_null]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[dates_null]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[dates_array]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[dates_string]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[checkin_invalid]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[checkin_timestamp]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[checkout_number]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[checkout_impossible]
tests/live/test_validation.py::test_creates_reject_invalid_field_types[firstname_number]
tests/live/test_validation.py::test_full_requests_require_both_dates[checkin-POST]
tests/live/test_validation.py::test_full_requests_require_both_dates[checkin-PUT]
tests/live/test_validation.py::test_full_requests_require_both_dates[checkout-POST]
tests/live/test_validation.py::test_full_requests_require_both_dates[checkout-PUT]
tests/live/test_validation.py::test_business_invalid_values_rejected[reversed_dates-POST]
tests/live/test_validation.py::test_business_invalid_values_rejected[reversed_dates-PUT]
tests/live/test_validation.py::test_business_invalid_values_rejected[reversed_dates-PATCH]
tests/live/test_validation.py::test_business_invalid_values_rejected[equal_dates-POST]
tests/live/test_validation.py::test_business_invalid_values_rejected[equal_dates-PUT]
tests/live/test_validation.py::test_business_invalid_values_rejected[equal_dates-PATCH]
tests/live/test_validation.py::test_business_invalid_values_rejected[negative_price-POST]
tests/live/test_validation.py::test_business_invalid_values_rejected[negative_price-PUT]
tests/live/test_validation.py::test_business_invalid_values_rejected[negative_price-PATCH]
tests/live/test_validation.py::test_calculated_price_and_deposit_round_trip[1-0-False]
tests/live/test_validation.py::test_calculated_price_and_deposit_round_trip[1-1-True]
tests/live/test_validation.py::test_calculated_price_and_deposit_round_trip[3-125-False]
tests/live/test_validation.py::test_calculated_price_and_deposit_round_trip[7-199-True]
tests/live/test_validation.py::test_patch_rejects_internal_fields[bookingid]
tests/live/test_validation.py::test_patch_rejects_internal_fields[meta]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[text-suffix-GET]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[text-suffix-PUT]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[text-suffix-PATCH]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[text-suffix-DELETE]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[fractional-id-GET]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[fractional-id-PUT]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[fractional-id-PATCH]
tests/live/test_validation.py::test_resource_ids_require_exact_integer[fractional-id-DELETE]
tests/live/test_validation.py::test_patch_rejects_invalid_types_without_mutation
tests/live/test_validation.py::test_incomplete_post_returns_client_error
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[def test_probe(): pass-passed-0]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[@pytest.mark.skip(reason='ordinary skip')\ndef test_probe(): pass-skipped-0]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[@pytest.mark.xfail(strict=True, reason='known gap')\ndef test_probe(): assert False-skipped-0]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[@pytest.mark.xfail(strict=True, reason='known gap')\ndef test_probe(): pass-failed-1]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[def test_probe(): assert False-failed-1]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[def test_probe(): raise RuntimeError('transport simulation')-broken-1]
tests/unit/test_allure_statuses.py::test_adapter_preserves_status_and_exit_code[@pytest.fixture\ndef resource():\n    yield\n    raise RuntimeError('cleanup failure')\ndef test_probe(resource): pass-broken-1]
tests/unit/test_allure_statuses.py::test_evidence_survives_real_fixture_failures[call]
tests/unit/test_allure_statuses.py::test_evidence_survives_real_fixture_failures[setup]
tests/unit/test_allure_statuses.py::test_evidence_survives_real_fixture_failures[teardown]
tests/unit/test_auth.py::test_parallel_initial_acquisition_is_single_flight
tests/unit/test_auth.py::test_concurrent_rejection_refreshes_once[401]
tests/unit/test_auth.py::test_concurrent_rejection_refreshes_once[403]
tests/unit/test_auth.py::test_persistent_forbidden_refresh_is_bounded
tests/unit/test_auth.py::test_authentication_failure_does_not_cache_missing_token
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[401-0]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[401-1]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[401-4]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[403-0]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[403-1]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_with_controlled_clock[403-4]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_detects_failures[never_expires]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_detects_failures[server_error]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_detects_failures[rejection_mutates]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_detects_failures[fresh_failure]
tests/unit/test_auth_lifecycle.py::test_token_expiry_workflow_detects_failures[recovery_rejected]
tests/unit/test_auth_lifecycle.py::test_new_login_policy_assertion_without_automatic_refresh[True]
tests/unit/test_auth_lifecycle.py::test_new_login_policy_assertion_without_automatic_refresh[False]
tests/unit/test_client.py::test_negative_response_is_preserved_without_retry
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[before-commit-POST]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[before-commit-PUT]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[before-commit-PATCH]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[before-commit-DELETE]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[after-commit-POST]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[after-commit-PUT]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[after-commit-PATCH]
tests/unit/test_commit_boundary_simulation.py::test_lost_response_reports_uncertainty_without_replaying_mutation[after-commit-DELETE]
tests/unit/test_contract.py::test_generated_payload_has_valid_contract_and_business_invariants
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change0]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change1]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change2]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change3]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change4]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change5]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change6]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change7]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change8]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change9]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change10]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change11]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change12]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change13]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change14]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change15]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change16]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change17]
tests/unit/test_contract.py::test_contract_rejects_malformed_wire_values[change18]
tests/unit/test_contract.py::test_date_order_is_a_separate_business_invariant[dates0]
tests/unit/test_contract.py::test_date_order_is_a_separate_business_invariant[dates1]
tests/unit/test_contract.py::test_negative_price_is_a_separate_business_invariant
tests/unit/test_contract.py::test_contract_accepts_valid_calendar_and_value_boundaries[2028-02-28-2028-03-01-0-False]
tests/unit/test_contract.py::test_contract_accepts_valid_calendar_and_value_boundaries[2028-02-29-2028-03-01-1-True]
tests/unit/test_contract.py::test_contract_accepts_valid_calendar_and_value_boundaries[2028-12-31-2029-01-01-200-False]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change0]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change1]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change2]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change3]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change4]
tests/unit/test_contract.py::test_matching_payloads_still_require_contract_and_invariants[change5]
tests/unit/test_coverage_reporting.py::test_scoped_coverage_never_counts_skips_or_failures_as_passes
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[accepted]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[reject_400]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[reject_409]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[server_error]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[malformed_acceptance]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[rejection_mutates_original]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[accepted_201]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[rejection_creates_duplicate]
tests/unit/test_duplicate_context.py::test_duplicate_context_and_failure_classification[success_with_error_text]
tests/unit/test_evidence.py::test_warning_logs_exclude_url_secrets[connect]
tests/unit/test_evidence.py::test_warning_logs_exclude_url_secrets[503]
tests/unit/test_evidence.py::test_warning_logs_exclude_url_secrets[401]
tests/unit/test_evidence.py::test_warning_logs_exclude_url_secrets[403]
tests/unit/test_evidence.py::test_auth_bodies_headers_and_query_secrets_never_enter_evidence
tests/unit/test_evidence.py::test_collector_keeps_all_thread_events_and_snapshot_is_detached
tests/unit/test_evidence.py::test_sanitizer_handles_case_and_nested_sequences
tests/unit/test_evidence.py::test_diffs_distinguish_nested_changes_types_missing_and_null_without_leaking_secrets
tests/unit/test_evidence.py::test_retry_and_refresh_events_correlate_attempts_and_exclude_sensitive_headers
tests/unit/test_evidence.py::test_auth_refresh_event_records_trigger_and_never_the_token
tests/unit/test_filter_assertions.py::test_malformed_filter_requires_client_error[400]
tests/unit/test_filter_assertions.py::test_malformed_filter_requires_client_error[422]
tests/unit/test_filter_assertions.py::test_malformed_filter_requires_client_error[500]
tests/unit/test_filter_assertions.py::test_date_filter_control_failure_is_visible
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[fixed]
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[lost_checkout]
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[other_corruption]
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[missing]
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[server_error]
tests/unit/test_lifecycle_assertions.py::test_nested_patch_detects_corruption[timeout]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[depositpaid-response-put]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[depositpaid-response-patch]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[depositpaid-persisted-put]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[depositpaid-persisted-patch]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[totalprice-response-put]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[totalprice-response-patch]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[totalprice-persisted-put]
tests/unit/test_lifecycle_assertions.py::test_live_update_checks_reject_type_drift[totalprice-persisted-patch]
tests/unit/test_lifecycle_assertions.py::test_create_contract_failure_keeps_id_available_for_cleanup[booking_shape]
tests/unit/test_lifecycle_assertions.py::test_create_contract_failure_keeps_id_available_for_cleanup[missing_booking]
tests/unit/test_lifecycle_assertions.py::test_create_contract_failure_keeps_id_available_for_cleanup[extra_envelope_field]
tests/unit/test_lifecycle_assertions.py::test_create_contract_failure_keeps_id_available_for_cleanup[status]
tests/unit/test_lifecycle_assertions.py::test_create_rejects_invalid_ids_without_registering_them[True]
tests/unit/test_lifecycle_assertions.py::test_create_rejects_invalid_ids_without_registering_them[0]
tests/unit/test_lifecycle_assertions.py::test_create_rejects_invalid_ids_without_registering_them[-1]
tests/unit/test_lifecycle_assertions.py::test_create_rejects_invalid_ids_without_registering_them[1]
tests/unit/test_lifecycle_assertions.py::test_create_rejects_invalid_ids_without_registering_them[None]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[first_then_second-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[first_then_second-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[second_then_first-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[second_then_first-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[lost_update-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[lost_update-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[corrupt_response-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[corrupt_response-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[corrupt_persisted-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[corrupt_persisted-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[invalid_persisted_type-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[invalid_persisted_type-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[server_error-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[server_error-independent]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[response_loss-conflicting]
tests/unit/test_lifecycle_assertions.py::test_parallel_patch_scenarios_detect_regressions[response_loss-independent]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[winner_a]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[winner_b]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[mixed_fields]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[partial_dates]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[invalid_price_type]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[unchanged]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[drift]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[missing]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[conflict409]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[precondition412]
tests/unit/test_lifecycle_assertions.py::test_conflicting_put_reconciliation_rejects_invalid_outcomes[server500]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[correct-A_then_B]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[correct-B_then_A]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[ignored_second-A_then_B]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[ignored_second-B_then_A]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[mixed_final-A_then_B]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[mixed_final-B_then_A]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[drift-A_then_B]
tests/unit/test_lifecycle_assertions.py::test_ordered_conflicting_put_control_detects_ignored_or_unstable_writes[drift-B_then_A]
tests/unit/test_resilience.py::test_get_retries_transient_failure_then_returns_response
tests/unit/test_resilience.py::test_get_retry_exhaustion_is_visible
tests/unit/test_resilience.py::test_uncertain_writes_are_never_transport_retried[POST]
tests/unit/test_resilience.py::test_uncertain_writes_are_never_transport_retried[PUT]
tests/unit/test_resilience.py::test_uncertain_writes_are_never_transport_retried[PATCH]
tests/unit/test_resilience.py::test_uncertain_writes_are_never_transport_retried[DELETE]
tests/unit/test_resilience.py::test_missing_prerequisite_recovery_is_bounded[False]
tests/unit/test_resilience.py::test_missing_prerequisite_recovery_is_bounded[True]
tests/unit/test_resilience.py::test_cleanup_attempts_all_owned_ids_and_reports_failure
tests/unit/test_resilience.py::test_connect_failure_before_send_can_be_retried[POST]
tests/unit/test_resilience.py::test_connect_failure_before_send_can_be_retried[PUT]
tests/unit/test_resilience.py::test_connect_failure_before_send_can_be_retried[PATCH]
tests/unit/test_resilience.py::test_connect_failure_before_send_can_be_retried[DELETE]
tests/unit/test_resilience.py::test_delete_405_requires_confirmed_absence[404]
tests/unit/test_resilience.py::test_delete_405_requires_confirmed_absence[200]
tests/unit/test_resilience.py::test_delete_405_requires_confirmed_absence[500]
tests/unit/test_resilience.py::test_available_prerequisite_is_reused
tests/unit/test_resilience.py::test_prerequisite_recovery_requires_confirmed_404[forbidden]
tests/unit/test_resilience.py::test_prerequisite_recovery_requires_confirmed_404[server_error]
tests/unit/test_resilience.py::test_prerequisite_recovery_requires_confirmed_404[timeout]
tests/unit/test_resilience.py::test_prerequisite_recovery_requires_confirmed_404[invalid_json]
tests/unit/test_resilience.py::test_cleanup_404_is_terminal_without_recreation
tests/unit/test_resilience.py::test_cleanup_transport_failure_still_attempts_remaining_ids
tests/unit/test_security_assertions.py::test_unauthorized_mutation_checks_status_and_state[403-none]
tests/unit/test_security_assertions.py::test_unauthorized_mutation_checks_status_and_state[200-none]
tests/unit/test_security_assertions.py::test_unauthorized_mutation_checks_status_and_state[200-update]
tests/unit/test_security_assertions.py::test_unauthorized_mutation_checks_status_and_state[403-update]
tests/unit/test_security_assertions.py::test_unauthorized_mutation_checks_status_and_state[403-delete]
tests/unit/test_security_assertions.py::test_internal_id_collision_is_reported_and_cleaned[missing-original]
tests/unit/test_security_assertions.py::test_internal_id_collision_is_reported_and_cleaned[reject-but-mutates]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_400-POST]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_400-PUT]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_400-PATCH]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_422-POST]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_422-PUT]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_422-PATCH]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[accept_200-POST]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[accept_200-PUT]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[accept_200-PATCH]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[server_500-POST]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[server_500-PUT]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[server_500-PATCH]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_but_change-POST]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_but_change-PUT]
tests/unit/test_validation_assertions.py::test_invalid_input_status_state_and_cleanup[reject_but_change-PATCH]
```

</details>

## Keeping the map current

When tests change, update the scenario row, source link, parameter summary, and
case count. Recheck collection with `python -m pytest --collect-only -q` and keep
the case-ID appendix aligned. Update assertion details in [test-cases.md](test-cases.md)
and execution outcomes in [validation-results.md](validation-results.md).
