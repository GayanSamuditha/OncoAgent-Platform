"""Versioned, synthetic-only scenarios used by the local client demonstration."""

from __future__ import annotations

SCENARIO_REGISTRY_VERSION = "client-demo-scenarios-v1"

DATASET_NAME = "synthea-eval-100"
LANGGRAPH_QUESTION = "Identify synthetic patients with diabetes and hypertension for research review."
LANGGRAPH_CRITERIA = [
    {"criterion_type": "condition", "clinical_concept": "diabetes", "operator": "contains", "required": True},
    {"criterion_type": "condition", "clinical_concept": "hypertension", "operator": "contains", "required": True},
]
CREWAI_QUESTION = "Identify synthetic oncology patients with documented cancer-related conditions for evidence review."
CREWAI_CRITERIA = [
    {"criterion_type": "condition", "clinical_concept": "cancer", "operator": "contains", "required": True},
]

SCENARIOS = {
    "langgraph_research": {"kind": "langgraph", "question": LANGGRAPH_QUESTION, "criteria": LANGGRAPH_CRITERIA},
    "temporal_crewai_research": {"kind": "crewai", "question": CREWAI_QUESTION, "criteria": CREWAI_CRITERIA},
}
