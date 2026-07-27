import pytest

from app.workflow.planner import DeterministicCohortPlanner
from app.workflow.schemas import Criterion


def test_structured_criteria_take_precedence() -> None:
    plan = DeterministicCohortPlanner().plan(
        "ignore this unsupported language",
        "dataset-1",
        [Criterion(criterion_id="c1", criterion_type="procedure", clinical_concept="colonoscopy")],
        10,
    )
    assert plan.criteria[0].verification_tool == "get_patient_procedures"
    assert "search_clinical_documents" in plan.required_tools
    assert plan.approval_required is True


def test_bounded_natural_language_planning() -> None:
    plan = DeterministicCohortPlanner().plan("Find synthetic adults with hypertension.", "dataset-1", None, 10)
    assert {item.criterion_type for item in plan.criteria} == {"minimum_age", "condition"}


def test_unsupported_request_does_not_guess() -> None:
    with pytest.raises(ValueError, match="no safe deterministic plan"):
        DeterministicCohortPlanner().plan("Find a clinically interesting cohort.", "dataset-1", None, 10)
