from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.retrieval import (
    ClinicalDocument,
    ClinicalDocumentChunk,
    ClinicalEmbedding,
    IndexingRun,
)
from app.retrieval.chunking import CHUNKING_VERSION, chunk_text
from app.retrieval.embeddings import POOLING_METHOD, EmbeddingProvider


def index_documents(session: Session, provider: EmbeddingProvider, dataset_id: str, max_length: int, overlap: int, batch_size: int, limit: int | None = None) -> IndexingRun:
    docs = list(session.scalars(select(ClinicalDocument).where(ClinicalDocument.dataset_id == dataset_id).order_by(ClinicalDocument.id).limit(limit or 100000)))
    run = IndexingRun(id=str(uuid4()), dataset_id=dataset_id, model_name=provider.info.model_name, model_revision=provider.info.model_revision, status="running", requested_document_count=len(docs), batch_size=batch_size, device_type=provider.info.device, configuration={"max_length": max_length, "overlap": overlap, "chunking_version": CHUNKING_VERSION})
    session.add(run)
    session.commit()
    try:
        for document in docs:
            chunks = list(session.scalars(select(ClinicalDocumentChunk).where(ClinicalDocumentChunk.document_id == document.id).order_by(ClinicalDocumentChunk.chunk_index)))
            if not chunks:
                from hashlib import sha256
                chunks = [ClinicalDocumentChunk(id=str(uuid4()), document_id=document.id, chunk_index=item.index, chunk_text=item.text, chunk_text_sha256=sha256(item.text.encode()).hexdigest(), token_start=item.token_start, token_end=item.token_end, token_count=item.token_count, source_resource_ids=document.source_resource_ids) for item in chunk_text(document.text, cast(Any, provider.tokenizer), max_length, overlap)]
                session.add_all(chunks)
                session.flush()
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start:start + batch_size]
                existing = {str(x.document_chunk_id) for x in session.scalars(select(ClinicalEmbedding).where(ClinicalEmbedding.document_chunk_id.in_([x.id for x in batch]), ClinicalEmbedding.model_revision == provider.info.model_revision, ClinicalEmbedding.pooling_method == POOLING_METHOD, ClinicalEmbedding.chunking_version == CHUNKING_VERSION))}
                pending = [x for x in batch if x.id not in existing]
                if pending:
                    vectors = provider.embed([x.chunk_text for x in pending])
                    for chunk, vector in zip(pending, vectors, strict=True):
                        session.add(ClinicalEmbedding(id=str(uuid4()), document_chunk_id=chunk.id, dataset_id=dataset_id, patient_id=document.patient_id, encounter_id=document.encounter_id, model_name=provider.info.model_name, model_revision=provider.info.model_revision, pooling_method=POOLING_METHOD, embedding_dimension=len(vector), chunking_version=CHUNKING_VERSION, document_builder_version=document.builder_version, device_type=provider.info.device, embedding=vector))
                    run.created_embedding_count += len(pending)
                run.skipped_embedding_count += len(existing)
            run.processed_document_count += 1
            session.commit()
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        session.commit()
    except Exception as exc:
        session.rollback()
        run.status, run.failure_message = "failed", str(exc)[:2000]
        run.completed_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        raise
    return run
