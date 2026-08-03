from sqlalchemy import String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class CopyMapping(Base):
    __tablename__ = "copy_mappings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    copied_by: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    source_document = relationship(
        "Document",
        back_populates="source_mappings",
        foreign_keys=[source_document_id],
    )
    target_document = relationship(
        "Document",
        back_populates="target_mappings",
        foreign_keys=[target_document_id],
    )

    clause_mappings = relationship(
        "ClauseCopyMapping",
        back_populates="copy_mapping",
        cascade="all, delete-orphan",
    )


class ClauseCopyMapping(Base):
    __tablename__ = "clause_copy_mappings"
    __table_args__ = (
        UniqueConstraint(
            "copy_mapping_id",
            "source_clause_id",
            name="uq_clause_copy_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    copy_mapping_id: Mapped[int] = mapped_column(
        ForeignKey("copy_mappings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_clause_id: Mapped[int] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_clause_id: Mapped[int] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
    )

    copy_mapping = relationship("CopyMapping", back_populates="clause_mappings")
