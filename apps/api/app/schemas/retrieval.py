from typing import Any

from pydantic import BaseModel, Field


class ClinicalSearchRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    document_types: list[str] = Field(default_factory=lambda: ["encounter"])
    patient_id: str | None = None
    minimum_score: float | None = Field(default=None, ge=-1, le=1)
    retrieval_profile: str = Field(default="medcpt", pattern="^(medcpt|bioclinicalbert|postgres_fts)$")


class ClinicalSearchResult(BaseModel):
    rank: int
    document_id: str
    chunk_id: str | None
    patient_id: str
    encounter_id: str | None
    document_type: str
    text_excerpt: str
    similarity_score: float
    source_fhir_resource_ids: list[str]
    model_name: str
    model_revision: str
    pooling_method: str
    document_builder_version: str
    chunking_version: str


class ClinicalSearchResponse(BaseModel):
    query: str
    dataset_id: str
    result_count: int
    model_name: str
    model_revision: str
    search_latency_ms: float
    synthetic_data_notice: str
    score_notice: str
    retrieval_profile: str
    query_model_name: str
    query_model_revision: str
    document_model_name: str
    document_model_revision: str
    representation_strategy: str
    normalization_strategy: str
    items: list[ClinicalSearchResult]


class ModelStatusResponse(BaseModel):
    providers: dict[str, Any]
    configured_model: str = ""
    loaded_status: str = "not_loaded"
    device: str = "cpu"
    embedding_dimension: int | None = None
    maximum_sequence_length: int = 512
    pooling_method: str = ""
    revision: str = ""
    last_successful_indexing_time: Any | None
    current_limitations: list[str]
