"""Bounded local execution service and safe structured fallback."""

import hashlib
import json
from typing import Any

from .mcp_client import MCPClientProtocol
from .policy import validate_request
from .schemas import CrewRunRequest, SyntheticResearchBrief
from .validation import summarize_task_outputs, validate_brief


class CrewExecutionService:
    def __init__(self, settings: Any, client: MCPClientProtocol) -> None:
        self.settings, self.client = settings, client
        self.last_execution: dict[str, Any] = {
            "used_fallback": False,
            "fallback_reason": None,
            "task_summaries": {},
        }

    def deterministic_run(self, request: CrewRunRequest, run_id: str) -> SyntheticResearchBrief:
        """A safe non-generative fallback used when CrewAI/Ollama is unavailable."""
        query = request.research_question
        search = self.client.call(
            "search_clinical_documents",
            {
                "dataset_id": request.dataset_id,
                "query": query,
                "top_k": request.maximum_candidates,
                "retrieval_profile": request.retrieval_profile,
            },
        )
        items = search.result.get("items", [])
        patient_ids = list(
            dict.fromkeys(str(item.get("patient_id")) for item in items if item.get("patient_id"))
        )[: request.maximum_candidates]
        evidence: list[dict[str, Any]] = []
        for patient_id in patient_ids:
            result = self.client.call(
                "build_patient_evidence",
                {"dataset_id": request.dataset_id, "patient_id": patient_id},
            )
            evidence.append(
                {
                    "patient_id": patient_id,
                    "source": result.result.get("facts", {}),
                    "source_resource_ids": result.result.get("facts", {}).get(
                        "source_resource_ids", []
                    ),
                }
            )
        brief = SyntheticResearchBrief(
            run_id=run_id,
            dataset_id=request.dataset_id,
            research_question=request.research_question,
            methods_summary="Deterministic MCP-only fallback; retrieval generated candidates and structured evidence was collected.",
            retrieval_summary={
                "requested_profile": request.retrieval_profile,
                "actual_profile": search.result.get("actual_retrieval_profile"),
                "fallbacks": search.result.get("retrieval_fallbacks", []),
            },
            candidate_count=len(patient_ids),
            proposed_included_count=0,
            proposed_excluded_count=len(patient_ids),
            unresolved_count=len(patient_ids),
            patient_summaries=evidence,
            evidence_limitations=["Deterministic fallback does not make inclusion decisions."],
            provenance_summary={
                "source_resource_ids": [
                    x for item in evidence for x in item.get("source_resource_ids", [])
                ]
            },
            model_lineage={"provider": "deterministic"},
            mcp_lineage={"request_ids": getattr(self.client, "request_ids", [])},
            review_status="awaiting_human_review",
        )
        validate_brief(brief, run_id, request.dataset_id)
        return brief

    def run(self, request: CrewRunRequest, run_id: str) -> SyntheticResearchBrief:
        allowed = {item for item in self.settings.crewai_mcp_dataset_ids.split(",") if item}
        validate_request(request, allowed)
        try:
            from .crew import build_crew

            model = (
                self.settings.crewai_default_model
                if request.model_profile == "automatic"
                else request.model_profile
            )
            result = build_crew(self.client, model, self.settings).kickoff(
                inputs={"run_id": run_id, **request.model_dump(exclude={"actor_context"})}
            )
            output = getattr(result, "pydantic", None)
            if output is None:
                raise ValueError("CrewAI output did not satisfy the required brief schema")
            brief = SyntheticResearchBrief.model_validate(
                output.model_dump() if hasattr(output, "model_dump") else output
            )
            self.last_execution = {
                "used_fallback": False,
                "fallback_reason": None,
                "task_summaries": summarize_task_outputs(result),
            }
            validate_brief(brief, run_id, request.dataset_id)
            return brief
        except Exception as exc:
            # No unsafe partial output is returned. The caller records the
            # fallback event and may invoke deterministic_run explicitly.
            self.last_execution = {
                "used_fallback": True,
                "fallback_reason": type(exc).__name__,
                "task_summaries": {},
            }
            return self.deterministic_run(request, run_id)

    @staticmethod
    def config_hash(settings: Any) -> str:
        value = json.dumps(
            {
                "crew_version": "phase4b-v1",
                "max_calls": settings.crewai_max_tool_calls_per_run,
                "memory": False,
                "delegation": False,
            },
            sort_keys=True,
        )
        return hashlib.sha256(value.encode()).hexdigest()
