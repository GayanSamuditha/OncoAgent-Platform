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


HTTP_REQUESTS = _counter(
    "oncoagent_http_requests_total", "HTTP requests", ("service", "route", "method", "status_class")
)
HTTP_ERRORS = _counter(
    "oncoagent_http_errors_total", "HTTP errors", ("service", "route", "error_category")
)
HTTP_DURATION = _histogram(
    "oncoagent_http_request_duration_seconds",
    "HTTP request duration",
    ("service", "route", "method"),
)
ACTIVE_REQUESTS = _gauge("oncoagent_active_requests", "Active HTTP requests", ("service",))
WORKFLOW_RUNS = _counter("oncoagent_workflow_runs_total", "Workflow runs", ("status", "outcome"))
WORKFLOW_DURATION = _histogram(
    "oncoagent_workflow_run_duration_seconds", "Workflow duration", ("status",)
)
WORKFLOW_NODE_DURATION = _histogram(
    "oncoagent_workflow_node_duration_seconds", "Workflow node duration", ("node", "status")
)
WORKFLOW_FAILURES = _counter(
    "oncoagent_workflow_failures_total", "Workflow failures", ("error_category",)
)
WORKFLOW_FALLBACKS = _counter(
    "oncoagent_workflow_fallbacks_total", "Workflow fallbacks", ("provider",)
)
AWAITING_APPROVAL = _gauge("oncoagent_workflows_awaiting_approval", "Workflows awaiting approval")
CHECKPOINT_RESUMES = _counter("oncoagent_checkpoint_resumes_total", "Checkpoint resumes")
CREW_RUNS = _counter("oncoagent_crew_runs_total", "CrewAI runs", ("status",))
CREW_DURATION = _histogram("oncoagent_crew_run_duration_seconds", "CrewAI duration", ("status",))
CREW_TASK_DURATION = _histogram(
    "oncoagent_crew_task_duration_seconds", "CrewAI task duration", ("task", "status")
)
CREW_FAILURES = _counter("oncoagent_crew_failures_total", "CrewAI failures", ("error_category",))
CREW_INTERRUPTS = _counter(
    "oncoagent_crew_process_interruptions_total", "CrewAI process interruptions"
)
CREW_AWAITING_REVIEW = _gauge("oncoagent_crew_runs_awaiting_review", "CrewAI runs awaiting review")
CREW_MCP_CALLS = _counter("oncoagent_crew_mcp_calls_total", "CrewAI MCP calls", ("tool", "status"))
MCP_REQUESTS = _counter(
    "oncoagent_mcp_requests_total", "MCP requests", ("tool", "status", "transport")
)
MCP_DURATION = _histogram(
    "oncoagent_mcp_request_duration_seconds", "MCP request duration", ("tool",)
)
MCP_ERRORS = _counter("oncoagent_mcp_errors_total", "MCP errors", ("tool", "error_category"))
MCP_AUTH_FAILURES = _counter("oncoagent_mcp_auth_failures_total", "MCP authentication failures")
MCP_DATASET_DENIALS = _counter("oncoagent_mcp_dataset_denials_total", "MCP dataset denials")
MCP_TOOL_CALLS = _counter("oncoagent_mcp_tool_calls_total", "MCP tool calls", ("tool",))
MCP_FALLBACKS = _counter("oncoagent_mcp_fallbacks_total", "MCP retrieval fallbacks", ("provider",))
MODEL_REQUESTS = _counter("oncoagent_model_requests_total", "Model requests", ("model", "status"))
MODEL_DURATION = _histogram(
    "oncoagent_model_request_duration_seconds", "Model duration", ("model",)
)
MODEL_FALLBACKS = _counter("oncoagent_model_fallbacks_total", "Model fallbacks", ("model",))
MODEL_SCHEMA_FAILURES = _counter(
    "oncoagent_model_schema_failures_total", "Model schema failures", ("model",)
)
MODEL_INPUT_TOKENS = _counter(
    "oncoagent_model_input_tokens_total", "Model input tokens", ("model",)
)
MODEL_OUTPUT_TOKENS = _counter(
    "oncoagent_model_output_tokens_total", "Model output tokens", ("model",)
)
GOVERNANCE_VIOLATIONS = _counter(
    "oncoagent_governance_violations_total", "Governance violations", ("category",)
)
UNSAFE_PREVENTED = _counter(
    "oncoagent_unsafe_requests_prevented_total", "Unsafe requests prevented", ("category",)
)
PROVENANCE_FAILURES = _counter(
    "oncoagent_provenance_validation_failures_total", "Provenance validation failures"
)
AUDIT_FAILURES = _counter("oncoagent_audit_validation_failures_total", "Audit validation failures")
ORPHAN_MCP = _gauge("oncoagent_orphan_mcp_requests", "Orphan MCP requests")
GOVERNANCE_GATE = _gauge(
    "oncoagent_governance_gate_status", "Governance gate status", ("framework", "gate")
)
DATABASE_DURATION = _histogram(
    "oncoagent_database_operation_duration_seconds", "Database operation duration", ("operation",)
)
DATABASE_ERRORS = _counter("oncoagent_database_errors_total", "Database errors", ("operation",))
RETRIEVAL_REQUESTS = _counter(
    "oncoagent_retrieval_requests_total", "Retrieval requests", ("provider", "status")
)
RETRIEVAL_DURATION = _histogram(
    "oncoagent_retrieval_request_duration_seconds", "Retrieval duration", ("provider",)
)
RETRIEVAL_ZERO_RESULTS = _counter(
    "oncoagent_retrieval_zero_results_total", "Retrieval zero-result requests", ("provider",)
)
TEMPORAL_WORKFLOWS = _counter(
    "oncoagent_temporal_workflows_total", "Temporal workflow outcomes", ("status",)
)
TEMPORAL_ACTIVITIES = _counter(
    "oncoagent_temporal_activities_total", "Temporal Activity outcomes", ("activity", "status")
)
TEMPORAL_RETRIES = _counter(
    "oncoagent_temporal_activity_retries_total", "Temporal Activity retries", ("activity",)
)
TEMPORAL_REVIEW_WAITS = _gauge(
    "oncoagent_temporal_workflows_waiting_for_review", "Temporal workflows waiting for review"
)
IDENTITY_AUTH = _counter(
    "oncoagent_identity_authentication_total", "Identity authentication outcomes", ("outcome",)
)
IDENTITY_AUTHZ = _counter(
    "oncoagent_identity_authorization_total", "Authorization outcomes", ("decision", "reason")
)
IDENTITY_DATASET = _counter(
    "oncoagent_identity_dataset_access_total", "Dataset access outcomes", ("decision",)
)
IDENTITY_REVIEW = _counter(
    "oncoagent_identity_review_authority_total", "Review authority outcomes", ("decision", "reason")
)
PERFORMANCE_QUEUE_DEPTH = _gauge(
    "oncoagent_performance_queue_depth", "Bounded performance queue depth", ("queue",)
)
PERFORMANCE_QUEUE_WAIT = _histogram(
    "oncoagent_performance_queue_wait_seconds", "Bounded queue wait", ("queue",)
)
PERFORMANCE_OVERLOAD_REJECTIONS = _counter(
    "oncoagent_performance_overload_rejections_total",
    "Bounded overload rejections",
    ("queue", "reason"),
)
PERFORMANCE_WORKFLOW_CONCURRENCY = _gauge(
    "oncoagent_performance_workflow_concurrency", "Active workflow executions", ("framework",)
)
PERFORMANCE_MCP_CONCURRENCY = _gauge(
    "oncoagent_performance_mcp_concurrency", "Active MCP calls", ("transport",)
)
PERFORMANCE_MODEL_CONCURRENCY = _gauge(
    "oncoagent_performance_model_concurrency", "Active model generations", ("provider",)
)
PERFORMANCE_RETRY_BUDGET = _gauge(
    "oncoagent_performance_retry_budget", "Remaining bounded retry budget", ("operation",)
)
PERFORMANCE_CANCELLATION_LATENCY = _histogram(
    "oncoagent_performance_cancellation_latency_seconds",
    "Cancellation observation latency",
    ("framework",),
)
PERFORMANCE_RECOVERY_TIME = _histogram(
    "oncoagent_performance_recovery_time_seconds",
    "Recovery duration",
    ("framework", "failure_category"),
)
PERFORMANCE_SLO_STATUS = _gauge(
    "oncoagent_performance_slo_status", "Development SLO status", ("slo", "status")
)
SECURITY_AUTH_FAILURES = _counter(
    "oncoagent_security_authentication_failures_total", "Authentication failures", ("reason",)
)
SECURITY_AUTHZ_DENIALS = _counter(
    "oncoagent_security_authorization_denials_total", "Authorization denials", ("reason",)
)
SECURITY_DATASET_DENIALS = _counter(
    "oncoagent_security_dataset_denials_total", "Dataset authorization denials"
)
SECURITY_SELF_APPROVAL_DENIALS = _counter(
    "oncoagent_security_self_approval_denials_total", "Self approval denials"
)
SECURITY_CSRF_DENIALS = _counter("oncoagent_security_csrf_denials_total", "CSRF denials")
SECURITY_SECRET_FINDINGS = _gauge(
    "oncoagent_security_secret_scan_findings", "Sanitized secret scan findings"
)
SECURITY_DEPENDENCY_FINDINGS = _gauge(
    "oncoagent_security_dependency_findings", "Dependency findings by severity", ("severity",)
)
SECURITY_PRIVACY_VIOLATIONS = _counter(
    "oncoagent_security_privacy_violations_total", "Privacy boundary violations", ("category",)
)
SECURITY_AUDIT_INTEGRITY_FAILURES = _gauge(
    "oncoagent_security_audit_integrity_failures", "Audit integrity failures"
)
SECURITY_ASSESSMENT_STATUS = _gauge(
    "oncoagent_security_assessment_status", "Security assessment status", ("status",)
)
SECURITY_PROMPT_INJECTION_PREVENTED = _counter(
    "oncoagent_security_prompt_injection_prevented_total", "Prompt injection attempts prevented"
)
SECURITY_TOOL_DENIALS = _counter(
    "oncoagent_security_tool_authorization_denials_total", "Tool authorization denials", ("reason",)
)


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
