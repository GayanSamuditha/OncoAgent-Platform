import os

import pytest

from app.core.config import Settings
from app.workflow.planner import LocalPlannerError, OllamaQwenPlannerProvider
from app.workflow.schemas import Criterion


@pytest.mark.skipif(os.getenv("RUN_REAL_LOCAL_LLM_TESTS") != "1", reason="set RUN_REAL_LOCAL_LLM_TESTS=1")
def test_real_qwen_local_planner_is_available_or_rejects_safely() -> None:
    provider = OllamaQwenPlannerProvider(Settings())
    assert provider.health()["installed"] is True
    try:
        outcome = provider.generate_cohort_plan("Adults with hypertension", "synthetic-test", [Criterion(criterion_id="condition", criterion_type="condition", clinical_concept="hypertension")], 2)
        assert outcome.plan.approval_required is True
        assert outcome.lineage["resolved_model_digest"]
        assert outcome.lineage["cohort_plan_schema_hash"]
    except LocalPlannerError as exc:
        assert exc.category in {"schema_policy_violation", "prompt_injection_policy_failure"}
