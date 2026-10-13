"""Derive scoped coverage from a completed Allure run, without claiming server coverage."""
import argparse
import json
from collections import Counter
from pathlib import Path

FAMILIES = {
    "Sequential identical PUT": (["test_put_three_times_is_idempotent",
                                  "test_sequential_identical_put_preserves_observable_state"], 3),
    "Concurrent identical PUT": (["test_concurrent_identical_put_preserves_observable_state"], 2),
    "Repeated DELETE": (["test_repeated_delete_keeps_booking_absent"], 1),
    "Repeated set-value PATCH": (["test_repeated_set_value_patch_preserves_observable_state"], 1),
}


def summarize(results):
    rows = []
    for family, (names, identified) in FAMILIES.items():
        cases = [r for r in results if any(name in r["fullName"] for name in names)]
        statuses = Counter(r["status"] for r in cases)
        rows.append({"family": family, "identified_cases": identified,
                     "executed_cases": sum(v for k, v in statuses.items() if k != "skipped"),
                     "passed_cases": statuses["passed"], "outcomes": dict(statuses)})
    simulated = [r for r in results if "test_lost_response_reports_uncertainty_without_replaying_mutation" in r["fullName"]]
    return {
        "scope": "Named idempotency catalog; not overall API or code coverage",
        "supported_live_families": {"identified": len(rows), "executed": sum(row["executed_cases"] > 0 for row in rows)},
        "supported_live_cases": {"identified": 7, "executed": sum(row["executed_cases"] for row in rows),
                                 "passed": sum(row["passed_cases"] for row in rows)},
        "families": rows,
        "controlled_response_loss_cases": {"identified": 8, "executed": sum(r["status"] != "skipped" for r in simulated),
                                           "passed": sum(r["status"] == "passed" for r in simulated)},
        "unsupported_live_capabilities": ["Idempotency-Key deduplication", "key scope and retention",
                                          "authoritative business-operation count", "hidden side effects",
                                          "deterministic live commit-boundary injection", "server restart/replica testing"],
        "server_branch_coverage": "unmeasured", "hidden_side_effect_coverage": "unmeasured",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "offline"], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = root / "reports" / args.mode
    results = [json.loads(p.read_text()) for p in (directory / "allure-results").glob("*-result.json")]
    if not results:
        raise SystemExit("No Allure results found; collect tests before measuring coverage")
    coverage = summarize(results)
    (directory / "coverage.json").write_text(json.dumps(coverage, indent=2) + "\n")
    print(json.dumps({"mode": args.mode, "live_cases": coverage["supported_live_cases"],
                      "simulated_cases": coverage["controlled_response_loss_cases"]}))
