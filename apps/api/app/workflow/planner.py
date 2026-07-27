import hashlib
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.workflow.schemas import CohortPlan, Criterion


class PlannerProvider(Protocol):
    provider_id: str

    def plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> CohortPlan: ...


PROMPT_ID = "qwen_cohort_planning"
PROMPT_VERSION = "phase3b-planner-v1"
UNSAFE_REQUEST_PATTERNS = ("ignore the schema", "reveal your system prompt", "hidden thinking", "chain of thought", "use sql", "run a shell", "read .env", "filesystem path", "unregistered tool", "without reviewer", "without a reviewer", "skip approval", "modify the audit", "change the ollama url", "arbitrary http", "clinically validated", "export all", "documented procedure", "receiving medication", "recent hypertension")
PLANNING_SYSTEM_PROMPT = """You convert a synthetic Synthea cohort request into one JSON CohortPlan.
You do not perform clinical decision-making or execute tools. Never create SQL, code,
URLs, paths, mutations, approval decisions, or unregistered tools. Use only the
allowlisted criterion types and tools represented by the provided JSON schema.
Human approval is mandatory. Identify unsupported requests instead of guessing.
Use synthetic-data context only. Do not reveal hidden reasoning; return JSON only.
The only criterion types are minimum_age, maximum_age, gender, condition,
observation, procedure, medication, diagnostic_report, encounter_type, and
date_window. The verification_tool must exactly match the criterion type:
minimum_age/maximum_age/gender=get_patient_demographics,
condition=get_patient_conditions, observation=get_patient_observations,
procedure=get_patient_procedures, medication=get_patient_medications,
diagnostic_report=get_patient_diagnostic_reports,
encounter_type=get_patient_encounters, date_window=verify_date_window.
The only required_tools are those verification tools plus
search_clinical_documents. Never invent a tool name or use a generic tool."""


class LocalPlannerError(RuntimeError):
    def __init__(self, category: str, message: str, retryable: bool = False, lineage: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.lineage = lineage or {}


@dataclass(frozen=True)
class PlannerOutcome:
    plan: CohortPlan
    lineage: dict[str, Any]


def _prompt_hash() -> str:
    return hashlib.sha256(PLANNING_SYSTEM_PROMPT.encode()).hexdigest()


def _schema_hash() -> str:
    return hashlib.sha256(json.dumps(CohortPlan.model_json_schema(), sort_keys=True).encode()).hexdigest()


def _validate_local_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("LOCAL_LLM_BASE_URL must be an HTTP(S) localhost URL")
    hostname = parsed.hostname.lower()
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        try:
            resolved = ipaddress.ip_address(socket.getaddrinfo(hostname, None)[0][4][0])
            if not resolved.is_loopback:
                raise ValueError("LOCAL_LLM_BASE_URL must resolve to localhost")
        except (OSError, IndexError, ValueError) as exc:
            raise ValueError("LOCAL_LLM_BASE_URL must resolve to localhost") from exc
    return base_url.rstrip("/")


class LocalPlannerProvider(Protocol):
    provider_id: str
    runtime: str
    model_name: str

    def generate_cohort_plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> PlannerOutcome: ...
    def health(self) -> dict[str, Any]: ...
    def metadata(self) -> dict[str, Any]: ...


class OllamaQwenPlannerProvider:
    provider_id = "qwen_local"
    runtime = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model_name = settings.local_llm_model
        self.base_url = _validate_local_url(settings.local_llm_base_url)
        self._last_success: str | None = None
        self._last_failure: str | None = None
        self._metadata: dict[str, Any] = {}

    def metadata(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "runtime": self.runtime, "configured_model": self.model_name, "prompt_id": PROMPT_ID, "prompt_version": PROMPT_VERSION, "prompt_content_hash": _prompt_hash(), "cohort_plan_schema_hash": _schema_hash(), "supports_structured_output": True, "supports_thinking_control": True, **self._metadata}

    def health(self) -> dict[str, Any]:
        payload: dict[str, Any] = {**self.metadata(), "installed": False, "available": False, "healthy": False, "loaded": None, "last_successful_request": self._last_success, "last_failure_category": self._last_failure, "limitations": ["Local Ollama service only; no hosted fallback."]}
        if not self.settings.local_llm_enabled:
            payload["last_failure_category"] = "disabled"
            return payload
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            models = response.json().get("models", [])
            match = next((item for item in models if item.get("name") == self.model_name), None)
            payload.update({"available": True, "healthy": True, "installed": match is not None, "resolved_model_digest": (match or {}).get("digest"), "model_size": (match or {}).get("size"), "last_modified": (match or {}).get("modified_at")})
        except Exception:
            payload["last_failure_category"] = "ollama_unavailable"
            self._last_failure = "ollama_unavailable"
        return payload

    def _chat(self, messages: list[dict[str, str]], repair: bool = False) -> tuple[dict[str, Any], str]:
        schema = CohortPlan.model_json_schema()
        body: dict[str, Any] = {"model": self.model_name, "messages": messages, "stream": False, "format": schema, "options": {"temperature": self.settings.local_llm_temperature, "num_ctx": self.settings.local_llm_context_length, "num_predict": self.settings.local_llm_max_output_tokens}, "keep_alive": self.settings.local_llm_keep_alive}
        if not repair:
            body["think"] = self.settings.local_llm_thinking
        modes = ["think_false" if not repair else "repair"]
        if not repair:
            modes.append("no_think_field")
        last: Exception | None = None
        for mode in modes:
            request_body = dict(body)
            if mode == "no_think_field":
                request_body.pop("think", None)
            try:
                with httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(self.settings.local_llm_timeout_seconds, connect=5.0), limits=httpx.Limits(max_connections=2)) as client:
                    response = client.post("/api/chat", json=request_body)
                if len(response.content) > self.settings.local_llm_max_response_bytes:
                    raise LocalPlannerError("malformed_response", "Ollama response exceeded configured size limit")
                if response.status_code == 404:
                    raise LocalPlannerError("model_not_installed", f"Ollama model {self.model_name} is not installed")
                response.raise_for_status()
                return response.json(), mode
            except LocalPlannerError:
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last = exc
                continue
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last = exc
                break
        raise LocalPlannerError("request_timeout" if isinstance(last, httpx.TimeoutException) else "generation_failure", str(last or "Ollama request failed"), True)

    def generate_cohort_plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> PlannerOutcome:
        if not self.settings.local_llm_enabled:
            raise LocalPlannerError("disabled", "Local planner is disabled")
        lowered_request = request.lower()
        if any(pattern in lowered_request for pattern in UNSAFE_REQUEST_PATTERNS):
            raise LocalPlannerError("prompt_injection_policy_failure", "request conflicts with planner safety policy")
        started = time.perf_counter()
        user = json.dumps({"dataset_id": dataset_id, "request": request, "criteria": [item.model_dump(mode="json") for item in criteria or []], "max_candidates": max_candidates})
        messages = [{"role": "system", "content": PLANNING_SYSTEM_PROMPT}, {"role": "user", "content": user}]
        response, mode = self._chat(messages)
        content = response.get("message", {}).get("content")
        if not isinstance(content, str):
            raise LocalPlannerError("malformed_response", "Ollama response did not contain message.content")
        try:
            plan = CohortPlan.model_validate_json(content)
        except Exception as exc:
            repair_prompt = f"Return only a valid CohortPlan JSON object. Validation error: {str(exc)[:1000]}"
            repaired, repair_mode = self._chat(messages + [{"role": "user", "content": repair_prompt}], repair=True)
            repaired_content = repaired.get("message", {}).get("content")
            if not isinstance(repaired_content, str):
                raise LocalPlannerError("schema_validation_failure", "repair response was not JSON") from exc
            try:
                plan = CohortPlan.model_validate_json(repaired_content)
            except Exception as repair_exc:
                raise LocalPlannerError("schema_validation_failure", str(repair_exc)) from repair_exc
            mode = f"{mode}+repair:{repair_mode}"
        try:
            validate_plan_output(plan, dataset_id, max_candidates)
        except LocalPlannerError as exc:
            exc.lineage = {"compatibility_mode": mode, "schema_version": "cohort-plan-v1", "model_load_duration_ms": (response.get("load_duration") or 0) / 1_000_000, "prompt_evaluation_duration_ms": (response.get("prompt_eval_duration") or 0) / 1_000_000, "generation_duration_ms": (response.get("eval_duration") or 0) / 1_000_000, "prompt_token_count": response.get("prompt_eval_count"), "generated_token_count": response.get("eval_count")}
            raise
        self._last_success = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        health = self.health()
        self._metadata.update({"resolved_model_digest": health.get("resolved_model_digest") or response.get("model", self.model_name), "compatibility_mode": mode})
        return PlannerOutcome(plan, {**self.metadata(), "schema_version": "cohort-plan-v1", "request_duration_ms": (time.perf_counter() - started) * 1000, "model_load_duration_ms": (response.get("load_duration") or 0) / 1_000_000, "prompt_evaluation_duration_ms": (response.get("prompt_eval_duration") or 0) / 1_000_000, "generation_duration_ms": (response.get("eval_duration") or 0) / 1_000_000, "prompt_token_count": response.get("prompt_eval_count"), "generated_token_count": response.get("eval_count"), "repair_attempts": 1 if "repair" in mode else 0})


class DeterministicFakeLocalPlannerProvider:
    provider_id = "fake_local_planner"
    runtime = "test"
    model_name = "fake-qwen"

    def generate_cohort_plan(self, request: str, dataset_id: str, criteria: list[Criterion] | None, max_candidates: int) -> PlannerOutcome:
        plan = DeterministicCohortPlanner().plan(request, dataset_id, criteria, max_candidates)
        return PlannerOutcome(plan, {"provider_id": self.provider_id, "runtime": self.runtime, "configured_model": self.model_name, "prompt_version": "test", "compatibility_mode": "fake"})

    def health(self) -> dict[str, Any]:
        return {"provider_id": self.provider_id, "runtime": self.runtime, "available": True, "healthy": True}

    def metadata(self) -> dict[str, Any]:
        return self.health()


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


def validate_plan_output(plan: CohortPlan, dataset_id: str, max_candidates: int) -> None:
    """Apply platform policy after JSON-schema validation and before execution."""
    if plan.dataset_id != dataset_id:
        raise LocalPlannerError("schema_policy_violation", "planner dataset does not match the requested dataset")
    if not plan.approval_required:
        raise LocalPlannerError("schema_policy_violation", "human approval is mandatory")
    if plan.max_candidates > max_candidates:
        raise LocalPlannerError("schema_policy_violation", "planner exceeded the requested candidate limit")
    allowed_tools = set(TOOL_BY_TYPE.values()) | {"search_clinical_documents"}
    if set(plan.required_tools) - allowed_tools:
        raise LocalPlannerError("schema_policy_violation", "planner emitted an unregistered tool")
    expected_tools = {TOOL_BY_TYPE[item.criterion_type] for item in plan.criteria}
    for criterion in plan.criteria:
        if criterion.verification_tool not in allowed_tools or criterion.verification_tool != TOOL_BY_TYPE[criterion.criterion_type]:
            raise LocalPlannerError("schema_policy_violation", "criterion verification tool is not allowlisted for its type")
    if not expected_tools.issubset(set(plan.required_tools)) or "search_clinical_documents" not in plan.required_tools:
        raise LocalPlannerError("schema_policy_violation", "required tool set is incomplete")


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
