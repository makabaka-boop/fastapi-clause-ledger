from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TagBinding(Base):
    __tablename__ = "tag_bindings"
    __table_args__ = (
        UniqueConstraint("clause_id", "tag_id", name="uq_binding_clause_tag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clause_id: Mapped[int] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clause = relationship("Clause", back_populates="tag_bindings")
    tag = relationship("Tag", back_populates="bindings")
