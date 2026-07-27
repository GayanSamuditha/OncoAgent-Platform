import math
from collections.abc import Sequence
from statistics import median
from typing import Any, cast


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return sum(item in relevant for item in retrieved[:k]) / max(k, 1)


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    return sum(item in relevant for item in retrieved[:k]) / max(len(relevant), 1)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    return next((1 / index for index, item in enumerate(retrieved, 1) if item in relevant), 0.0)


def ndcg_at_k(retrieved: Sequence[str], relevant: set[str], k: int = 5) -> float:
    dcg = sum((1 / math.log2(index + 1)) for index, item in enumerate(retrieved[:k], 1) if item in relevant)
    ideal = sum(1 / math.log2(index + 1) for index in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def summarize(results: list[dict[str, object]]) -> dict[str, float]:
    values = cast(list[dict[str, Any]], results)
    latencies = [float(item["latency_ms"]) for item in values]
    return {"precision_at_5": sum(float(item["precision_at_5"]) for item in values) / max(len(values), 1), "recall_at_5": sum(float(item["recall_at_5"]) for item in values) / max(len(values), 1), "mrr": sum(float(item["mrr"]) for item in values) / max(len(values), 1), "ndcg_at_5": sum(float(item["ndcg_at_5"]) for item in values) / max(len(values), 1), "zero_result_rate": sum(not bool(item["retrieved"]) for item in values) / max(len(values), 1), "median_query_latency_ms": median(latencies) if latencies else 0.0}
