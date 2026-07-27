from typing import Any

from pydantic import BaseModel, Field


class ClinicalSearchRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    document_types: list[str] = Field(default_factory=lambda: ["encounter"])
    patient_id: str | None = None
    minimum_score: float | None = Field(default=None, ge=-1, le=1)


class ClinicalSearchResult(BaseModel):
    rank: int
    document_id: str
    chunk_id: str
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
    items: list[ClinicalSearchResult]


class ModelStatusResponse(BaseModel):
    configured_model: str
    loaded_status: str
    device: str
    embedding_dimension: int | None
    maximum_sequence_length: int
    pooling_method: str
    revision: str
    last_successful_indexing_time: Any | None
    current_limitations: list[str]
