from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.process_record import ProcessRecord
from app.repositories.base import BaseRepository


class ProcessRecordRepository(BaseRepository[ProcessRecord]):
    def __init__(self, db: Session):
        super().__init__(ProcessRecord, db)

    def get_by_id(self, record_id: int) -> Optional[ProcessRecord]:
        return self.db.get(ProcessRecord, record_id)

    def list_by_comment(self, comment_id: int) -> List[ProcessRecord]:
        stmt = (
            select(ProcessRecord)
            .where(ProcessRecord.comment_id == comment_id)
            .order_by(ProcessRecord.created_at.asc(), ProcessRecord.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def create(
        self,
        comment_id: int,
        from_status: str,
        to_status: str,
        note: str,
        operator: str,
    ) -> ProcessRecord:
        record = ProcessRecord(
            comment_id=comment_id,
            from_status=from_status,
            to_status=to_status,
            note=note,
            operator=operator,
        )
        return self.add(record)
