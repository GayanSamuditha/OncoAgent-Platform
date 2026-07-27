from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.workflow.tools import ToolExecutionError, build_tool_registry, execute_tool


def test_all_phase3a_tools_are_registered() -> None:
    registry = build_tool_registry()
    assert {"search_clinical_documents", "get_patient_demographics", "get_patient_conditions", "get_patient_observations", "get_patient_procedures", "get_patient_medications", "get_patient_diagnostic_reports", "get_patient_encounters", "verify_date_window", "build_patient_evidence"} <= set(registry)


def test_unregistered_tool_is_rejected() -> None:
    with pytest.raises(ToolExecutionError, match="not registered"):
        execute_tool({}, "arbitrary_sql", object(), {})  # type: ignore[arg-type]


def test_tool_arguments_are_validated_before_execution() -> None:
    registry = build_tool_registry()
    with pytest.raises(ValidationError):
        execute_tool(registry, "get_patient_demographics", SimpleNamespace(actor_role="researcher"), {"dataset_id": "only-dataset"})  # type: ignore[arg-type]
