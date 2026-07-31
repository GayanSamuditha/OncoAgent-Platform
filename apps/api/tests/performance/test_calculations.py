from app.performance.calculations import evaluate_slo, percentile, ratio
from app.performance.profiles import PROFILES, get_profile


def test_percentiles_are_deterministic() -> None:
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([], 0.95) is None


def test_empty_denominator_is_not_evaluable() -> None:
    assert ratio(0, 0) is None
    result = evaluate_slo("latency", None, 100, unit="ms", sample_size=0, blocking=False)
    assert result.status == "not_evaluable"


def test_profiles_are_bounded_and_complete() -> None:
    assert len(PROFILES) == 11
    assert get_profile("api-read-concurrent").concurrency <= 32
