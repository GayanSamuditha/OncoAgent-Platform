from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"
    __table_args__ = (UniqueConstraint("dataset_id", "patient_id", "encounter_id", "document_type", "document_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    document_type: Mapped[str] = mapped_column(String(40))
    document_version: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64), index=True)
    token_count: Mapped[int] = mapped_column(Integer)
    source_resource_ids: Mapped[list[Any]] = mapped_column(JSONB)
    source_resource_count: Mapped[int] = mapped_column(Integer)
    builder_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ClinicalDocumentChunk(Base):
    __tablename__ = "clinical_document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("clinical_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_text: Mapped[str] = mapped_column(Text)
    chunk_text_sha256: Mapped[str] = mapped_column(String(64))
    token_start: Mapped[int] = mapped_column(Integer)
    token_end: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    source_resource_ids: Mapped[list[Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicalEmbedding(Base):
    __tablename__ = "clinical_embeddings"
    __table_args__ = (UniqueConstraint("document_chunk_id", "model_revision", "pooling_method", "chunking_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_chunk_id: Mapped[str] = mapped_column(ForeignKey("clinical_document_chunks.id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[str | None] = mapped_column(ForeignKey("encounters.id"), nullable=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_revision: Mapped[str] = mapped_column(String(200))
    model_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pooling_method: Mapped[str] = mapped_column(String(60))
    embedding_dimension: Mapped[int] = mapped_column(Integer)
    chunking_version: Mapped[str] = mapped_column(String(40))
    document_builder_version: Mapped[str] = mapped_column(String(40))
    device_type: Mapped[str] = mapped_column(String(20))
    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IndexingRun(Base):
    __tablename__ = "indexing_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_revision: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30))
    requested_document_count: Mapped[int] = mapped_column(Integer)
    processed_document_count: Mapped[int] = mapped_column(Integer, default=0)
    created_embedding_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_embedding_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_embedding_count: Mapped[int] = mapped_column(Integer, default=0)
    batch_size: Mapped[int] = mapped_column(Integer)
    device_type: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
