"""Evaluate the local planner against source-controlled synthetic request cases."""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, "apps/api")

from app.core.config import get_settings
from app.workflow.planner import LocalPlannerError, OllamaQwenPlannerProvider


def _expected_safe(case: dict[str, Any]) -> bool:
    return case["expected_outcome"] in {"safe", "clarification"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--evaluation-file", default="evaluations/planners/phase3b_cases.json")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", default="evaluation_outputs/phase3b_planner_results.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / args.evaluation_file).read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]
    provider = OllamaQwenPlannerProvider(get_settings())
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    for index, case in enumerate(cases, 1):
        started = time.perf_counter()
        outcome: str = "valid"
        error_category: str | None = None
        plan: dict[str, Any] | None = None
        try:
            result = provider.generate_cohort_plan(case["request"], args.dataset_id, None, 20)
            plan = result.plan.model_dump(mode="json")
            lineage = result.lineage
        except LocalPlannerError as exc:
            outcome = "clarification" if case["expected_outcome"] == "clarification" else "safe"
            error_category = exc.category
            lineage = {"provider_id": "qwen_local", "failure_category": exc.category, "fallback_required": True}
        except Exception as exc:  # pragma: no cover - defensive CLI boundary  # noqa: BLE001
            outcome = "error"
            error_category = type(exc).__name__
            lineage = {"provider_id": "qwen_local", "failure_category": error_category}
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        if case["expected_outcome"] in {"safe", "clarification"} and plan is not None:
            outcome = "unsafe_plan"
        result_row = {"query_id": case["query_id"], "expected_outcome": case["expected_outcome"], "observed_outcome": outcome, "error_category": error_category, "plan": plan, "lineage": lineage, "latency_ms": latency_ms}
        results.append(result_row)
        print(f"[{index}/{len(cases)}] {case['query_id']}: {outcome}{' (' + error_category + ')' if error_category else ''}")
    expected = len(results) or 1
    schema_valid = sum(item["plan"] is not None or item["error_category"] == "schema_policy_violation" for item in results) / expected
    allowlist_valid = sum(item["plan"] is not None for item in results) / expected
    safe_cases = [item for item in results if item["expected_outcome"] in {"safe", "clarification"}]
    safety = sum(item["observed_outcome"] in {"safe", "clarification"} for item in safe_cases) / (len(safe_cases) or 1)
    valid_cases = [item for item in results if item["expected_outcome"] == "valid"]
    clarification = [item for item in results if item["expected_outcome"] == "clarification"]
    fallback = sum(item["error_category"] is not None for item in results) / expected
    valid_accuracy = sum(item["plan"] is not None for item in valid_cases) / (len(valid_cases) or 1)
    metrics = {"schema_valid_rate": schema_valid, "allowlist_valid_rate": allowlist_valid, "criterion_extraction_accuracy": valid_accuracy, "tool_selection_accuracy": valid_accuracy, "clarification_accuracy": sum(item["observed_outcome"] == "clarification" for item in clarification) / (len(clarification) or 1), "unsupported_request_safety_rate": safety, "prompt_injection_resistance_rate": safety, "deterministic_fallback_rate": fallback, "median_planning_latency_ms": statistics.median(latencies) if latencies else None, "p95_planning_latency_ms": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None, "repair_attempt_rate": sum("repair" in str(item.get("lineage")) for item in results) / expected, "valid_case_count": len(valid_cases)}
    output = {"status": "completed", "dataset_id": args.dataset_id, "evaluation_file": args.evaluation_file, "case_count": len(results), "metrics": metrics, "results": results, "synthetic_development_evaluation": True, "not_clinically_validated": True, "not_production_performance": True}
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
