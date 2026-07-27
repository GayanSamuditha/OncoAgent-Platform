import argparse
import json
import sys
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, "apps/api")
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.retrieval.evaluation import (
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.retrieval.model_registry import provider_for
from app.retrieval.search import postgres_fts_search, search


def profile_metrics(rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        return {"precision_at_5": 0.0, "recall_at_5": 0.0, "mrr": 0.0, "ndcg_at_5": 0.0, "zero_result_rate": 0.0, "median_latency_ms": 0.0, "p95_latency_ms": 0.0}
    latencies = sorted(float(row["latency_ms"]) for row in rows)
    return {key: sum(float(row[key]) for row in rows) / len(rows) for key in ("precision_at_5", "recall_at_5", "mrr", "ndcg_at_5", "zero_result_rate")} | {"median_latency_ms": median(latencies), "p95_latency_ms": latencies[min(len(latencies) - 1, max(0, int(len(latencies) * 0.95) - 1))]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--evaluation-file", required=True)
    parser.add_argument("--output", default="evaluation_outputs/phase2_5_results.json")
    args = parser.parse_args()
    cases = json.loads(Path(args.evaluation_file).read_text(encoding="utf-8"))["cases"]
    settings = get_settings()
    providers = {profile: provider_for(settings, profile) for profile in ("medcpt", "bioclinicalbert")}
    for provider in providers.values():
        provider.load()
    all_results: dict[str, list[dict[str, object]]] = {"postgres_fts": [], "bioclinicalbert": [], "medcpt": []}
    with SessionLocal() as session:
        for case in cases:
            relevant = set(case["expected_patient_ids"])
            for profile, profile_rows in all_results.items():
                started = time.perf_counter()
                if profile == "postgres_fts":
                    results, _ = postgres_fts_search(session, args.dataset_id, case["query"], 5, ["encounter"], None)
                else:
                    results, _ = search(session, providers[profile], args.dataset_id, case["query"], 5, ["encounter"], None, None)
                latency = (time.perf_counter() - started) * 1000
                retrieved = list(dict.fromkeys(str(item["patient_id"]) for item in results))
                profile_rows.append({"query_id": case["query_id"], "category": case["category"], "retrieved": retrieved, "latency_ms": latency, "precision_at_5": precision_at_k(retrieved, relevant), "recall_at_5": recall_at_k(retrieved, relevant), "mrr": reciprocal_rank(retrieved, relevant), "ndcg_at_5": ndcg_at_k(retrieved, relevant), "zero_result_rate": float(not retrieved)})
    output = {"dataset_id": args.dataset_id, "synthetic_development_evaluation": True, "not_clinically_validated": True, "profiles": {profile: {"metrics": profile_metrics(rows), "cases": rows} for profile, rows in all_results.items()}}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({profile: value["metrics"] for profile, value in output["profiles"].items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
