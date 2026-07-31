from app.performance.calculations import evaluate_slo


def test_correctness_slo_can_be_blocking_without_latency_gate() -> None:
    correctness = evaluate_slo(
        "duplicate_records", 0, 0, unit="ratio", sample_size=4, blocking=True
    )
    latency = evaluate_slo("p95", None, 500, unit="ms", sample_size=0, blocking=False)
    assert correctness.status == "pass"
    assert correctness.blocking is True
    assert latency.status == "not_evaluable"
    assert latency.blocking is False
