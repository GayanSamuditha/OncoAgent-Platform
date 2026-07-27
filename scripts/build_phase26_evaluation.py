"""Build source-controlled evaluation cases from normalized synthetic facts."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, "apps/api")

from app.db.session import SessionLocal
from app.models import (
    Condition,
    DiagnosticReport,
    Encounter,
    MedicationRequest,
    Observation,
    Procedure,
)
from sqlalchemy import select


def fact_case(prefix: str, index: int, query: str, category: str, row: Any, display: str, source_id: str) -> dict[str, object]:
    patient_id = str(row.patient_id)
    encounter_id = getattr(row, "encounter_id", None)
    return {
        "query_id": f"{prefix}-{index:03d}",
        "query": query,
        "category": category,
        "expected_patient_ids": [patient_id],
        "expected_encounter_ids": [str(encounter_id)] if encounter_id else [],
        "relevance_grades": {patient_id: 1},
        "relevant_fhir_resource_ids": [source_id],
        "evidence_explanation": f"Structured {category} fact: {display}.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", default="evaluations/retrieval/phase2_6_cases.json")
    args = parser.parse_args()
    cases: list[dict[str, object]] = []
    with SessionLocal() as session:
        specs: list[tuple[str, Any, str, str, str]] = [
            ("condition", Condition, "condition", "display", "source_resource_id"),
            ("observation", Observation, "observation", "display", "source_resource_id"),
            ("procedure", Procedure, "procedure", "display", "source_resource_id"),
            ("medication", MedicationRequest, "medication", "display", "source_resource_id"),
            ("diagnostic", DiagnosticReport, "diagnostic-report", "display", "source_resource_id"),
        ]
        for prefix, model, category, display_field, source_field in specs:
            rows = list(session.scalars(select(model).where(model.dataset_id == args.dataset_id).order_by(model.fhir_id).limit(8)))
            for index, row in enumerate(rows, 1):
                display = str(getattr(row, display_field) or category)
                query = display
                if prefix == "observation":
                    query = f"{display} measurement"
                elif prefix == "medication":
                    query = f"medication request for {display}"
                elif prefix == "diagnostic":
                    query = f"diagnostic report {display}"
                cases.append(fact_case(prefix, index, query, category, row, display, str(getattr(row, source_field))))

        encounters = list(session.scalars(select(Encounter).where(Encounter.dataset_id == args.dataset_id).order_by(Encounter.fhir_id).limit(8)))
        for index, row in enumerate(encounters, 1):
            display = row.encounter_type_display or row.encounter_class or "encounter"
            cases.append(fact_case("encounter", index, f"{display} encounter", "encounter-type", row, str(display), row.source_resource_id))

        condition_rows = list(session.scalars(select(Condition).where(Condition.dataset_id == args.dataset_id, Condition.encounter_id.is_not(None)).order_by(Condition.fhir_id).limit(8)))
        for index, row in enumerate(condition_rows, 1):
            display = str(row.display or "clinical condition")
            cases.append(fact_case("paraphrase", index, f"patient record documenting {display.lower()}", "lexical-paraphrase", row, display, row.source_resource_id))

    for index, case in enumerate(cases, 1):
        case["query_id"] = f"{case['query_id']}-{index:03d}"
    payload = {
        "dataset_id": args.dataset_id,
        "synthetic_development_evaluation": True,
        "not_clinically_validated": True,
        "ground_truth_source": "normalized structured Synthea FHIR facts",
        "cases": cases,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} structured-ground-truth cases to {destination}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
