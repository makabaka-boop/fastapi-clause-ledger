from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessRecord


class ProcessRecordRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        review_id: int,
        from_status: Optional[str],
        to_status: str,
        operator_name: str,
        note: str = "",
    ) -> ProcessRecord:
        record = ProcessRecord(
            review_id=review_id,
            from_status=from_status,
            to_status=to_status,
            operator_name=operator_name,
            note=note,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def list_by_review(self, review_id: int) -> List[ProcessRecord]:
        stmt = (
            select(ProcessRecord)
            .where(ProcessRecord.review_id == review_id)
            .order_by(ProcessRecord.created_at, ProcessRecord.id)
        )
        return list(self.db.scalars(stmt).all())
