"""Deterministic percentile, SLO, and bounded backpressure helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable

from app.performance.contracts import SLOResult


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def evaluate_slo(
    name: str,
    value: float | None,
    threshold: float | None,
    *,
    unit: str,
    sample_size: int,
    blocking: bool,
    higher_is_better: bool = True,
) -> SLOResult:
    if value is None or sample_size == 0:
        return SLOResult(
            name=name,
            value=value,
            threshold=threshold,
            unit=unit,
            status="not_evaluable",
            blocking=blocking,
            sample_size=sample_size,
            reason="No applicable measurements were collected.",
        )
    passed = threshold is None or (value >= threshold if higher_is_better else value <= threshold)
    return SLOResult(
        name=name,
        value=value,
        threshold=threshold,
        unit=unit,
        status="pass" if passed else "fail",
        blocking=blocking,
        sample_size=sample_size,
        reason="Measured value satisfies the development threshold."
        if passed
        else "Measured value misses the development threshold.",
    )
