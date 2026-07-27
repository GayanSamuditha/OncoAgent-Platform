import time
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.retrieval import (
    ClinicalDocument,
    ClinicalDocumentChunk,
    ClinicalEmbedding,
    IndexingRun,
)
from app.retrieval.embeddings import DenseRetrievalProvider


def search(session: Session, provider: DenseRetrievalProvider, dataset_id: str, query: str, top_k: int, document_types: list[str], patient_id: str | None, minimum_score: float | None) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    vector = provider.encode_queries([query])[0]
    distance = ClinicalEmbedding.embedding.cosine_distance(vector).label("distance")
    statement = select(ClinicalEmbedding, ClinicalDocument, ClinicalDocumentChunk, distance).join(ClinicalDocumentChunk, ClinicalDocumentChunk.id == ClinicalEmbedding.document_chunk_id).join(ClinicalDocument, ClinicalDocument.id == ClinicalDocumentChunk.document_id).where(ClinicalEmbedding.dataset_id == dataset_id, ClinicalEmbedding.provider_id == provider.metadata.provider_id, ClinicalEmbedding.document_model_revision == provider.metadata.document_model_revision, ClinicalDocument.document_type.in_(document_types)).order_by(distance).limit(top_k)
    if patient_id:
        statement = statement.where(ClinicalEmbedding.patient_id == patient_id)
    rows: list[dict[str, object]] = []
    for embedding, document, chunk, raw_distance in session.execute(statement):
        score = 1 - float(raw_distance)
        if minimum_score is not None and score < minimum_score:
            continue
        rows.append({"rank": len(rows) + 1, "document_id": document.id, "chunk_id": chunk.id, "patient_id": embedding.patient_id, "encounter_id": embedding.encounter_id, "document_type": document.document_type, "text_excerpt": chunk.chunk_text[:600], "similarity_score": score, "source_fhir_resource_ids": chunk.source_resource_ids, "model_name": embedding.document_model_name, "model_revision": embedding.document_model_revision, "pooling_method": embedding.pooling_method, "document_builder_version": embedding.document_builder_version, "chunking_version": embedding.chunking_version})
    return rows, (time.perf_counter() - started) * 1000


def last_indexing(session: Session, model_name: str) -> IndexingRun | None:
    return session.scalar(select(IndexingRun).where(IndexingRun.model_name == model_name, IndexingRun.status == "completed").order_by(IndexingRun.completed_at.desc()).limit(1))


def postgres_fts_search(session: Session, dataset_id: str, query: str, top_k: int, document_types: list[str], patient_id: str | None) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    document_text = func.to_tsvector("simple", ClinicalDocument.title + " " + ClinicalDocument.text)
    query_text = func.plainto_tsquery("simple", query)
    lexical_score = func.ts_rank(document_text, query_text).label("lexical_score")
    statement = select(ClinicalDocument, lexical_score).where(ClinicalDocument.dataset_id == dataset_id, ClinicalDocument.document_type.in_(document_types), lexical_score > 0).order_by(lexical_score.desc(), ClinicalDocument.id).limit(top_k)
    if patient_id:
        statement = statement.where(ClinicalDocument.patient_id == patient_id)
    rows = [{"rank": index, "document_id": doc.id, "chunk_id": None, "patient_id": doc.patient_id, "encounter_id": doc.encounter_id, "document_type": doc.document_type, "text_excerpt": doc.text[:600], "similarity_score": float(score), "source_fhir_resource_ids": doc.source_resource_ids, "model_name": "postgresql-fts", "model_revision": "database", "pooling_method": "lexical", "document_builder_version": doc.builder_version, "chunking_version": "none"} for index, (doc, score) in enumerate(session.execute(statement), 1)]
    return rows, (time.perf_counter() - started) * 1000


def reciprocal_rank_fusion(lexical: list[dict[str, object]], dense: list[dict[str, object]], constant: int = 60, limit: int = 20) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for rank, item in enumerate(lexical, 1):
        key = str(item["document_id"])
        merged.setdefault(key, dict(item)).update({"lexical_rank": rank, "lexical_score": item.get("similarity_score")})
    for rank, item in enumerate(dense, 1):
        key = str(item["document_id"])
        target = merged.setdefault(key, dict(item))
        target.update({"dense_rank": rank, "dense_similarity_score": item.get("similarity_score"), "chunk_id": item.get("chunk_id")})
        if "text_excerpt" not in target:
            target.update(item)
    for item in merged.values():
        lexical_rank = int(cast(Any, item.get("lexical_rank", 10_000)))
        dense_rank = int(cast(Any, item.get("dense_rank", 10_000)))
        item["fused_score"] = (1 / (constant + lexical_rank) if "lexical_rank" in item else 0) + (1 / (constant + dense_rank) if "dense_rank" in item else 0)
    ranked = sorted(merged.values(), key=lambda item: (-float(cast(Any, item["fused_score"])), str(item["document_id"])))[:limit]
    for index, item in enumerate(ranked, 1):
        item["fused_rank"] = index
        item["initial_candidate_rank"] = index
    return ranked


def hybrid_search(session: Session, provider: DenseRetrievalProvider, dataset_id: str, query: str, candidate_pool: int, document_types: list[str], patient_id: str | None, rrf_constant: int) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    lexical, _ = postgres_fts_search(session, dataset_id, query, candidate_pool, document_types, patient_id)
    dense, _ = search(session, provider, dataset_id, query, candidate_pool, document_types, patient_id, None)
    return reciprocal_rank_fusion(lexical, dense, rrf_constant, candidate_pool), (time.perf_counter() - started) * 1000
