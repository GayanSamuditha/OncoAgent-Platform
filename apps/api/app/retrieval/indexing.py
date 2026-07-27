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
from app.retrieval.embeddings import DenseRetrievalProvider


def index_documents(
    session: Session,
    provider: DenseRetrievalProvider,
    dataset_id: str,
    max_length: int,
    overlap: int,
    batch_size: int,
    limit: int | None = None,
) -> IndexingRun:
    docs = list(
        session.scalars(
            select(ClinicalDocument)
            .where(ClinicalDocument.dataset_id == dataset_id)
            .order_by(ClinicalDocument.id)
            .limit(limit or 100000)
        )
    )
    metadata = provider.metadata
    run = IndexingRun(
        id=str(uuid4()),
        dataset_id=dataset_id,
        model_name=metadata.document_model_name,
        model_revision=metadata.document_model_revision,
        provider_id=metadata.provider_id,
        document_model_name=metadata.document_model_name,
        document_model_revision=metadata.document_model_revision,
        status="running",
        requested_document_count=len(docs),
        batch_size=batch_size,
        device_type=metadata.device,
        configuration={
            "max_length": max_length,
            "overlap": overlap,
            "chunking_version": CHUNKING_VERSION,
        },
    )
    session.add(run)
    session.commit()
    try:
        for document in docs:
            chunks = list(
                session.scalars(
                    select(ClinicalDocumentChunk)
                    .where(ClinicalDocumentChunk.document_id == document.id)
                    .order_by(ClinicalDocumentChunk.chunk_index)
                )
            )
            if not chunks:
                from hashlib import sha256

                chunks = [
                    ClinicalDocumentChunk(
                        id=str(uuid4()),
                        document_id=document.id,
                        chunk_index=item.index,
                        chunk_text=item.text,
                        chunk_text_sha256=sha256(item.text.encode()).hexdigest(),
                        token_start=item.token_start,
                        token_end=item.token_end,
                        token_count=item.token_count,
                        source_resource_ids=document.source_resource_ids,
                    )
                    for item in chunk_text(
                        document.text, cast(Any, provider.tokenizer), max_length, overlap
                    )
                ]
                session.add_all(chunks)
                session.flush()
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                existing = {
                    str(x.document_chunk_id)
                    for x in session.scalars(
                        select(ClinicalEmbedding).where(
                            ClinicalEmbedding.document_chunk_id.in_([x.id for x in batch]),
                            ClinicalEmbedding.provider_id == metadata.provider_id,
                            ClinicalEmbedding.document_model_revision
                            == metadata.document_model_revision,
                            ClinicalEmbedding.pooling_method == metadata.pooling_strategy,
                            ClinicalEmbedding.chunking_version == CHUNKING_VERSION,
                        )
                    )
                }
                pending = [x for x in batch if x.id not in existing]
                if pending:
                    vectors = provider.encode_documents(
                        [(document.title, x.chunk_text) for x in pending]
                    )
                    for chunk, vector in zip(pending, vectors, strict=True):
                        session.add(
                            ClinicalEmbedding(
                                id=str(uuid4()),
                                document_chunk_id=chunk.id,
                                dataset_id=dataset_id,
                                patient_id=document.patient_id,
                                encounter_id=document.encounter_id,
                                model_name=metadata.document_model_name,
                                model_revision=metadata.document_model_revision,
                                provider_id=metadata.provider_id,
                                query_model_name=metadata.query_model_name,
                                document_model_name=metadata.document_model_name,
                                query_model_revision=metadata.query_model_revision,
                                document_model_revision=metadata.document_model_revision,
                                pooling_method=metadata.pooling_strategy,
                                embedding_dimension=len(vector),
                                normalization_strategy=metadata.normalization_strategy,
                                query_max_length=metadata.query_max_length,
                                document_max_length=metadata.document_max_length,
                                representation_version="clinical-document-v2",
                                chunking_version=CHUNKING_VERSION,
                                document_builder_version=document.builder_version,
                                device_type=metadata.device,
                                embedding=vector,
                            )
                        )
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
