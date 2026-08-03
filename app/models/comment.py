from sqlalchemy import String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clause_id: Mapped[int] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    process_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    clause = relationship("Clause", back_populates="comments")
    process_records = relationship(
        "ProcessRecord",
        back_populates="comment",
        cascade="all, delete-orphan",
    )
