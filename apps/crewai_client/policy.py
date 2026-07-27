"""Defense-in-depth request policy for the downstream crew."""

import re

from .schemas import CrewRunRequest

BLOCKED = re.compile(
    r"(reveal.*(token|prompt|reasoning)|hidden reasoning|chain.of.thought|direct database|postgres|sql|shell|terminal|filesystem|\.env|bypass.*mcp|bypass.*review|approve.*cohort|raw fhir|change.*audit|ollama.*url|unregistered tool|export patient)",
    re.I,
)


def validate_request(request: CrewRunRequest, allowed_datasets: set[str]) -> None:
    if request.dataset_id not in allowed_datasets:
        raise ValueError("dataset is not allowlisted for CrewAI")
    if BLOCKED.search(request.research_question):
        raise ValueError("request violates the CrewAI safety policy")
    if any(BLOCKED.search(str(item.model_dump())) for item in request.structured_criteria):
        raise ValueError("criterion violates the CrewAI safety policy")
