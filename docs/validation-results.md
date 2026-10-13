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
