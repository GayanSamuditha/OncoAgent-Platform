import pytest

from app.services.demo_reset import sanitized_counts, validate_demo_id


def test_demo_reset_requires_exact_local_prefix() -> None:
    assert validate_demo_id("client-demo-closure") == "client-demo-closure"
    with pytest.raises(ValueError):
        validate_demo_id("demo-closure")
    with pytest.raises(ValueError):
        validate_demo_id("client-demo-")


def test_demo_reset_counts_are_sanitized() -> None:
    assert sanitized_counts({"workflow_runs": 2, "patient_names": 4}) == {
        "workflow_runs": 2,
        "patient_names": 4,
    }
