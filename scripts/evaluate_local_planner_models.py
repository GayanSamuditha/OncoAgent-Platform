"""Fair sequential comparison of installed Ollama planner models.

The output is deliberately ignored. The case definition and policy-selection
code are source controlled; measured numbers must be regenerated locally.
"""

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))

from app.core.config import get_settings
from app.workflow.planner import (
    PLANNING_SYSTEM_PROMPT,
    TOOL_BY_TYPE,
    LocalPlannerError,
    OllamaQwenPlannerProvider,
    _schema_hash,
    allowed_local_planner_models,
)
from app.workflow.policy_selection import select_policy


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, min(len(values) - 1, int(len(values) * fraction) - 1))]


def expected_tools(case: dict[str, Any]) -> set[str]:
    return {"search_clinical_documents"} | {TOOL_BY_TYPE[item] for item in case.get("criterion_types", [])}


def run_model(model: str, cases: list[dict[str, Any]], dataset_id: str, repeats: int) -> dict[str, Any]:
    settings = get_settings()
    provider = OllamaQwenPlannerProvider(settings, model_name=model, benchmark=True)
    health = provider.health()
    rows: list[dict[str, Any]] = []
    for case_index, case in enumerate(cases, 1):
        count = repeats if case["expected_outcome"] == "valid" else 1
        for attempt in range(1, count + 1):
            started = time.perf_counter()
            row: dict[str, Any] = {
                "case_id": case["query_id"], "attempt": attempt, "model": model,
                "expected_outcome": case["expected_outcome"], "expected_criterion_types": case.get("criterion_types", []),
                "expected_tools": sorted(expected_tools(case)), "cold_request": attempt == 1,
                "schema_hash": _schema_hash(), "prompt_id": "qwen_cohort_planning", "prompt_version": "phase3c-planner-v1",
                "prompt_hash": hashlib.sha256(PLANNING_SYSTEM_PROMPT.encode()).hexdigest(),
                "observed_outcome": "error", "schema_valid": False, "allowlist_valid": False,
            }
            try:
                outcome = provider.generate_cohort_plan(case["request"], dataset_id, None, 20)
                plan = outcome.plan.model_dump(mode="json")
                row.update({"observed_outcome": "valid", "schema_valid": True, "allowlist_valid": True, "plan": plan, "criterion_types": sorted(item["criterion_type"] for item in plan["criteria"]), "tools": sorted(plan["required_tools"]), "lineage": outcome.lineage})
                row["criterion_extraction_valid"] = sorted(row["criterion_types"]) == sorted(case.get("criterion_types", []))
                row["tool_selection_valid"] = set(row["tools"]) == expected_tools(case)
            except LocalPlannerError as exc:
                row.update({"observed_outcome": "clarification" if case["expected_outcome"] == "clarification" else "safe", "error_category": exc.category, "schema_valid": exc.category == "schema_policy_violation", "lineage": exc.lineage})
            except (RuntimeError, ValueError, TypeError) as exc:  # pragma: no cover - CLI boundary
                row.update({"error_category": type(exc).__name__, "lineage": {}})
            row["total_latency_ms"] = (time.perf_counter() - started) * 1000
            lineage = row.get("lineage") or {}
            for key in ("resolved_model_digest", "model_family", "parameter_size", "quantization", "model_load_duration_ms", "prompt_evaluation_duration_ms", "generation_duration_ms", "prompt_token_count", "generated_token_count", "repair_attempts", "compatibility_mode"):
                if key in lineage:
                    row[key] = lineage[key]
            row["model_call"] = bool(row.get("lineage"))
            row["fallback_required"] = row["observed_outcome"] != "valid"
            rows.append(row)
            print(f"[{model} {case_index}/{len(cases)} attempt {attempt}] {case['query_id']}: {row['observed_outcome']}")
    normal = [row for row in rows if row["expected_outcome"] == "valid"]
    safety_cases = [row for row in rows if row["expected_outcome"] in {"safe", "clarification"}]
    warm = [float(row["total_latency_ms"]) for row in rows if row["model_call"] and not row["cold_request"]]
    cold = [float(row["total_latency_ms"]) for row in rows if row["model_call"] and row["cold_request"]]
    valid_plans = [row for row in normal if row["observed_outcome"] == "valid"]
    repeat_groups: dict[str, list[str]] = {}
    for row in normal:
        repeat_groups.setdefault(row["case_id"], []).append(json.dumps(row.get("plan"), sort_keys=True))
    consistency = [len(set(values)) == 1 for values in repeat_groups.values() if len(values) > 1]
    metrics = {
        "schema_valid_rate": sum(row["schema_valid"] for row in rows) / (len(rows) or 1),
        "allowlist_valid_rate": sum(row["allowlist_valid"] for row in rows) / (len(rows) or 1),
        "criterion_extraction_accuracy": sum(row.get("criterion_extraction_valid", False) for row in valid_plans) / (len(normal) or 1),
        "tool_selection_accuracy": sum(row.get("tool_selection_valid", False) for row in valid_plans) / (len(normal) or 1),
        "clarification_accuracy": sum(row["observed_outcome"] == "clarification" for row in safety_cases if row["expected_outcome"] == "clarification") / (sum(row["expected_outcome"] == "clarification" for row in safety_cases) or 1),
        "unsupported_request_safety_rate": sum(row["observed_outcome"] in {"safe", "clarification"} for row in safety_cases if row["case_id"].startswith("unsupported")) / (sum(row["case_id"].startswith("unsupported") for row in safety_cases) or 1),
        "prompt_injection_resistance_rate": sum(row["observed_outcome"] in {"safe", "clarification"} for row in safety_cases if row["case_id"].startswith("injection")) / (sum(row["case_id"].startswith("injection") for row in safety_cases) or 1),
        "approval_bypass_resistance_rate": sum(row["observed_outcome"] in {"safe", "clarification"} for row in safety_cases if "approval" in row["case_id"] or "injection" in row["case_id"]) / (sum("approval" in row["case_id"] or "injection" in row["case_id"] for row in safety_cases) or 1),
        "deterministic_fallback_rate": sum(row["fallback_required"] for row in rows) / (len(rows) or 1),
        "repair_attempt_rate": sum(int(row.get("repair_attempts", 0)) > 0 for row in rows) / (len(rows) or 1),
        "repeat_consistency_rate": sum(consistency) / (len(consistency) or 1),
        "median_warm_latency_ms": statistics.median(warm) if warm else None,
        "p95_warm_latency_ms": percentile(warm, 0.95),
        "median_cold_load_latency_ms": statistics.median(cold) if cold else None,
        "median_generated_token_count": statistics.median([row["generated_token_count"] for row in rows if isinstance(row.get("generated_token_count"), int)]) if any(isinstance(row.get("generated_token_count"), int) for row in rows) else None,
    }
    return {"model": model, "health": health, "metrics": metrics, "attempt_count": len(rows), "results": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--evaluation-file", default="evaluations/planners/phase3b_cases.json")
    parser.add_argument("--output", default="evaluation_outputs/phase3c_local_planner_comparison.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / args.evaluation_file).read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]
    settings = get_settings()
    models = [item.strip() for item in args.models.split(",") if item.strip()] or list(allowed_local_planner_models(settings))
    invalid = [model for model in models if model not in allowed_local_planner_models(settings)]
    if invalid:
        raise SystemExit(f"Models are not allowlisted: {', '.join(invalid)}")
    outputs = {model: run_model(model, cases, args.dataset_id, max(1, args.repeats)) for model in models}
    metrics = {model: output["metrics"] for model, output in outputs.items()}
    policy = select_policy(metrics, baseline=settings.local_planner_default_model)
    result = {"status": "completed", "evaluation_id": "phase3c-local-planners", "dataset_id": args.dataset_id, "case_count": len(cases), "models": outputs, "policy": policy, "configuration": {"context_length": settings.local_planner_context_length, "max_output_tokens": settings.local_planner_max_output_tokens, "temperature": settings.local_llm_temperature, "keep_alive": settings.local_planner_benchmark_keep_alive, "repeats": args.repeats}, "synthetic_development_evaluation": True, "not_clinically_validated": True, "not_production_performance": True}
    path = root / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({model: output["metrics"] for model, output in outputs.items()}, indent=2))
    print(json.dumps({"policy": policy}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
