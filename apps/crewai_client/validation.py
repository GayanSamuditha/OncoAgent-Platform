"""Deterministic validation for the final CrewAI research brief."""

import re
from typing import Any

from .schemas import (
    CandidateDiscoveryResult,
    EligibilityReviewResult,
    StructuredEvidenceResult,
    SyntheticResearchBrief,
)


class BriefValidationError(ValueError):
    """Raised when a generated brief is inconsistent with structured outputs."""


_UNSAFE_LANGUAGE = re.compile(
    r"\b(clinically approved|clinical approval|diagnos(?:e|is)|treatment recommendation|"
    r"prescribe|trial eligible|patient care)\b",
    re.IGNORECASE,
)


def validate_brief(
    brief: SyntheticResearchBrief,
    request_run_id: str,
    request_dataset_id: str,
    candidates: CandidateDiscoveryResult | None = None,
    evidence: StructuredEvidenceResult | None = None,
    review: EligibilityReviewResult | None = None,
) -> SyntheticResearchBrief:
    """Validate only claims that can be checked without model interpretation."""
    errors: list[str] = []
    if brief.run_id != request_run_id:
        errors.append("brief run_id does not match the persisted run")
    if brief.dataset_id != request_dataset_id:
        errors.append("brief dataset_id does not match the requested dataset")
    if brief.review_status != "awaiting_human_review":
        errors.append("brief must remain awaiting_human_review")
    if _UNSAFE_LANGUAGE.search(brief.methods_summary):
        errors.append("brief contains clinical approval or treatment language")

    candidate_ids = set(candidates.candidate_patient_ids) if candidates else set()
    included = {
        str(x.get("patient_id"))
        for x in brief.patient_summaries
        if x.get("patient_id") is not None
    }
    if candidates and included - candidate_ids:
        errors.append("brief contains a patient absent from candidate discovery")
    if review:
        expected_included = set(review.proposed_included_patients)
        if brief.proposed_included_count != len(expected_included):
            errors.append("included count does not match eligibility review")
        if set(review.proposed_included_patients) - candidate_ids:
            errors.append("eligibility review includes a non-candidate patient")
        if brief.proposed_excluded_count != len(review.proposed_excluded_patients):
            errors.append("excluded count does not match eligibility review")
        if brief.unresolved_count != len(review.unresolved_patients):
            errors.append("unresolved count does not match eligibility review")
    if evidence:
        known_resources = set(evidence.source_resource_ids)
        for item in brief.patient_summaries:
            for resource_id in item.get("source_resource_ids", []):
                if resource_id not in known_resources:
                    errors.append("brief contains an unknown provenance identifier")
                    break
    if not brief.synthetic_data_notice or not brief.clinical_validation_notice:
        errors.append("required safety notices are missing")
    if not isinstance(brief.mcp_lineage, dict):
        errors.append("MCP lineage is missing")
    if errors:
        raise BriefValidationError("; ".join(dict.fromkeys(errors)))
    return brief


def summarize_task_outputs(result: Any) -> dict[str, Any]:
    """Extract safe, structured task summaries without scratchpads."""
    summaries: dict[str, Any] = {}
    for task in getattr(result, "tasks_output", []) or []:
        model = getattr(task, "pydantic", None)
        if model is not None and hasattr(model, "model_dump"):
            summaries[str(getattr(task, "description", "task"))[:80]] = model.model_dump(mode="json")
    return summaries
