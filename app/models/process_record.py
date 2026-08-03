from sqlalchemy import String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow


class ProcessRecord(Base):
    __tablename__ = "process_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    operator: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    comment = relationship("Comment", back_populates="process_records")
