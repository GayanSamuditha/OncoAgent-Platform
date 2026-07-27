import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retrieval import (
    ClinicalDocument,
    ClinicalDocumentChunk,
    ClinicalEmbedding,
    IndexingRun,
)
from app.retrieval.embeddings import EmbeddingProvider


def search(session: Session, provider: EmbeddingProvider, dataset_id: str, query: str, top_k: int, document_types: list[str], patient_id: str | None, minimum_score: float | None) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    vector = provider.embed([query])[0]
    distance = ClinicalEmbedding.embedding.cosine_distance(vector).label("distance")
    statement = select(ClinicalEmbedding, ClinicalDocument, ClinicalDocumentChunk, distance).join(ClinicalDocumentChunk, ClinicalDocumentChunk.id == ClinicalEmbedding.document_chunk_id).join(ClinicalDocument, ClinicalDocument.id == ClinicalDocumentChunk.document_id).where(ClinicalEmbedding.dataset_id == dataset_id, ClinicalDocument.document_type.in_(document_types)).order_by(distance).limit(top_k)
    if patient_id:
        statement = statement.where(ClinicalEmbedding.patient_id == patient_id)
    rows: list[dict[str, object]] = []
    for embedding, document, chunk, raw_distance in session.execute(statement):
        score = 1 - float(raw_distance)
        if minimum_score is not None and score < minimum_score:
            continue
        rows.append({"rank": len(rows) + 1, "document_id": document.id, "chunk_id": chunk.id, "patient_id": embedding.patient_id, "encounter_id": embedding.encounter_id, "document_type": document.document_type, "text_excerpt": chunk.chunk_text[:600], "similarity_score": score, "source_fhir_resource_ids": chunk.source_resource_ids, "model_name": embedding.model_name, "model_revision": embedding.model_revision, "pooling_method": embedding.pooling_method, "document_builder_version": embedding.document_builder_version, "chunking_version": embedding.chunking_version})
    return rows, (time.perf_counter() - started) * 1000


def last_indexing(session: Session, model_name: str) -> IndexingRun | None:
    return session.scalar(select(IndexingRun).where(IndexingRun.model_name == model_name, IndexingRun.status == "completed").order_by(IndexingRun.completed_at.desc()).limit(1))
