from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_department: Mapped[str] = mapped_column(String(128), nullable=False)
    version_no: Mapped[str] = mapped_column(String(64), nullable=False)
    document_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    clauses: Mapped[list] = relationship("Clause", back_populates="document")


class Clause(Base):
    __tablename__ = "clauses"
    __table_args__ = (
        UniqueConstraint("document_id", "clause_no", name="uq_clause_document_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    clause_no: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    clause_type: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    importance: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deprecated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="clauses")
    reviews: Mapped[list] = relationship("Review", back_populates="clause")
    tag_bindings: Mapped[list] = relationship("ClauseTagBinding", back_populates="clause")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clause_id: Mapped[int] = mapped_column(ForeignKey("clauses.id"), nullable=False, index=True)
    reviewer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    process_status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    clause: Mapped[Clause] = relationship("Clause", back_populates="reviews")
    process_records: Mapped[list] = relationship(
        "ProcessRecord", back_populates="review", order_by="ProcessRecord.created_at"
    )


class RiskTag(Base):
    __tablename__ = "risk_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    bindings: Mapped[list] = relationship("ClauseTagBinding", back_populates="tag")


class ClauseTagBinding(Base):
    __tablename__ = "clause_tag_bindings"
    __table_args__ = (
        UniqueConstraint("clause_id", "tag_id", name="uq_binding_clause_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clause_id: Mapped[int] = mapped_column(ForeignKey("clauses.id"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("risk_tags.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    clause: Mapped[Clause] = relationship("Clause", back_populates="tag_bindings")
    tag: Mapped[RiskTag] = relationship("RiskTag", back_populates="bindings")


class ProcessRecord(Base):
    __tablename__ = "process_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    review: Mapped[Review] = relationship("Review", back_populates="process_records")


class DocumentCopyMapping(Base):
    __tablename__ = "document_copy_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    target_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    copied_clause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_deprecated_clause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    copied_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_resolved_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    copied_tag_binding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    items: Mapped[list] = relationship("CopyItem", back_populates="mapping")


class CopyItem(Base):
    """复制明细：记录每个条款的复制/跳过动作，支撑复制结果详情查询。"""

    __tablename__ = "copy_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mapping_id: Mapped[int] = mapped_column(ForeignKey("document_copy_mappings.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)  # clause / review
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # copied / skipped
    source_clause_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_clause_id: Mapped[int] = mapped_column(Integer, nullable=True)
    source_review_id: Mapped[int] = mapped_column(Integer, nullable=True)
    clause_no: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=True)  # deprecated_clause / resolved_review
    inherited_tag_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON 数组
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mapping: Mapped[DocumentCopyMapping] = relationship("DocumentCopyMapping", back_populates="items")
