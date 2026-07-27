from typing import Any

from pydantic import BaseModel, Field


class ClinicalSearchRequest(BaseModel):
    dataset_id: str
    query: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    document_types: list[str] = Field(default_factory=lambda: ["encounter"])
    patient_id: str | None = None
    minimum_score: float | None = Field(default=None, ge=-1, le=1)
    retrieval_profile: str = Field(
        default="bioclinicalbert",
        pattern="^(medcpt|bioclinicalbert|postgres_fts|hybrid_bioclinicalbert|hybrid_medcpt)$",
    )
    reranker: str = Field(default="none", pattern="^(none|medcpt_cross_encoder)$")
    candidate_pool_size: int = Field(default=20, ge=1, le=50)


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
    lexical_rank: int | None = None
    lexical_score: float | None = None
    dense_rank: int | None = None
    dense_similarity_score: float | None = None
    fused_rank: int | None = None
    fused_score: float | None = None
    initial_candidate_rank: int | None = None
    reranked_rank: int | None = None
    reranker_logit: float | None = None
    final_rank: int | None = None


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
    lexical_provider: str | None = None
    dense_provider: str | None = None
    fusion_method: str | None = None
    rrf_constant: int | None = None
    reranker: str = "none"
    candidate_pool_size: int = 0
    first_stage_latency_ms: float = 0.0
    reranking_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    reranker_model_name: str | None = None
    reranker_model_revision: str | None = None
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
