# Validation results — 13 October 2026

Runtime: `/Users/yzp/Documents/code3000/py3148/bin/python`, Python 3.14.8.

| Run | Outcome | Report |
| --- | --- | --- |
| Offline, two workers, final suite | 32 passed, 16 live tests skipped | reports/offline.xml |
| Live sequential checkpoint | 44 passed, 3 XFAIL | reports/sequential.xml |
| Live, two workers, final suite | 45 passed, 3 XFAIL | reports/parallel.xml |

The final parallel suite contains one additional live concurrent token-acquisition
check added after the sequential checkpoint. All final tests were executed in the
parallel run. Both live runs include three independent two-thread collision rounds.
JUnit properties include winner, release skew, owned IDs, and recovery replacements.
All tracked booking cleanup completed without errors in the successful runs.

Expected failures are duplicate rejection, reversed-date rejection, and negative
price rejection. Their separate characterization tests passed. Unsupported rooms,
user ownership, price formulas, resource versions, true token TTL, and exact server
arrival timing remain explicitly documented in requirements-coverage.md.

Initial runs exposed TLS connection timeouts and repeated DELETE returning 405.
Pre-send connection failures now retry within the configured limit. A DELETE 405
is accepted only after GET confirms 404. Controlled tests cover those paths, plus
ambiguous write outcomes that must never be retried. The reruns passed without
hiding initial infrastructure failures as expected business gaps.

`pip check` reports no broken dependencies; `git diff --check` passes. The editable
package was successfully installed into the specified environment. GitHub Actions
configuration is included but has not been run remotely. Generated XML reports are
ignored by git; this document records the reviewable validation snapshot.


## Allure 3 integration verification

Pinned Allure Report 3.20.1 and allure-pytest 2.16.2. Added ten reporting checks:
seven adapter outcome/exit-code scenarios and three evidence/redaction/threading
checks. Final offline run: 42 passed, 16 skipped. Final live two-worker run:
55 passed, 3 strict XFAIL. All tracked booking cleanup completed successfully.
Raw result identities and attachment references match the generated report counts.
HTML was generated but not visually inspected because this session lacks browser
connections and Computer Use permission. See allure-reporting.md for report commands.


## History-preserving rerun

The live suite reran with two workers: 55 passed, 3 strict XFAIL in 18.27 seconds.
Allure history was seeded from the previous saved results before clearing raw
results. After report generation, live.jsonl contains two runs with all 58 stable
test IDs shared between them; the previous history bytes remain unchanged.
The regenerated report identifies zero new tests. Offline history retains its
separate baseline. Previous raw results and HTML are archived under
reports/archive/20261013T143028Z. History retention is configured for future local
runs and branch-specific GitHub Actions caching; remote CI has not been run.


## Improved execution evidence

Added paired request/response steps, allowed headers, typed JSON field differences,
scenario comparisons, and explicit retry/authentication/recovery/cleanup events.
Six additional checks verify nested/type-sensitive/redacted differences, retry and
refresh evidence, and retained attachments across setup/call/teardown failures.

Full two-worker offline run: 48 passed, 16 live tests skipped. Full live run:
61 passed, 3 strict XFAIL in 16.71 seconds. Final targeted failure-phase evidence
checks also pass (3 passed). The live report contains 64 distinct test identities;
all attachment references resolve. Per-test HTTP booking IDs match each fixture's
owned cleanup IDs, with no cross-test evidence mixing. All 17 tracked cleanup
outcomes succeeded. Live trace records 83 HTTP attempts, 15 token-acquisition
events, one refresh, and one prerequisite recreation. No retries were needed in
this live run; controlled checks verify retry reasons, attempt correlation, and backoff.

History retained its exact previous bytes and appended one run per mode: three
live runs and two offline runs. Previous report/history snapshots are archived at
reports/archive/20261013T181819Z. Reports were regenerated and audited directly;
visual browser inspection was unavailable. Dependency and diff checks pass.


## Idempotency coverage expansion

Added bounded sequential PUT counts (2/5 alongside the existing three-PUT test),
concurrent identical PUTs with 2/4 writers, three repeated DELETEs with confirmed
absence, and three repeated set-value PATCHes. Conflicting payloads remain a
separate integrity category. Eight local-model response-loss cases verify before/
after simulated commit behavior without blindly replaying uncertain mutations.
A coverage-accounting check ensures skips and failures are never counted as passes.

Full live two-worker run: 76 passed, 3 strict XFAIL in 29.04 seconds. Offline:
57 passed, 22 live tests skipped. The supported idempotency catalog executed and
passed 7/7 cases across 4/4 families; controlled response-loss cases passed 8/8.
These are catalog counts, not percentages of all server behavior. Server branches,
operation counts, hidden effects, and live key-based deduplication are unmeasured
or unsupported. Actual counts are in reports/live/coverage.json.

All 23 owned-ID cleanup outcomes succeeded. Report identities are distinct (79),
all attachment references resolve, and scope labels distinguish identical requests
from conflicting-write integrity. Measured coverage JSON and scope documentation
are embedded as global attachments in both generated HTML reports.

History retained its prior bytes and appended one run per mode: four live runs and
three offline runs. All 64 identities from the previous run are preserved; 15 added
cases are reported as new. Previous report/history snapshots are archived under
reports/archive/20261013T191559Z. Dependency and diff checks pass. Remote CI and
visual browser rendering were not exercised in this session.
