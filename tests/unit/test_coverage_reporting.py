"""Coverage denominators must distinguish collection, execution, and success."""
import importlib.util
from pathlib import Path


def test_scoped_coverage_never_counts_skips_or_failures_as_passes():
    path = Path(__file__).parents[2] / "scripts/report_coverage.py"
    spec = importlib.util.spec_from_file_location("scoped_coverage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = [
        {"fullName": "module#test_put_three_times_is_idempotent", "status": "passed"},
        {"fullName": "module#test_sequential_identical_put_preserves_observable_state", "status": "skipped"},
        {"fullName": "module#test_concurrent_identical_put_preserves_observable_state", "status": "broken"},
        {"fullName": "module#test_lost_response_reports_uncertainty_without_replaying_mutation", "status": "failed"},
        {"fullName": "module#test_conflicting_updates_reconcile_to_one_complete_payload", "status": "passed"},
    ]
    summary = module.summarize(results)
    assert summary["supported_live_families"] == {"identified": 4, "executed": 2}
    assert summary["supported_live_cases"] == {"identified": 7, "executed": 2, "passed": 1}
    assert summary["controlled_response_loss_cases"] == {"identified": 8, "executed": 1, "passed": 0}
    assert summary["server_branch_coverage"] == "unmeasured"
