from types import SimpleNamespace
from typing import Any

from crewai_client.schemas import CrewRunRequest
from crewai_client.service import CrewExecutionService


class FakeMCPClient:
    request_ids = ["request-search", "request-evidence"]

    def call(self, tool_name: str, arguments: dict[str, Any]) -> SimpleNamespace:
        if tool_name == "search_clinical_documents":
            result = {
                "items": [{"patient_id": "synthetic-patient-1"}],
                "actual_retrieval_profile": "postgres_fts",
                "retrieval_fallbacks": [],
            }
            request_id = "request-search"
        else:
            assert tool_name == "build_patient_evidence"
            assert arguments["patient_id"] == "synthetic-patient-1"
            result = {
                "facts": {
                    "source_resource_ids": ["synthetic-resource-1"],
                }
            }
            request_id = "request-evidence"
        return SimpleNamespace(
            result=result,
            request_id=request_id,
            tool_name=tool_name,
        )


def test_deterministic_fallback_records_measured_task_durations() -> None:
    service = CrewExecutionService(SimpleNamespace(), FakeMCPClient())
    request = CrewRunRequest.model_validate(
        {
            "dataset_id": "synthetic-dataset",
            "research_question": "Find synthetic adults with hypertension",
            "structured_criteria": [
                {
                    "criterion_type": "condition",
                    "clinical_concept": "hypertension",
                    "required": True,
                }
            ],
            "maximum_candidates": 2,
            "retrieval_profile": "postgres_fts",
            "model_profile": "automatic",
            "actor_context": {
                "actor_id": "researcher-console",
                "actor_role": "researcher",
            },
        }
    )

    brief = service.deterministic_run(request, "run-1")

    assert brief.unresolved_count == 1
    durations = service.last_execution["task_durations_seconds"]
    assert set(durations) == {
        "candidate_discovery",
        "structured_evidence_collection",
        "eligibility_evidence_review",
        "research_brief_generation",
    }
    assert all(duration > 0 for duration in durations.values())
    assert service.last_execution["task_statuses"] == {
        task_name: "completed" for task_name in durations
    }
