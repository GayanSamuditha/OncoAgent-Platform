from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="OncoAgent Platform API", validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    environment: str = Field(default="local", validation_alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://oncoagent:oncoagent_dev@localhost:5432/oncoagent",
        validation_alias="DATABASE_URL",
    )
    cors_origins: list[str] = ["http://localhost:3000"]
    clinical_embedding_model: str = Field(
        default="emilyalsentzer/Bio_ClinicalBERT", validation_alias="CLINICAL_EMBEDDING_MODEL"
    )
    clinical_embedding_model_revision: str = Field(
        default="main", validation_alias="CLINICAL_EMBEDDING_MODEL_REVISION"
    )
    embedding_device: str = Field(default="auto", validation_alias="EMBEDDING_DEVICE")
    embedding_max_sequence_length: int = Field(
        default=256, validation_alias="EMBEDDING_MAX_SEQUENCE_LENGTH"
    )
    embedding_token_overlap: int = Field(default=32, validation_alias="EMBEDDING_TOKEN_OVERLAP")
    embedding_batch_size_mps: int = Field(default=8, validation_alias="EMBEDDING_BATCH_SIZE_MPS")
    embedding_batch_size_cpu: int = Field(default=4, validation_alias="EMBEDDING_BATCH_SIZE_CPU")
    retrieval_profile: str = Field(default="medcpt", validation_alias="RETRIEVAL_PROFILE")
    medcpt_query_model: str = Field(
        default="ncbi/MedCPT-Query-Encoder", validation_alias="MEDCPT_QUERY_MODEL"
    )
    medcpt_document_model: str = Field(
        default="ncbi/MedCPT-Article-Encoder", validation_alias="MEDCPT_DOCUMENT_MODEL"
    )
    medcpt_query_revision: str = Field(default="main", validation_alias="MEDCPT_QUERY_REVISION")
    medcpt_document_revision: str = Field(
        default="main", validation_alias="MEDCPT_DOCUMENT_REVISION"
    )
    retrieval_query_max_length: int = Field(
        default=64, validation_alias="RETRIEVAL_QUERY_MAX_LENGTH"
    )
    retrieval_document_max_length: int = Field(
        default=512, validation_alias="RETRIEVAL_DOCUMENT_MAX_LENGTH"
    )
    reranker_model: str = Field(
        default="ncbi/MedCPT-Cross-Encoder", validation_alias="RERANKER_MODEL"
    )
    reranker_model_revision: str = Field(default="main", validation_alias="RERANKER_MODEL_REVISION")
    reranker_batch_size: int = Field(default=4, validation_alias="RERANKER_BATCH_SIZE")
    rrf_constant: int = Field(default=60, validation_alias="RRF_CONSTANT")
    agent_execution_enabled: bool = Field(default=True, validation_alias="AGENT_EXECUTION_ENABLED")
    workflow_max_candidates: int = Field(default=50, validation_alias="WORKFLOW_MAX_CANDIDATES")
    workflow_tool_timeout_seconds: int = Field(
        default=10, validation_alias="WORKFLOW_TOOL_TIMEOUT_SECONDS"
    )
    local_llm_enabled: bool = Field(default=True, validation_alias="LOCAL_LLM_ENABLED")
    local_llm_provider: str = Field(default="ollama", validation_alias="LOCAL_LLM_PROVIDER")
    local_llm_base_url: str = Field(
        default="http://127.0.0.1:11434", validation_alias="LOCAL_LLM_BASE_URL"
    )
    local_llm_model: str = Field(default="qwen3:8b", validation_alias="LOCAL_LLM_MODEL")
    local_llm_timeout_seconds: int = Field(
        default=60, ge=1, le=300, validation_alias="LOCAL_LLM_TIMEOUT_SECONDS"
    )
    local_llm_max_retries: int = Field(
        default=1, ge=0, le=2, validation_alias="LOCAL_LLM_MAX_RETRIES"
    )
    local_llm_temperature: float = Field(
        default=0.0, ge=0, le=1, validation_alias="LOCAL_LLM_TEMPERATURE"
    )
    local_llm_context_length: int = Field(
        default=8192, ge=256, le=32768, validation_alias="LOCAL_LLM_CONTEXT_LENGTH"
    )
    local_llm_max_output_tokens: int = Field(
        default=1024, ge=64, le=4096, validation_alias="LOCAL_LLM_MAX_OUTPUT_TOKENS"
    )
    local_llm_keep_alive: str = Field(default="5m", validation_alias="LOCAL_LLM_KEEP_ALIVE")
    local_llm_thinking: bool = Field(default=False, validation_alias="LOCAL_LLM_THINKING")
    local_llm_require_structured_output: bool = Field(
        default=True, validation_alias="LOCAL_LLM_REQUIRE_STRUCTURED_OUTPUT"
    )
    local_llm_max_response_bytes: int = Field(
        default=1048576, ge=1024, le=10485760, validation_alias="LOCAL_LLM_MAX_RESPONSE_BYTES"
    )
    planner_default_provider: str = Field(
        default="qwen_local", validation_alias="PLANNER_DEFAULT_PROVIDER"
    )
    planner_fallback_provider: str = Field(
        default="deterministic", validation_alias="PLANNER_FALLBACK_PROVIDER"
    )
    mcp_enabled: bool = Field(default=True, validation_alias="MCP_ENABLED")
    mcp_streamable_http_enabled: bool = Field(
        default=True, validation_alias="MCP_STREAMABLE_HTTP_ENABLED"
    )
    mcp_stdio_enabled: bool = Field(default=True, validation_alias="MCP_STDIO_ENABLED")
    mcp_host: str = Field(default="127.0.0.1", validation_alias="MCP_HOST")
    mcp_port: int = Field(default=8010, ge=1, le=65535, validation_alias="MCP_PORT")
    mcp_max_results: int = Field(default=50, ge=1, le=100, validation_alias="MCP_MAX_RESULTS")
    mcp_max_response_bytes: int = Field(
        default=1048576, ge=1024, le=10485760, validation_alias="MCP_MAX_RESPONSE_BYTES"
    )
    mcp_request_timeout_seconds: int = Field(
        default=30, ge=1, le=300, validation_alias="MCP_REQUEST_TIMEOUT_SECONDS"
    )
    mcp_dev_clients: str = Field(default="", validation_alias="MCP_DEV_CLIENTS")
    local_planner_models: str = Field(
        default="qwen3:8b,qwen2.5:7b,llama3.2:3b,gemma3:4b",
        validation_alias="LOCAL_PLANNER_MODELS",
    )
    local_planner_default_model: str = Field(
        default="qwen3:8b", validation_alias="LOCAL_PLANNER_DEFAULT_MODEL"
    )
    local_planner_benchmark_keep_alive: str = Field(
        default="0", validation_alias="LOCAL_PLANNER_BENCHMARK_KEEP_ALIVE"
    )
    local_planner_context_length: int = Field(
        default=8192, ge=256, le=32768, validation_alias="LOCAL_PLANNER_CONTEXT_LENGTH"
    )
    local_planner_max_output_tokens: int = Field(
        default=1024, ge=64, le=4096, validation_alias="LOCAL_PLANNER_MAX_OUTPUT_TOKENS"
    )
    crewai_enabled: bool = Field(default=True, validation_alias="CREWAI_ENABLED")
    crewai_default_model: str = Field(
        default="llama3.2:3b", validation_alias="CREWAI_DEFAULT_MODEL"
    )
    crewai_secondary_model: str = Field(
        default="qwen3:8b", validation_alias="CREWAI_SECONDARY_MODEL"
    )
    crewai_ollama_base_url: str = Field(
        default="http://127.0.0.1:11434", validation_alias="CREWAI_OLLAMA_BASE_URL"
    )
    crewai_temperature: float = Field(
        default=0.0, ge=0, le=1, validation_alias="CREWAI_TEMPERATURE"
    )
    crewai_max_iterations_per_agent: int = Field(
        default=5, ge=1, le=10, validation_alias="CREWAI_MAX_ITERATIONS_PER_AGENT"
    )
    crewai_max_tool_calls_per_run: int = Field(
        default=30, ge=1, le=100, validation_alias="CREWAI_MAX_TOOL_CALLS_PER_RUN"
    )
    crewai_run_timeout_seconds: int = Field(
        default=180, ge=10, le=600, validation_alias="CREWAI_RUN_TIMEOUT_SECONDS"
    )
    crewai_memory_enabled: bool = Field(default=False, validation_alias="CREWAI_MEMORY_ENABLED")
    crewai_delegation_enabled: bool = Field(
        default=False, validation_alias="CREWAI_DELEGATION_ENABLED"
    )
    crewai_verbose: bool = Field(default=False, validation_alias="CREWAI_VERBOSE")
    crewai_mcp_url: str = Field(
        default="http://127.0.0.1:8010/mcp", validation_alias="CREWAI_MCP_URL"
    )
    crewai_mcp_client_id: str = Field(default="", validation_alias="CREWAI_MCP_CLIENT_ID")
    crewai_mcp_token: str = Field(default="", validation_alias="CREWAI_MCP_TOKEN")
    crewai_mcp_dataset_ids: str = Field(default="", validation_alias="CREWAI_MCP_DATASET_IDS")
    crewai_concurrency: int = Field(default=1, ge=1, le=1, validation_alias="CREWAI_CONCURRENCY")
    crewai_execution_mode: Literal["temporal", "legacy"] = Field(
        default="temporal", validation_alias="CREWAI_EXECUTION_MODE"
    )
    temporal_enabled: bool = Field(default=True, validation_alias="TEMPORAL_ENABLED")
    temporal_address: str = Field(default="127.0.0.1:7233", validation_alias="TEMPORAL_ADDRESS")
    temporal_namespace: str = Field(default="oncoagent", validation_alias="TEMPORAL_NAMESPACE")
    temporal_task_queue: str = Field(
        default="oncoagent-crewai", validation_alias="TEMPORAL_TASK_QUEUE"
    )
    temporal_ui_url: str = Field(
        default="http://127.0.0.1:8233", validation_alias="TEMPORAL_UI_URL"
    )
    temporal_workflow_execution_timeout_seconds: int = Field(
        default=1800,
        ge=60,
        le=86400,
        validation_alias="TEMPORAL_WORKFLOW_EXECUTION_TIMEOUT_SECONDS",
    )
    temporal_activity_start_to_close_seconds: int = Field(
        default=300, ge=10, le=3600, validation_alias="TEMPORAL_ACTIVITY_START_TO_CLOSE_SECONDS"
    )
    temporal_activity_schedule_to_close_seconds: int = Field(
        default=900, ge=30, le=7200, validation_alias="TEMPORAL_ACTIVITY_SCHEDULE_TO_CLOSE_SECONDS"
    )
    temporal_activity_heartbeat_seconds: int = Field(
        default=30, ge=5, le=300, validation_alias="TEMPORAL_ACTIVITY_HEARTBEAT_SECONDS"
    )
    temporal_max_activity_attempts: int = Field(
        default=2, ge=1, le=5, validation_alias="TEMPORAL_MAX_ACTIVITY_ATTEMPTS"
    )
    temporal_dev_fault_stage: str = Field(default="", validation_alias="TEMPORAL_DEV_FAULT_STAGE")
    temporal_dev_fault_category: str = Field(
        default="", validation_alias="TEMPORAL_DEV_FAULT_CATEGORY"
    )
    temporal_dev_fault_attempts: int = Field(
        default=1, ge=1, le=2, validation_alias="TEMPORAL_DEV_FAULT_ATTEMPTS"
    )
    temporal_dev_activity_delay_seconds: float = Field(
        default=0, ge=0, le=120, validation_alias="TEMPORAL_DEV_ACTIVITY_DELAY_SECONDS"
    )
    observability_enabled: bool = Field(default=True, validation_alias="OBSERVABILITY_ENABLED")
    otel_service_name: str = Field(default="oncoagent-api", validation_alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://127.0.0.1:4317", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_protocol: str = Field(
        default="grpc", validation_alias="OTEL_EXPORTER_OTLP_PROTOCOL"
    )
    otel_traces_exporter: str = Field(default="otlp", validation_alias="OTEL_TRACES_EXPORTER")
    otel_metrics_exporter: str = Field(default="otlp", validation_alias="OTEL_METRICS_EXPORTER")
    otel_log_level: str = Field(default="INFO", validation_alias="OTEL_LOG_LEVEL")
    otel_trace_sample_ratio: float = Field(
        default=1.0, ge=0, le=1, validation_alias="OTEL_TRACE_SAMPLE_RATIO"
    )
    prometheus_metrics_enabled: bool = Field(
        default=True, validation_alias="PROMETHEUS_METRICS_ENABLED"
    )
    prometheus_metrics_path: str = Field(
        default="/metrics", validation_alias="PROMETHEUS_METRICS_PATH"
    )
    structured_logging_enabled: bool = Field(
        default=True, validation_alias="STRUCTURED_LOGGING_ENABLED"
    )
    identity_enabled: bool = Field(default=True, validation_alias="IDENTITY_ENABLED")
    identity_issuer: str = Field(
        default="http://127.0.0.1:8000/local-oidc", validation_alias="IDENTITY_ISSUER"
    )
    identity_audience: str = Field(
        default="oncoagent-platform", validation_alias="IDENTITY_AUDIENCE"
    )
    identity_signing_secret: str = Field(
        default="local-development-only-change-me", validation_alias="IDENTITY_SIGNING_SECRET"
    )
    identity_session_cookie: str = Field(
        default="oncoagent_session", validation_alias="IDENTITY_SESSION_COOKIE"
    )
    identity_session_ttl_seconds: int = Field(
        default=3600, ge=60, le=86400, validation_alias="IDENTITY_SESSION_TTL_SECONDS"
    )
    identity_cookie_secure: bool = Field(default=False, validation_alias="IDENTITY_COOKIE_SECURE")
    identity_dev_users: str = Field(default="", validation_alias="IDENTITY_DEV_USERS")
    identity_allowed_roles: list[str] = [
        "researcher",
        "reviewer",
        "governance_officer",
        "platform_operator",
        "auditor",
        "administrator",
    ]
    identity_legacy_headers_enabled: bool = Field(
        default=True, validation_alias="IDENTITY_LEGACY_HEADERS_ENABLED"
    )
    performance_enabled: bool = Field(default=True, validation_alias="PERFORMANCE_ENABLED")
    performance_max_concurrency: int = Field(
        default=8, ge=1, le=32, validation_alias="PERFORMANCE_MAX_CONCURRENCY"
    )
    performance_queue_timeout_seconds: float = Field(
        default=5, ge=0.1, le=60, validation_alias="PERFORMANCE_QUEUE_TIMEOUT_SECONDS"
    )
    performance_run_timeout_seconds: int = Field(
        default=600, ge=10, le=3600, validation_alias="PERFORMANCE_RUN_TIMEOUT_SECONDS"
    )
    api_workflow_concurrency: int = Field(
        default=1, ge=1, le=8, validation_alias="API_WORKFLOW_CONCURRENCY"
    )
    langgraph_concurrency: int = Field(
        default=1, ge=1, le=8, validation_alias="LANGGRAPH_CONCURRENCY"
    )
    mcp_concurrency: int = Field(default=8, ge=1, le=32, validation_alias="MCP_CONCURRENCY")
    ollama_concurrency: int = Field(default=1, ge=1, le=2, validation_alias="OLLAMA_CONCURRENCY")
    database_pool_size: int = Field(default=5, ge=1, le=20, validation_alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(
        default=5, ge=0, le=20, validation_alias="DATABASE_MAX_OVERFLOW"
    )
    retry_budget_per_operation: int = Field(
        default=2, ge=0, le=5, validation_alias="RETRY_BUDGET_PER_OPERATION"
    )
    performance_blocking_latency_slos: bool = Field(
        default=False, validation_alias="PERFORMANCE_BLOCKING_LATENCY_SLOS"
    )

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env", extra="ignore", populate_by_name=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
