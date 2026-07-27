from functools import lru_cache
from pathlib import Path

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
    clinical_embedding_model: str = Field(default="emilyalsentzer/Bio_ClinicalBERT", validation_alias="CLINICAL_EMBEDDING_MODEL")
    clinical_embedding_model_revision: str = Field(default="main", validation_alias="CLINICAL_EMBEDDING_MODEL_REVISION")
    embedding_device: str = Field(default="auto", validation_alias="EMBEDDING_DEVICE")
    embedding_max_sequence_length: int = Field(default=256, validation_alias="EMBEDDING_MAX_SEQUENCE_LENGTH")
    embedding_token_overlap: int = Field(default=32, validation_alias="EMBEDDING_TOKEN_OVERLAP")
    embedding_batch_size_mps: int = Field(default=8, validation_alias="EMBEDDING_BATCH_SIZE_MPS")
    embedding_batch_size_cpu: int = Field(default=4, validation_alias="EMBEDDING_BATCH_SIZE_CPU")
    retrieval_profile: str = Field(default="medcpt", validation_alias="RETRIEVAL_PROFILE")
    medcpt_query_model: str = Field(default="ncbi/MedCPT-Query-Encoder", validation_alias="MEDCPT_QUERY_MODEL")
    medcpt_document_model: str = Field(default="ncbi/MedCPT-Article-Encoder", validation_alias="MEDCPT_DOCUMENT_MODEL")
    medcpt_query_revision: str = Field(default="main", validation_alias="MEDCPT_QUERY_REVISION")
    medcpt_document_revision: str = Field(default="main", validation_alias="MEDCPT_DOCUMENT_REVISION")
    retrieval_query_max_length: int = Field(default=64, validation_alias="RETRIEVAL_QUERY_MAX_LENGTH")
    retrieval_document_max_length: int = Field(default=512, validation_alias="RETRIEVAL_DOCUMENT_MAX_LENGTH")
    reranker_model: str = Field(default="ncbi/MedCPT-Cross-Encoder", validation_alias="RERANKER_MODEL")
    reranker_model_revision: str = Field(default="main", validation_alias="RERANKER_MODEL_REVISION")
    reranker_batch_size: int = Field(default=4, validation_alias="RERANKER_BATCH_SIZE")
    rrf_constant: int = Field(default=60, validation_alias="RRF_CONSTANT")
    agent_execution_enabled: bool = Field(default=True, validation_alias="AGENT_EXECUTION_ENABLED")
    workflow_max_candidates: int = Field(default=50, validation_alias="WORKFLOW_MAX_CANDIDATES")
    workflow_tool_timeout_seconds: int = Field(default=10, validation_alias="WORKFLOW_TOOL_TIMEOUT_SECONDS")
    local_llm_enabled: bool = Field(default=True, validation_alias="LOCAL_LLM_ENABLED")
    local_llm_provider: str = Field(default="ollama", validation_alias="LOCAL_LLM_PROVIDER")
    local_llm_base_url: str = Field(default="http://127.0.0.1:11434", validation_alias="LOCAL_LLM_BASE_URL")
    local_llm_model: str = Field(default="qwen3:8b", validation_alias="LOCAL_LLM_MODEL")
    local_llm_timeout_seconds: int = Field(default=60, ge=1, le=300, validation_alias="LOCAL_LLM_TIMEOUT_SECONDS")
    local_llm_max_retries: int = Field(default=1, ge=0, le=2, validation_alias="LOCAL_LLM_MAX_RETRIES")
    local_llm_temperature: float = Field(default=0.0, ge=0, le=1, validation_alias="LOCAL_LLM_TEMPERATURE")
    local_llm_context_length: int = Field(default=8192, ge=256, le=32768, validation_alias="LOCAL_LLM_CONTEXT_LENGTH")
    local_llm_max_output_tokens: int = Field(default=1024, ge=64, le=4096, validation_alias="LOCAL_LLM_MAX_OUTPUT_TOKENS")
    local_llm_keep_alive: str = Field(default="5m", validation_alias="LOCAL_LLM_KEEP_ALIVE")
    local_llm_thinking: bool = Field(default=False, validation_alias="LOCAL_LLM_THINKING")
    local_llm_require_structured_output: bool = Field(default=True, validation_alias="LOCAL_LLM_REQUIRE_STRUCTURED_OUTPUT")
    local_llm_max_response_bytes: int = Field(default=1048576, ge=1024, le=10485760, validation_alias="LOCAL_LLM_MAX_RESPONSE_BYTES")
    planner_default_provider: str = Field(default="qwen_local", validation_alias="PLANNER_DEFAULT_PROVIDER")
    planner_fallback_provider: str = Field(default="deterministic", validation_alias="PLANNER_FALLBACK_PROVIDER")
    mcp_enabled: bool = Field(default=True, validation_alias="MCP_ENABLED")
    mcp_streamable_http_enabled: bool = Field(default=True, validation_alias="MCP_STREAMABLE_HTTP_ENABLED")
    mcp_stdio_enabled: bool = Field(default=True, validation_alias="MCP_STDIO_ENABLED")
    mcp_host: str = Field(default="127.0.0.1", validation_alias="MCP_HOST")
    mcp_port: int = Field(default=8010, ge=1, le=65535, validation_alias="MCP_PORT")
    mcp_max_results: int = Field(default=50, ge=1, le=100, validation_alias="MCP_MAX_RESULTS")
    mcp_max_response_bytes: int = Field(default=1048576, ge=1024, le=10485760, validation_alias="MCP_MAX_RESPONSE_BYTES")
    mcp_request_timeout_seconds: int = Field(default=30, ge=1, le=300, validation_alias="MCP_REQUEST_TIMEOUT_SECONDS")
    mcp_dev_clients: str = Field(default="", validation_alias="MCP_DEV_CLIENTS")
    local_planner_models: str = Field(
        default="qwen3:8b,qwen2.5:7b,llama3.2:3b,gemma3:4b",
        validation_alias="LOCAL_PLANNER_MODELS",
    )
    local_planner_default_model: str = Field(default="qwen3:8b", validation_alias="LOCAL_PLANNER_DEFAULT_MODEL")
    local_planner_benchmark_keep_alive: str = Field(default="0", validation_alias="LOCAL_PLANNER_BENCHMARK_KEEP_ALIVE")
    local_planner_context_length: int = Field(default=8192, ge=256, le=32768, validation_alias="LOCAL_PLANNER_CONTEXT_LENGTH")
    local_planner_max_output_tokens: int = Field(default=1024, ge=64, le=4096, validation_alias="LOCAL_PLANNER_MAX_OUTPUT_TOKENS")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env", extra="ignore", populate_by_name=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
