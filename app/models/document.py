from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_department: Mapped[str] = mapped_column(String(200), nullable=False)
    version_no: Mapped[str] = mapped_column(String(100), nullable=False)
    document_status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    clauses = relationship(
        "Clause",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    source_mappings = relationship(
        "CopyMapping",
        back_populates="source_document",
        foreign_keys="CopyMapping.source_document_id",
    )
    target_mappings = relationship(
        "CopyMapping",
        back_populates="target_document",
        foreign_keys="CopyMapping.target_document_id",
    )
