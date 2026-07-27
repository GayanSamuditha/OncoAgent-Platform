"""Allowlisted, read-only workflow tools over normalized Phase 1 data."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion import (
    Condition,
    DiagnosticReport,
    Encounter,
    MedicationRequest,
    Observation,
    Patient,
    Procedure,
)
from app.retrieval.model_registry import provider_for
from app.retrieval.search import postgres_fts_search, search
from app.workflow.schemas import ToolDescriptor


class ToolExecutionError(Exception):
    def __init__(self, category: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


class PatientRequest(BaseModel):
    dataset_id: str
    patient_id: str


class SearchRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=20, ge=1, le=50)
    retrieval_profile: str = "medcpt"


class DateWindowRequest(BaseModel):
    timestamp: str | None = None
    date_window: dict[str, str]


class ToolExecutionContext:
    def __init__(self, session: Session, settings: Any, actor_role: str) -> None:
        self.session = session
        self.settings = settings
        self.actor_role = actor_role


ToolHandler = Callable[[ToolExecutionContext, BaseModel], dict[str, Any]]


class RegisteredTool:
    def __init__(self, descriptor: ToolDescriptor, request_model: type[BaseModel], handler: ToolHandler) -> None:
        self.descriptor = descriptor
        self.request_model = request_model
        self.handler = handler


def _descriptor(name: str, description: str, roles: list[str], maximum: int = 100) -> ToolDescriptor:
    return ToolDescriptor(name=name, version="phase3a-tool-v1", description=description, allowed_roles=roles, read_only=True, timeout_seconds=10, maximum_result_size=maximum, retry_policy={"max_attempts": 2, "retryable": ["transient_read"]})


def _rows(session: Session, model: type[Any], dataset_id: str, patient_id: str, maximum: int = 100) -> list[dict[str, Any]]:
    rows = session.scalars(select(model).where(model.dataset_id == dataset_id, model.patient_id == patient_id).limit(maximum)).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append({key: (getattr(row, key).isoformat() if isinstance(getattr(row, key), datetime) else getattr(row, key)) for key in ("id", "fhir_id", "encounter_id", "code_system", "code", "display", "status", "clinical_status", "verification_status", "value_numeric", "value_text", "unit", "effective_time", "performed_start", "authored_on", "issued_time", "encounter_type_display", "encounter_class", "start_time", "source_resource_id") if hasattr(row, key)})
    return result


def _demographics(context: ToolExecutionContext, request: BaseModel) -> dict[str, Any]:
    item = request  # validated by registry
    patient_request = PatientRequest.model_validate(item)
    patient = context.session.scalar(select(Patient).where(Patient.id == patient_request.patient_id, Patient.dataset_id == patient_request.dataset_id))
    if patient is None:
        raise ValueError("patient not found in requested dataset")
    return {"patient_id": patient.id, "dataset_id": patient.dataset_id, "fhir_id": patient.fhir_id, "birth_date": patient.birth_date, "gender": patient.gender, "deceased": patient.deceased, "source_resource_id": patient.source_resource_id}


def _resource_handler(model: type[Any]) -> ToolHandler:
    return lambda context, request: {"items": _rows(context.session, model, PatientRequest.model_validate(request).dataset_id, PatientRequest.model_validate(request).patient_id)}


def _search(context: ToolExecutionContext, request: BaseModel) -> dict[str, Any]:
    item = SearchRequest.model_validate(request)
    if item.retrieval_profile == "postgres_fts":
        results, latency = postgres_fts_search(context.session, item.dataset_id, item.query, item.top_k, ["encounter", "patient-summary"], None)
    else:
        provider = provider_for(context.settings, item.retrieval_profile)
        provider.load()
        results, latency = search(context.session, provider, item.dataset_id, item.query, item.top_k, ["encounter", "patient-summary"], None, None)
    return {"items": results, "latency_ms": latency, "retrieval_profile": item.retrieval_profile}


def _date_window(_: ToolExecutionContext, request: BaseModel) -> dict[str, Any]:
    item = DateWindowRequest.model_validate(request)
    if not item.timestamp:
        return {"status": "missing_data", "timestamp": None}
    value = datetime.fromisoformat(item.timestamp.replace("Z", "+00:00")).date()
    start = datetime.fromisoformat(item.date_window["start"]).date()
    end = datetime.fromisoformat(item.date_window["end"]).date()
    return {"status": "verified" if start <= value <= end else "not_verified", "timestamp": item.timestamp}


def build_tool_registry() -> dict[str, RegisteredTool]:
    roles = ["researcher", "reviewer", "admin"]
    return {
        "search_clinical_documents": RegisteredTool(_descriptor("search_clinical_documents", "Generate bounded candidate documents.", roles, 50), SearchRequest, _search),
        "get_patient_demographics": RegisteredTool(_descriptor("get_patient_demographics", "Read synthetic patient demographics.", roles), PatientRequest, _demographics),
        "get_patient_conditions": RegisteredTool(_descriptor("get_patient_conditions", "Read normalized condition facts.", roles), PatientRequest, _resource_handler(Condition)),
        "get_patient_observations": RegisteredTool(_descriptor("get_patient_observations", "Read normalized observation facts.", roles), PatientRequest, _resource_handler(Observation)),
        "get_patient_procedures": RegisteredTool(_descriptor("get_patient_procedures", "Read normalized procedure facts.", roles), PatientRequest, _resource_handler(Procedure)),
        "get_patient_medications": RegisteredTool(_descriptor("get_patient_medications", "Read normalized medication request facts.", roles), PatientRequest, _resource_handler(MedicationRequest)),
        "get_patient_diagnostic_reports": RegisteredTool(_descriptor("get_patient_diagnostic_reports", "Read normalized diagnostic report facts.", roles), PatientRequest, _resource_handler(DiagnosticReport)),
        "get_patient_encounters": RegisteredTool(_descriptor("get_patient_encounters", "Read normalized encounter facts.", roles), PatientRequest, _resource_handler(Encounter)),
        "verify_date_window": RegisteredTool(_descriptor("verify_date_window", "Verify an ISO timestamp against an explicit date window.", roles), DateWindowRequest, _date_window),
        "build_patient_evidence": RegisteredTool(_descriptor("build_patient_evidence", "Assemble provenance-linked evidence from structured facts.", roles), PatientRequest, lambda context, request: {"status": "delegated_to_verification_node"}),
    }


def execute_tool(registry: dict[str, RegisteredTool], name: str, context: ToolExecutionContext, arguments: dict[str, Any]) -> dict[str, Any]:
    registered = registry.get(name)
    if registered is None:
        raise ToolExecutionError("unregistered_tool", f"Tool {name} is not registered")
    if context.actor_role not in registered.descriptor.allowed_roles:
        raise ToolExecutionError("authorization", "Actor role is not allowed for this tool")
    validated = registered.request_model.model_validate(arguments)
    return registered.handler(context, validated)
