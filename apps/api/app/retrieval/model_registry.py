from functools import lru_cache

from app.core.config import Settings
from app.retrieval.embeddings import (
    BioClinicalBERTProvider,
    DenseRetrievalProvider,
    MedCPTDualEncoderProvider,
)
from app.retrieval.reranking import MedCPTRerankerProvider


def provider_for(settings: Settings, profile: str | None = None) -> DenseRetrievalProvider:
    selected = profile or settings.retrieval_profile
    if selected == "medcpt":
        return get_medcpt(settings.medcpt_query_model, settings.medcpt_document_model, settings.medcpt_query_revision, settings.medcpt_document_revision, settings.embedding_device, settings.retrieval_query_max_length, settings.retrieval_document_max_length)
    if selected == "bioclinicalbert":
        return get_biobert(settings.clinical_embedding_model, settings.clinical_embedding_model_revision, settings.embedding_device, settings.embedding_max_sequence_length)
    raise ValueError(f"unsupported dense retrieval profile: {selected}")


@lru_cache
def get_medcpt(query: str, document: str, query_revision: str, document_revision: str, device: str, query_length: int, document_length: int) -> MedCPTDualEncoderProvider:
    return MedCPTDualEncoderProvider(query, document, query_revision, document_revision, device, query_length, document_length)


@lru_cache
def get_biobert(model: str, revision: str, device: str, max_length: int) -> BioClinicalBERTProvider:
    return BioClinicalBERTProvider(model, revision, device, max_length)


@lru_cache
def get_reranker(model: str, revision: str, device: str, batch_size: int) -> MedCPTRerankerProvider:
    return MedCPTRerankerProvider(model, revision, device, batch_size)
