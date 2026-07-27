"""The bounded sequential OncologyResearchCrew definition."""

import os
from typing import Any

from .schemas import (
    CandidateDiscoveryResult,
    EligibilityReviewResult,
    StructuredEvidenceResult,
    SyntheticResearchBrief,
)
from .tools import tools_for


def build_crew(client: Any, model: str, settings: Any) -> Any:
    # CrewAI may initialize optional local storage at import time. Keep it in a
    # caller-controlled ignored/temp location and disable telemetry.
    os.environ.setdefault("CREWAI_STORAGE_DIR", "oncoagent-crewai")
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("CREWAI_DISABLE_TRACKING", "true")
    from crewai import LLM, Agent, Crew, Process, Task

    llm = LLM(
        model=f"ollama/{model}",
        base_url=settings.crewai_ollama_base_url,
        temperature=0,
        max_tokens=1024,
        timeout=settings.crewai_run_timeout_seconds,
    )
    researcher = Agent(
        role="Cohort Researcher",
        goal="Find bounded candidate IDs using only the assigned MCP search tool.",
        backstory="You are a synthetic-data retrieval specialist. Never make final inclusion decisions.",
        tools=tools_for(client, ["search_clinical_documents"]),
        llm=llm,
        allow_delegation=False,
        memory=False,
        max_iter=5,
        max_execution_time=180,
        allow_code_execution=False,
        verbose=False,
    )
    investigator = Agent(
        role="Structured Evidence Investigator",
        goal="Collect structured facts and FHIR provenance for candidates.",
        backstory="You report only facts returned by MCP and identify missing or conflicting data.",
        tools=tools_for(
            client,
            [
                "get_patient_demographics",
                "get_patient_conditions",
                "get_patient_observations",
                "get_patient_procedures",
                "get_patient_medications",
                "get_patient_diagnostic_reports",
                "get_patient_encounters",
                "verify_date_window",
            ],
        ),
        llm=llm,
        allow_delegation=False,
        memory=False,
        max_iter=5,
        allow_code_execution=False,
        verbose=False,
    )
    reviewer = Agent(
        role="Eligibility Evidence Reviewer",
        goal="Compare required criteria with structured evidence without adding unsupported claims.",
        backstory="Every output requires human review and provenance.",
        tools=tools_for(client, ["build_patient_evidence", "verify_date_window"]),
        llm=llm,
        allow_delegation=False,
        memory=False,
        max_iter=5,
        allow_code_execution=False,
        verbose=False,
    )
    writer = Agent(
        role="Research Brief Writer",
        goal="Write a concise synthetic research brief from validated structured outputs.",
        backstory="Do not make tool calls, clinical recommendations, or approval decisions.",
        tools=[],
        llm=llm,
        allow_delegation=False,
        memory=False,
        max_iter=5,
        allow_code_execution=False,
        verbose=False,
    )
    t1 = Task(
        description="Return only a CandidateDiscoveryResult for the bounded request. Do not expose reasoning.",
        expected_output="Validated CandidateDiscoveryResult JSON.",
        agent=researcher,
        output_pydantic=CandidateDiscoveryResult,
    )
    t2 = Task(
        description="Using only the validated candidate result, return StructuredEvidenceResult JSON with provenance.",
        expected_output="Validated StructuredEvidenceResult JSON.",
        agent=investigator,
        context=[t1],
        output_pydantic=StructuredEvidenceResult,
    )
    t3 = Task(
        description="Using only validated prior JSON, return EligibilityReviewResult. review_required must be true.",
        expected_output="Validated EligibilityReviewResult JSON.",
        agent=reviewer,
        context=[t1, t2],
        output_pydantic=EligibilityReviewResult,
    )
    t4 = Task(
        description="Using only validated prior JSON, return SyntheticResearchBrief. It must await human review.",
        expected_output="Validated SyntheticResearchBrief JSON.",
        agent=writer,
        context=[t1, t2, t3],
        output_pydantic=SyntheticResearchBrief,
    )
    return Crew(
        name="OncologyResearchCrew",
        agents=[researcher, investigator, reviewer, writer],
        tasks=[t1, t2, t3, t4],
        process=Process.sequential,
        verbose=False,
        memory=False,
        tracing=False,
    )
