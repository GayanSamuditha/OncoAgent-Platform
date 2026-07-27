import re
from typing import Any, Protocol

from app.workflow.schemas import CohortPlan, Criterion


class PlannerProvider(Protocol):
    provider_id: str

    def plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> CohortPlan: ...


TOOL_BY_TYPE = {
    "minimum_age": "get_patient_demographics",
    "maximum_age": "get_patient_demographics",
    "gender": "get_patient_demographics",
    "condition": "get_patient_conditions",
    "observation": "get_patient_observations",
    "procedure": "get_patient_procedures",
    "medication": "get_patient_medications",
    "diagnostic_report": "get_patient_diagnostic_reports",
    "encounter_type": "get_patient_encounters",
    "date_window": "verify_date_window",
}


class DeterministicCohortPlanner:
    provider_id = "deterministic-cohort-planner-v1"

    def plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> CohortPlan:
        selected = [criterion.model_copy(update={"verification_tool": TOOL_BY_TYPE[criterion.criterion_type]}) for criterion in (criteria or [])]
        if not selected:
            selected = self._bounded_natural_language_plan(request)
        if not selected:
            raise ValueError("Request needs explicit supported criteria; no safe deterministic plan was found.")
        query = request.strip()
        return CohortPlan(objective=request.strip(), dataset_id=dataset_id, retrieval_query=query, criteria=selected, retrieval_profile="medcpt", max_candidates=max_candidates, required_tools=sorted({TOOL_BY_TYPE[item.criterion_type] for item in selected} | {"search_clinical_documents"}), verification_requirements=[item.criterion_id for item in selected], approval_required=True)

    def _bounded_natural_language_plan(self, request: str) -> list[Criterion]:
        lowered = request.lower()
        found: list[Criterion] = []
        if re.search(r"\badult|age\s*(?:>=|over|at least)\s*18", lowered):
            found.append(Criterion(criterion_id="age-minimum", criterion_type="minimum_age", value=18, operator="gte"))
        concepts = (("hypertension", "condition", "condition-hypertension"), ("elevated blood pressure", "observation", "observation-blood-pressure"), ("blood pressure", "observation", "observation-blood-pressure"), ("colonoscopy", "procedure", "procedure-colonoscopy"), ("inhaler", "medication", "medication-inhaler"))
        for concept, kind, criterion_id in concepts:
            if concept in lowered and not any(item.criterion_id == criterion_id for item in found):
                found.append(Criterion(criterion_id=criterion_id, criterion_type=kind, clinical_concept=concept, operator="contains"))  # type: ignore[arg-type]
        return found


class DeterministicFakePlanner(DeterministicCohortPlanner):
    provider_id = "fake-cohort-planner"


def plan_to_dict(plan: CohortPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")
