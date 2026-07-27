"""Run a bounded, comparative synthetic retrieval evaluation."""

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import median
from typing import Any

sys.path.insert(0, "apps/api")

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.retrieval.evaluation import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.retrieval.model_registry import get_reranker, provider_for
from app.retrieval.search import hybrid_search, postgres_fts_search, search

FIRST_STAGE_PROFILES = ("postgres_fts", "bioclinicalbert", "medcpt", "hybrid_bioclinicalbert", "hybrid_medcpt")
PROFILE_SPECS = FIRST_STAGE_PROFILES + (
    "bioclinicalbert+medcpt_cross_encoder",
    "medcpt+medcpt_cross_encoder",
    "hybrid_bioclinicalbert+medcpt_cross_encoder",
    "hybrid_medcpt+medcpt_cross_encoder",
)


def metrics_for(retrieved: list[str], relevant: set[str]) -> dict[str, float]:
    return {
        "precision_at_5": precision_at_k(retrieved, relevant),
        "recall_at_5": recall_at_k(retrieved, relevant),
        "mrr": reciprocal_rank(retrieved, relevant),
        "ndcg_at_5": ndcg_at_k(retrieved, relevant),
        "zero_result_rate": float(not retrieved),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    values = {key: sum(float(row[key]) for row in rows) / max(len(rows), 1) for key in ("precision_at_5", "recall_at_5", "mrr", "ndcg_at_5", "zero_result_rate")}
    values["median_latency_ms"] = median(latencies) if latencies else 0.0
    values["p95_latency_ms"] = latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))] if latencies else 0.0
    values["average_candidate_pool_size"] = sum(float(row["candidate_pool_size"]) for row in rows) / max(len(rows), 1)
    values["average_reranking_latency_ms"] = sum(float(row["reranking_latency_ms"]) for row in rows) / max(len(rows), 1)
    return values


def base_profile(profile: str) -> str:
    return profile.replace("+medcpt_cross_encoder", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--evaluation-file", required=True)
    parser.add_argument("--output", default="evaluation_outputs/phase2_6_results.json")
    parser.add_argument("--candidate-pool-size", type=int, default=20)
    args = parser.parse_args()
    if not 5 <= args.candidate_pool_size <= 50:
        parser.error("candidate pool must be between 5 and 50")
    definition = json.loads(Path(args.evaluation_file).read_text(encoding="utf-8"))
    cases = definition["cases"]
    settings = get_settings()
    providers = {profile: provider_for(settings, profile) for profile in ("bioclinicalbert", "medcpt")}
    for provider in providers.values():
        provider.load()
    reranker = get_reranker(settings.reranker_model, settings.reranker_model_revision, settings.embedding_device, settings.reranker_batch_size)
    all_results: dict[str, list[dict[str, Any]]] = {profile: [] for profile in PROFILE_SPECS}
    with SessionLocal() as session:
        for case in cases:
            relevant = set(case["expected_patient_ids"])
            for profile in PROFILE_SPECS:
                first = base_profile(profile)
                reranking = "+medcpt_cross_encoder" in profile
                started = time.perf_counter()
                if first == "postgres_fts":
                    initial, first_latency = postgres_fts_search(session, args.dataset_id, case["query"], args.candidate_pool_size if reranking else 5, ["encounter"], None)
                elif first.startswith("hybrid_"):
                    initial, first_latency = hybrid_search(session, providers[first.removeprefix("hybrid_")], args.dataset_id, case["query"], args.candidate_pool_size if reranking else 5, ["encounter"], None, settings.rrf_constant)
                else:
                    initial, first_latency = search(session, providers[first], args.dataset_id, case["query"], args.candidate_pool_size if reranking else 5, ["encounter"], None, None)
                initial_patients = list(dict.fromkeys(str(item["patient_id"]) for item in initial))
                rerank_latency = 0.0
                final = initial
                if reranking:
                    rerank_started = time.perf_counter()
                    logits = reranker.rerank(case["query"], initial)
                    for item, logit in zip(initial, logits, strict=True):
                        item["reranker_logit"] = logit
                        item["initial_candidate_rank"] = item.get("rank")
                    final = sorted(initial, key=lambda item: (-float(str(item["reranker_logit"])), str(item["document_id"])))[:5]
                    for rank, item in enumerate(final, 1):
                        item["reranked_rank"] = rank
                        item["final_rank"] = rank
                    rerank_latency = (time.perf_counter() - rerank_started) * 1000
                retrieved = list(dict.fromkeys(str(item["patient_id"]) for item in final))[:5]
                row = {"query_id": case["query_id"], "query": case["query"], "category": case["category"], "retrieved": retrieved, "initial_retrieved": initial_patients[:5], "latency_ms": (time.perf_counter() - started) * 1000, "first_stage_latency_ms": first_latency, "reranking_latency_ms": rerank_latency, "candidate_pool_size": len(initial), **metrics_for(retrieved, relevant), "expected_patient_ids": list(relevant), "results": final[:5]}
                all_results[profile].append(row)

    profiles: dict[str, Any] = {}
    for profile, rows in all_results.items():
        profile_output: dict[str, Any] = {"metrics": summarize(rows), "cases": rows}
        if "+medcpt_cross_encoder" in profile:
            base_rows = all_results[base_profile(profile)]
            changes = []
            for base, row in zip(base_rows, rows, strict=True):
                before = metrics_for(base["initial_retrieved"], set(base["expected_patient_ids"]))
                after = metrics_for(row["retrieved"], set(row["expected_patient_ids"]))
                delta = after["mrr"] - before["mrr"]
                changes.append(delta)
            profile_output["reranking_outcomes"] = {"improved_percentage": sum(value > 0 for value in changes) / max(len(changes), 1), "unchanged_percentage": sum(value == 0 for value in changes) / max(len(changes), 1), "worsened_percentage": sum(value < 0 for value in changes) / max(len(changes), 1)}
        categories: dict[str, Any] = {}
        for category in sorted({str(row["category"]) for row in rows}):
            categories[category] = summarize([row for row in rows if row["category"] == category])
        profile_output["category_metrics"] = categories
        profiles[profile] = profile_output

    failures: list[dict[str, Any]] = []
    for index, case in enumerate(cases[:10]):
        base = all_results["bioclinicalbert"][index]
        reranked = all_results["bioclinicalbert+medcpt_cross_encoder"][index]
        failures.append({"query_id": case["query_id"], "query": case["query"], "category": case["category"], "expected_patient_ids": case["expected_patient_ids"], "first_stage_results": base["initial_retrieved"], "reranked_results": reranked["retrieved"], "structured_evidence": case["evidence_explanation"], "likely_failure_reason": "The bounded deterministic document representation or candidate ranking may omit or dilute the structured fact.", "possible_future_improvement": "Add section-aware retrieval features or structured verification after candidate retrieval."})
    output = {"dataset_id": args.dataset_id, "evaluation_case_count": len(cases), "synthetic_development_evaluation": True, "not_clinically_validated": True, "not_production_performance": True, "rrf_constant": settings.rrf_constant, "candidate_pool_size": args.candidate_pool_size, "profiles": profiles, "failure_analysis": failures}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({profile: value["metrics"] for profile, value in profiles.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
