"""MCP transport boundary over the existing platform tool registry."""

import json
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

try:
    from opentelemetry import context as otel_context
    from opentelemetry.propagate import extract as extract_trace_context
except ImportError:  # pragma: no cover - optional observability boundary
    otel_context = None  # type: ignore[assignment]
    extract_trace_context = None  # type: ignore[assignment]

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.ingestion import Dataset
from app.models.mcp import MCPRequest
from app.observability.metrics import (
    MCP_AUTH_FAILURES,
    MCP_DATASET_DENIALS,
    MCP_DURATION,
    MCP_ERRORS,
    MCP_FALLBACKS,
    MCP_REQUESTS,
    MCP_TOOL_CALLS,
    observe,
)
from app.observability.telemetry import current_trace_context, span
from app.retrieval.model_registry import provider_for
from app.retrieval.search import postgres_fts_search, search
from app.workflow.tools import (
    DateWindowRequest,
    PatientRequest,
    ToolExecutionContext,
    build_tool_registry,
    execute_tool,
)
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import MCPAuthError, MCPClientIdentity, authenticate, headers_from_context

TOOL_VERSION = "phase3a-tool-v1"
MCP_PROTOCOL_VERSION = "2025-06-18"
ALLOWED_PROFILES = {"medcpt", "bioclinicalbert", "postgres_fts"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MCPPatientRequest(StrictModel):
    dataset_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)


class MCPSearchRequest(StrictModel):
    dataset_id: str = Field(min_length=1)
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=20, ge=1, le=50)
    retrieval_profile: str = "medcpt"


class MCPDateWindowRequest(StrictModel):
    dataset_id: str = Field(min_length=1)
    timestamp: str | None = None
    date_window: dict[str, str]


class MCPError(StrictModel):
    category: str
    message: str
    retryable: bool = False


def _error(category: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"error": MCPError(category=category, message=message, retryable=retryable).model_dump(), "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}


def _headers_from_context(context: Context[Any, Any, Any] | None) -> dict[str, str]:
    return headers_from_context(context) if context is not None else {}


class MCPGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = build_tool_registry()
        self._stdio_mode = False
        self.server = FastMCP("OncoAgent Platform MCP Gateway", instructions="Read-only synthetic clinical tools. Retrieval is candidate generation only; structured FHIR verification remains authoritative.", host=self.settings.mcp_host, port=self.settings.mcp_port, streamable_http_path="/mcp")
        self._register_tools()

    def _identity(self, context: Context[Any, Any, Any] | None, stdio: bool = False) -> MCPClientIdentity:
        if not self.settings.mcp_enabled:
            raise MCPAuthError("authorization_denied", "MCP gateway is disabled by platform policy")
        return authenticate(self.settings, _headers_from_context(context), stdio=stdio)

    def _dataset(self, identity: MCPClientIdentity, dataset_id: str) -> None:
        if "*" not in identity.dataset_ids and dataset_id not in identity.dataset_ids:
            raise MCPAuthError("dataset_not_allowed", "client is not authorized for the requested dataset")
        with SessionLocal() as session:
            dataset = session.get(Dataset, dataset_id)
        if dataset is None:
            raise MCPAuthError("dataset_not_found", "requested dataset was not found")
        if dataset.source_format and "Synthea" not in dataset.source_format:
            raise MCPAuthError("dataset_not_allowed", "only synthetic Synthea datasets are supported")

    def _safe_args(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = dict(arguments)
        if "query" in result and isinstance(result["query"], str):
            result["query"] = f"<query length={len(result['query'])}>"
        return {key: value for key, value in result.items() if key not in {"token", "authorization", "headers"}}

    def _audit(self, request_id: str, identity: MCPClientIdentity, tool_name: str, arguments: dict[str, Any], dataset_id: str | None, status: str, started: datetime, latency_ms: float, result_count: int, response_size: int, error_category: str | None = None, fallback_reason: str | None = None, retrieval_lineage: dict[str, Any] | None = None) -> None:
        trace_context = current_trace_context()
        with SessionLocal.begin() as session:
            session.add(MCPRequest(id=request_id, protocol_version=MCP_PROTOCOL_VERSION, server_version=self.settings.app_version, client_id=identity.client_id, actor_id=identity.actor_id, actor_role=identity.actor_role, client_type=identity.client_type, correlation_id=str(uuid4()), tool_name=tool_name, tool_version=TOOL_VERSION, dataset_id=dataset_id, sanitized_arguments=self._safe_args(arguments), status=status, result_count=result_count, response_size_bytes=response_size, latency_ms=latency_ms, error_category=error_category, fallback_reason=fallback_reason, retrieval_lineage=retrieval_lineage or {}, started_at=started, completed_at=datetime.now(UTC), trace_id=trace_context["trace_id"], span_id=trace_context["span_id"]))

    def _search(self, identity: MCPClientIdentity, request: MCPSearchRequest) -> tuple[dict[str, Any], dict[str, Any]]:
        if request.retrieval_profile not in ALLOWED_PROFILES:
            raise MCPAuthError("invalid_arguments", "retrieval profile is not allowlisted")
        attempts: list[dict[str, Any]] = []
        fallbacks: list[dict[str, Any]] = []
        last_error = ""
        for profile in (request.retrieval_profile, "bioclinicalbert", "postgres_fts"):
            if profile in {item["provider"] for item in attempts}:
                continue
            started = time.perf_counter()
            try:
                with SessionLocal() as session:
                    if profile == "postgres_fts":
                        items, latency = postgres_fts_search(session, request.dataset_id, request.query, min(request.top_k, self.settings.mcp_max_results), ["encounter", "patient-summary"], None)
                    else:
                        provider = provider_for(self.settings, profile)
                        provider.load()
                        items, latency = search(session, provider, request.dataset_id, request.query, min(request.top_k, self.settings.mcp_max_results), ["encounter", "patient-summary"], None, None)
                attempts.append({"provider": profile, "status": "success", "latency_ms": latency, "duration_ms": (time.perf_counter() - started) * 1000})
                if profile != request.retrieval_profile:
                    fallbacks.append({"from": request.retrieval_profile, "to": profile, "reason": last_error or "primary provider unavailable"})
                return {"items": items, "latency_ms": latency, "requested_retrieval_profile": request.retrieval_profile, "actual_retrieval_profile": profile, "retrieval_attempts": attempts, "retrieval_fallbacks": fallbacks}, {"attempts": attempts, "fallbacks": fallbacks, "actual_provider": profile}
            except (RuntimeError, ValueError, OSError) as exc:
                last_error = f"{type(exc).__name__}: provider unavailable"
                attempts.append({"provider": profile, "status": "failed", "duration_ms": (time.perf_counter() - started) * 1000, "error_category": "provider_unavailable"})
        raise RuntimeError("all retrieval providers are unavailable")

    def execute(self, tool_name: str, arguments: dict[str, Any], context: Context[Any, Any, Any] | None = None, stdio: bool = False) -> dict[str, Any]:
        """Execute a tool under the caller's W3C trace context.

        The attach/detach pair is scoped to this synchronous tool callback,
        not to the surrounding ASGI request task. This preserves propagation
        without crossing Starlette/AnyIO task boundaries.
        """
        token = None
        if otel_context is not None and extract_trace_context is not None:
            token = otel_context.attach(extract_trace_context(_headers_from_context(context)))
        try:
            return self._execute(tool_name, arguments, context, stdio)
        finally:
            if token is not None:
                otel_context.detach(token)

    def _execute(self, tool_name: str, arguments: dict[str, Any], context: Context[Any, Any, Any] | None = None, stdio: bool = False) -> dict[str, Any]:
        request_id = str(uuid4())
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        identity: MCPClientIdentity | None = None
        dataset_id = arguments.get("dataset_id") if isinstance(arguments.get("dataset_id"), str) else None
        with span("mcp.tool.call", self.settings, {"mcp.tool": tool_name, "mcp.transport": "stdio" if stdio else "streamable-http"}):
          try:
            with span("mcp.authentication", self.settings, {"mcp.status": "checked"}):
                identity = self._identity(context, stdio=stdio or self._stdio_mode)
            if tool_name not in self.registry:
                raise MCPAuthError("unknown_tool", "tool is not registered")
            with span("mcp.authorization", self.settings, {"mcp.status": "checked"}):
                if identity.actor_role not in self.registry[tool_name].descriptor.allowed_roles:
                    raise MCPAuthError("authorization_denied", "actor role is not allowed for this tool")
            request: Any = None
            validated_request: Any = None
            if tool_name == "search_clinical_documents":
                request = MCPSearchRequest.model_validate(arguments)
                validated_request = request
                dataset_id = request.dataset_id
            elif tool_name == "verify_date_window":
                request = MCPDateWindowRequest.model_validate(arguments)
                validated_request = request
                dataset_id = request.dataset_id
            else:
                request = MCPPatientRequest.model_validate(arguments)
                validated_request = request
                dataset_id = request.dataset_id
            if dataset_id:
                with span("mcp.dataset.policy", self.settings, {"mcp.status": "checked"}):
                    self._dataset(identity, dataset_id)
            if tool_name == "search_clinical_documents":
                request = MCPSearchRequest.model_validate(validated_request.model_dump())
                result, lineage = self._search(identity, request)
            elif tool_name == "verify_date_window":
                request = MCPDateWindowRequest.model_validate(validated_request.model_dump())
                with SessionLocal() as session:
                    result = execute_tool(self.registry, tool_name, ToolExecutionContext(session, self.settings, identity.actor_role), DateWindowRequest.model_validate(request.model_dump(exclude={"dataset_id"})).model_dump())
                lineage = {}
            else:
                request = MCPPatientRequest.model_validate(validated_request.model_dump())
                with SessionLocal() as session:
                    result = execute_tool(self.registry, tool_name, ToolExecutionContext(session, self.settings, identity.actor_role), PatientRequest.model_validate(request.model_dump()).model_dump())
                lineage = {}
            if tool_name == "build_patient_evidence":
                result = {"status": "structured_facts_available", "patient_id": arguments.get("patient_id"), "dataset_id": dataset_id, "facts": result, "evidence_notice": "Facts are not cohort inclusion decisions; structured verification and human approval remain required."}
            response = {**result, "tool_name": tool_name, "tool_version": TOOL_VERSION, "correlation_id": request_id, "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}
            with span("mcp.result.validation", self.settings, {"mcp.status": "validated"}):
                encoded = json.dumps(response, default=str).encode()
            if len(encoded) > self.settings.mcp_max_response_bytes:
                raise MCPAuthError("result_limit_exceeded", "MCP response exceeded the configured size limit")
            result_count = len(result.get("items", [])) if isinstance(result.get("items"), list) else 1
            self._audit(request_id, identity, tool_name, arguments, dataset_id, "success", started_at, (time.perf_counter() - started) * 1000, result_count, len(encoded), retrieval_lineage=lineage)
            observe(MCP_REQUESTS, labels={"tool": tool_name, "status": "success", "transport": "stdio" if stdio else "streamable-http"})
            observe(MCP_TOOL_CALLS, labels={"tool": tool_name})
            observe(MCP_DURATION, (time.perf_counter() - started), {"tool": tool_name})
            if lineage.get("fallbacks"):
                for item in lineage["fallbacks"]:
                    observe(MCP_FALLBACKS, labels={"provider": str(item.get("to", "unknown"))})
            return response
          except ValidationError:
            error = _error("invalid_arguments", "tool arguments did not satisfy the registered schema")
            category = "invalid_arguments"
          except MCPAuthError as exc:
            error = _error(exc.category, str(exc))
            category = exc.category
          except TimeoutError:
            error = _error("timeout", "tool execution timed out", True)
            category = "timeout"
          except RuntimeError as exc:
            error = _error("provider_unavailable", str(exc), True)
            category = "provider_unavailable"
          except (ValueError, OSError):
            error = _error("structured_data_unavailable", "structured synthetic data could not be read", True)
            category = "structured_data_unavailable"
          except Exception:  # noqa: BLE001  # pragma: no cover - safe transport boundary
            error = _error("internal_safe_failure", "MCP tool execution failed safely")
            category = "internal_safe_failure"
          if identity is not None:
              self._audit(request_id, identity, tool_name, arguments, dataset_id, "error", started_at, (time.perf_counter() - started) * 1000, 0, len(json.dumps(error)), error_category=category)
          observe(MCP_ERRORS, labels={"tool": tool_name, "error_category": category})
          if category in {"authentication_failed", "unknown_client"}:
              observe(MCP_AUTH_FAILURES)
          if category == "dataset_not_allowed":
              observe(MCP_DATASET_DENIALS)
          observe(MCP_REQUESTS, labels={"tool": tool_name, "status": "error", "transport": "stdio" if stdio else "streamable-http"})
          return {**error, "tool_name": tool_name, "tool_version": TOOL_VERSION, "correlation_id": request_id}

    def _register_tools(self) -> None:
        @self.server.tool(name="search_clinical_documents", description="Search bounded synthetic clinical documents using the allowlisted retrieval policy.", structured_output=True)
        async def search_clinical_documents(request: MCPSearchRequest, ctx: Context[Any, Any, Any]) -> dict[str, Any]:
            return self.execute("search_clinical_documents", request.model_dump(), ctx)

        @self.server.tool(name="get_patient_demographics", description="Read bounded synthetic patient demographics.", structured_output=True)
        async def get_patient_demographics(request: MCPPatientRequest, ctx: Context[Any, Any, Any]) -> dict[str, Any]:
            return self.execute("get_patient_demographics", request.model_dump(), ctx)

        for name, description in {
            "get_patient_conditions": "Read normalized synthetic condition facts.",
            "get_patient_observations": "Read normalized synthetic observation facts.",
            "get_patient_procedures": "Read normalized synthetic procedure facts.",
            "get_patient_medications": "Read normalized synthetic medication request facts.",
            "get_patient_diagnostic_reports": "Read normalized synthetic diagnostic report facts.",
            "get_patient_encounters": "Read normalized synthetic encounter facts.",
            "build_patient_evidence": "Build a bounded provenance-linked summary of structured patient facts.",
        }.items():
            def make_resource_tool(tool_name: str) -> Any:
                async def resource_tool(request: MCPPatientRequest, ctx: Context[Any, Any, Any]) -> dict[str, Any]:
                    return self.execute(tool_name, request.model_dump(), ctx)
                resource_tool.__name__ = tool_name
                return resource_tool
            self.server.tool(name=name, description=description, structured_output=True)(make_resource_tool(name))

        @self.server.tool(name="verify_date_window", description="Verify a timestamp against an explicit bounded date window.", structured_output=True)
        async def verify_date_window(request: MCPDateWindowRequest, ctx: Context[Any, Any, Any]) -> dict[str, Any]:
            return self.execute("verify_date_window", request.model_dump(), ctx)

    def metadata(self) -> dict[str, Any]:
        return {"server_name": "OncoAgent Platform MCP Gateway", "server_version": self.settings.app_version, "protocol_version": MCP_PROTOCOL_VERSION, "enabled": self.settings.mcp_enabled, "streamable_http_enabled": self.settings.mcp_streamable_http_enabled, "stdio_enabled": self.settings.mcp_stdio_enabled, "host": self.settings.mcp_host, "port": self.settings.mcp_port, "tools": [{"name": item.descriptor.name, "version": TOOL_VERSION, "read_only": True} for item in self.registry.values()], "synthetic_data_notice": "Synthetic Synthea data only.", "clinical_validation_notice": "Not clinically validated."}

    async def run_stdio(self) -> None:
        if not self.settings.mcp_enabled or not self.settings.mcp_stdio_enabled:
            return
        self._stdio_mode = True
        await self.server.run_stdio_async()

    async def run_http(self) -> None:
        if not self.settings.mcp_enabled or not self.settings.mcp_streamable_http_enabled:
            return
        await self.server.run_streamable_http_async()
