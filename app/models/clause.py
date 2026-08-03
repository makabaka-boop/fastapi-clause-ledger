from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    ForeignKey,
    UniqueConstraint,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class Clause(Base):
    __tablename__ = "clauses"
    __table_args__ = (
        UniqueConstraint("document_id", "clause_no", name="uq_clause_doc_no"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clause_no: Mapped[str] = mapped_column(String(100), nullable=False)
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    clause_type: Mapped[str] = mapped_column(String(100), nullable=False)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    document = relationship("Document", back_populates="clauses")
    comments = relationship(
        "Comment",
        back_populates="clause",
        cascade="all, delete-orphan",
    )
    tag_bindings = relationship(
        "TagBinding",
        back_populates="clause",
        cascade="all, delete-orphan",
    )
