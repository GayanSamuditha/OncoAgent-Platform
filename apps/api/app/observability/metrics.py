"""Low-cardinality Prometheus metrics."""

from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest
except ImportError:  # pragma: no cover - optional dependency boundary
    Counter = Gauge = Histogram = None  # type: ignore[assignment,misc]


def _counter(name: str, documentation: str, labels: tuple[str, ...] = ()) -> Any:
    return Counter(name, documentation, labels) if Counter is not None else None


def _histogram(name: str, documentation: str, labels: tuple[str, ...] = ()) -> Any:
    return Histogram(name, documentation, labels) if Histogram is not None else None


def _gauge(name: str, documentation: str, labels: tuple[str, ...] = ()) -> Any:
    return Gauge(name, documentation, labels) if Gauge is not None else None


HTTP_REQUESTS = _counter("oncoagent_http_requests_total", "HTTP requests", ("service", "route", "method", "status_class"))
HTTP_ERRORS = _counter("oncoagent_http_errors_total", "HTTP errors", ("service", "route", "error_category"))
HTTP_DURATION = _histogram("oncoagent_http_request_duration_seconds", "HTTP request duration", ("service", "route", "method"))
ACTIVE_REQUESTS = _gauge("oncoagent_active_requests", "Active HTTP requests", ("service",))
WORKFLOW_RUNS = _counter("oncoagent_workflow_runs_total", "Workflow runs", ("status", "outcome"))
WORKFLOW_DURATION = _histogram("oncoagent_workflow_run_duration_seconds", "Workflow duration", ("status",))
WORKFLOW_NODE_DURATION = _histogram("oncoagent_workflow_node_duration_seconds", "Workflow node duration", ("node", "status"))
WORKFLOW_FAILURES = _counter("oncoagent_workflow_failures_total", "Workflow failures", ("error_category",))
WORKFLOW_FALLBACKS = _counter("oncoagent_workflow_fallbacks_total", "Workflow fallbacks", ("provider",))
AWAITING_APPROVAL = _gauge("oncoagent_workflows_awaiting_approval", "Workflows awaiting approval")
CHECKPOINT_RESUMES = _counter("oncoagent_checkpoint_resumes_total", "Checkpoint resumes")
CREW_RUNS = _counter("oncoagent_crew_runs_total", "CrewAI runs", ("status",))
CREW_DURATION = _histogram("oncoagent_crew_run_duration_seconds", "CrewAI duration", ("status",))
CREW_TASK_DURATION = _histogram("oncoagent_crew_task_duration_seconds", "CrewAI task duration", ("task", "status"))
CREW_FAILURES = _counter("oncoagent_crew_failures_total", "CrewAI failures", ("error_category",))
CREW_INTERRUPTS = _counter("oncoagent_crew_process_interruptions_total", "CrewAI process interruptions")
CREW_AWAITING_REVIEW = _gauge("oncoagent_crew_runs_awaiting_review", "CrewAI runs awaiting review")
CREW_MCP_CALLS = _counter("oncoagent_crew_mcp_calls_total", "CrewAI MCP calls", ("tool", "status"))
MCP_REQUESTS = _counter("oncoagent_mcp_requests_total", "MCP requests", ("tool", "status", "transport"))
MCP_DURATION = _histogram("oncoagent_mcp_request_duration_seconds", "MCP request duration", ("tool",))
MCP_ERRORS = _counter("oncoagent_mcp_errors_total", "MCP errors", ("tool", "error_category"))
MCP_AUTH_FAILURES = _counter("oncoagent_mcp_auth_failures_total", "MCP authentication failures")
MCP_DATASET_DENIALS = _counter("oncoagent_mcp_dataset_denials_total", "MCP dataset denials")
MCP_TOOL_CALLS = _counter("oncoagent_mcp_tool_calls_total", "MCP tool calls", ("tool",))
MCP_FALLBACKS = _counter("oncoagent_mcp_fallbacks_total", "MCP retrieval fallbacks", ("provider",))
MODEL_REQUESTS = _counter("oncoagent_model_requests_total", "Model requests", ("model", "status"))
MODEL_DURATION = _histogram("oncoagent_model_request_duration_seconds", "Model duration", ("model",))
MODEL_FALLBACKS = _counter("oncoagent_model_fallbacks_total", "Model fallbacks", ("model",))
MODEL_SCHEMA_FAILURES = _counter("oncoagent_model_schema_failures_total", "Model schema failures", ("model",))
MODEL_INPUT_TOKENS = _counter("oncoagent_model_input_tokens_total", "Model input tokens", ("model",))
MODEL_OUTPUT_TOKENS = _counter("oncoagent_model_output_tokens_total", "Model output tokens", ("model",))
GOVERNANCE_VIOLATIONS = _counter("oncoagent_governance_violations_total", "Governance violations", ("category",))
UNSAFE_PREVENTED = _counter("oncoagent_unsafe_requests_prevented_total", "Unsafe requests prevented", ("category",))
PROVENANCE_FAILURES = _counter("oncoagent_provenance_validation_failures_total", "Provenance validation failures")
AUDIT_FAILURES = _counter("oncoagent_audit_validation_failures_total", "Audit validation failures")
ORPHAN_MCP = _gauge("oncoagent_orphan_mcp_requests", "Orphan MCP requests")
GOVERNANCE_GATE = _gauge("oncoagent_governance_gate_status", "Governance gate status", ("framework", "gate"))
DATABASE_DURATION = _histogram("oncoagent_database_operation_duration_seconds", "Database operation duration", ("operation",))
DATABASE_ERRORS = _counter("oncoagent_database_errors_total", "Database errors", ("operation",))
RETRIEVAL_REQUESTS = _counter("oncoagent_retrieval_requests_total", "Retrieval requests", ("provider", "status"))
RETRIEVAL_DURATION = _histogram("oncoagent_retrieval_request_duration_seconds", "Retrieval duration", ("provider",))
RETRIEVAL_ZERO_RESULTS = _counter("oncoagent_retrieval_zero_results_total", "Retrieval zero-result requests", ("provider",))


def observe(metric: Any, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
    if metric is None:
        return
    child = metric.labels(**labels) if labels else metric
    if hasattr(child, "observe"):
        child.observe(value)
    elif hasattr(child, "inc"):
        child.inc(value)
    elif hasattr(child, "set"):
        child.set(value)


def prometheus_payload() -> tuple[bytes, str]:
    if generate_latest is None:
        return b"# observability metrics dependency unavailable\n", "text/plain; version=0.0.4"
    return generate_latest(), "text/plain; version=0.0.4; charset=utf-8"
