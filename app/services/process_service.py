from typing import List

from sqlalchemy.orm import Session

from app.enums import ProcessStatus
from app.exceptions.app_exceptions import NotFoundError
from app.models.process_record import ProcessRecord
from app.repositories.comment_repo import CommentRepository
from app.repositories.process_repo import ProcessRecordRepository
from app.schemas.process_record import ProcessRecordCreate


class ProcessService:
    def __init__(self, db: Session):
        self.db = db
        self.process_repo = ProcessRecordRepository(db)
        self.comment_repo = CommentRepository(db)

    def _create_record(
        self,
        comment_id: int,
        from_status: ProcessStatus,
        to_status: ProcessStatus,
        note: str,
        operator: str,
    ) -> ProcessRecord:
        record = self.process_repo.create(
            comment_id=comment_id,
            from_status=from_status.value,
            to_status=to_status.value,
            note=note or "",
            operator=operator or "system",
        )
        self.db.flush()
        return record

    def add_record(
        self, comment_id: int, payload: ProcessRecordCreate
    ) -> ProcessRecord:
        comment = self.comment_repo.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                message="Comment not found",
                details={"comment_id": comment_id},
            )

        current = ProcessStatus(comment.process_status)
        record = self._create_record(
            comment_id=comment_id,
            from_status=current,
            to_status=current,
            note=payload.note,
            operator=payload.operator,
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_history(self, comment_id: int) -> List[ProcessRecord]:
        comment = self.comment_repo.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                message="Comment not found",
                details={"comment_id": comment_id},
            )
        return self.process_repo.list_by_comment(comment_id)
