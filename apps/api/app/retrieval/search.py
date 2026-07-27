import time

from sqlalchemy import select
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
    return rows, (time.perf_counter() - started) * 1000  # type: ignore[return-value]


def last_indexing(session: Session, model_name: str) -> IndexingRun | None:
    return session.scalar(select(IndexingRun).where(IndexingRun.model_name == model_name, IndexingRun.status == "completed").order_by(IndexingRun.completed_at.desc()).limit(1))


def postgres_fts_search(session: Session, dataset_id: str, query: str, top_k: int, document_types: list[str], patient_id: str | None) -> tuple[list[dict[str, object]], float]:
    started = time.perf_counter()
    statement = select(ClinicalDocument).where(ClinicalDocument.dataset_id == dataset_id, ClinicalDocument.document_type.in_(document_types)).order_by(ClinicalDocument.id).limit(10000)
    if patient_id:
        statement = statement.where(ClinicalDocument.patient_id == patient_id)
    terms = {term.lower() for term in query.split() if len(term) > 2}
    scored = []
    for document in session.scalars(statement):
        words = set((document.title + " " + document.text).lower().split())
        score = len(terms & words) / max(len(terms), 1)
        if score:
            scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    rows = [{"rank": index, "document_id": doc.id, "chunk_id": None, "patient_id": doc.patient_id, "encounter_id": doc.encounter_id, "document_type": doc.document_type, "text_excerpt": doc.text[:600], "similarity_score": score, "source_fhir_resource_ids": doc.source_resource_ids, "model_name": "postgresql-fts", "model_revision": "database", "pooling_method": "lexical", "document_builder_version": doc.builder_version, "chunking_version": "none"} for index, (score, doc) in enumerate(scored[:top_k], 1)]
    return rows, (time.perf_counter() - started) * 1000  # type: ignore[return-value]
