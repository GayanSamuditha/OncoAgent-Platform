import pytest
from crewai_client.schemas import SyntheticResearchBrief
from crewai_client.validation import BriefValidationError, validate_brief


def _brief(**overrides: object) -> SyntheticResearchBrief:
    value = {
        "run_id": "run-1",
        "dataset_id": "dataset-1",
        "research_question": "synthetic question",
        "methods_summary": "Structured MCP-only synthetic research summary.",
        "retrieval_summary": {},
        "candidate_count": 0,
        "proposed_included_count": 0,
        "proposed_excluded_count": 0,
        "unresolved_count": 0,
        "patient_summaries": [],
        "mcp_lineage": {"request_ids": []},
        "review_status": "awaiting_human_review",
    }
    value.update(overrides)
    return SyntheticResearchBrief.model_validate(value)


def test_brief_validation_accepts_safe_empty_summary() -> None:
    assert validate_brief(_brief(), "run-1", "dataset-1").review_status == "awaiting_human_review"


def test_brief_validation_rejects_clinical_claim_language() -> None:
    with pytest.raises(BriefValidationError):
        validate_brief(_brief(methods_summary="This is clinically approved for patient care."), "run-1", "dataset-1")


def test_brief_validation_rejects_unknown_patient() -> None:
    from crewai_client.schemas import CandidateDiscoveryResult

    candidates = CandidateDiscoveryResult(
        run_id="run-1", dataset_id="dataset-1", normalized_query="q",
        retrieval_profile_requested="medcpt", retrieval_provider_used="medcpt",
        candidate_patient_ids=["patient-1"],
    )
    with pytest.raises(BriefValidationError):
        validate_brief(_brief(patient_summaries=[{"patient_id": "patient-2"}]), "run-1", "dataset-1", candidates=candidates)
