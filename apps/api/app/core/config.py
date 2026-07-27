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

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[4] / ".env", extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
