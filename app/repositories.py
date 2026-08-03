from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.enums import ProcessStatus


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        title: str,
        source_department: str,
        version_no: str,
        document_status: str,
    ) -> models.Document:
        doc = models.Document(
            title=title,
            source_department=source_department,
            version_no=version_no,
            document_status=document_status,
        )
        self.db.add(doc)
        self.db.flush()
        return doc

    def get_by_id(self, document_id: int) -> Optional[models.Document]:
        return self.db.get(models.Document, document_id)

    def get_by_title_and_version(self, title: str, version_no: str) -> Optional[models.Document]:
        stmt = select(models.Document).where(
            models.Document.title == title,
            models.Document.version_no == version_no,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_status(self, document: models.Document, new_status: str) -> models.Document:
        document.document_status = new_status
        self.db.flush()
        return document

    def list_all(self) -> list[models.Document]:
        stmt = select(models.Document).order_by(models.Document.id)
        return list(self.db.execute(stmt).scalars().all())


class ClauseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        document_id: int,
        clause_no: str,
        clause_text: str,
        clause_type: str,
        importance: str,
    ) -> models.Clause:
        clause = models.Clause(
            document_id=document_id,
            clause_no=clause_no,
            clause_text=clause_text,
            clause_type=clause_type,
            importance=importance,
        )
        self.db.add(clause)
        self.db.flush()
        return clause

    def get_by_id(self, clause_id: int) -> Optional[models.Clause]:
        return self.db.get(models.Clause, clause_id)

    def get_by_document_and_no(
        self, document_id: int, clause_no: str
    ) -> Optional[models.Clause]:
        stmt = select(models.Clause).where(
            models.Clause.document_id == document_id,
            models.Clause.clause_no == clause_no,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_document(self, document_id: int) -> list[models.Clause]:
        stmt = (
            select(models.Clause)
            .where(models.Clause.document_id == document_id)
            .order_by(models.Clause.clause_no)
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_active_by_document(self, document_id: int) -> list[models.Clause]:
        stmt = (
            select(models.Clause)
            .where(
                models.Clause.document_id == document_id,
                models.Clause.deprecated.is_(False),
            )
            .order_by(models.Clause.clause_no)
        )
        return list(self.db.execute(stmt).scalars().all())

    def deprecate(self, clause: models.Clause) -> models.Clause:
        clause.deprecated = True
        self.db.flush()
        return clause

    def update_fields(self, clause: models.Clause, **fields) -> models.Clause:
        for key, value in fields.items():
            setattr(clause, key, value)
        self.db.flush()
        return clause


class CommentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        clause_id: int,
        reviewer_name: str,
        comment_text: str,
        risk_level: str,
        process_status: str = "open",
    ) -> models.Comment:
        comment = models.Comment(
            clause_id=clause_id,
            reviewer_name=reviewer_name,
            comment_text=comment_text,
            risk_level=risk_level,
            process_status=process_status,
        )
        self.db.add(comment)
        self.db.flush()
        return comment

    def get_by_id(self, comment_id: int) -> Optional[models.Comment]:
        return self.db.get(models.Comment, comment_id)

    def list_by_clause(self, clause_id: int) -> list[models.Comment]:
        stmt = (
            select(models.Comment)
            .where(models.Comment.clause_id == clause_id)
            .order_by(models.Comment.created_at.desc(), models.Comment.id.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_by_clause(self, clause_id: int) -> Optional[models.Comment]:
        stmt = (
            select(models.Comment)
            .where(models.Comment.clause_id == clause_id)
            .order_by(models.Comment.created_at.desc(), models.Comment.id.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_unresolved_by_risk_level(
        self, risk_level: str
    ) -> list[models.Comment]:
        unresolved_statuses = [
            ProcessStatus.OPEN.value,
            ProcessStatus.ACCEPTED.value,
        ]
        stmt = (
            select(models.Comment)
            .where(
                models.Comment.risk_level == risk_level,
                models.Comment.process_status.in_(unresolved_statuses),
            )
            .options(selectinload(models.Comment.clause))
            .order_by(models.Comment.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def update_status(self, comment: models.Comment, new_status: str) -> models.Comment:
        comment.process_status = new_status
        self.db.flush()
        return comment

    def list_by_document(self, document_id: int) -> list[models.Comment]:
        stmt = (
            select(models.Comment)
            .join(models.Clause, models.Comment.clause_id == models.Clause.id)
            .where(models.Clause.document_id == document_id)
            .options(selectinload(models.Comment.clause))
        )
        return list(self.db.execute(stmt).scalars().all())

    def count_by_document_and_status(self, document_id: int) -> dict[str, int]:
        stmt = (
            select(models.Comment.process_status, func.count(models.Comment.id))
            .join(models.Clause, models.Comment.clause_id == models.Clause.id)
            .where(models.Clause.document_id == document_id)
            .group_by(models.Comment.process_status)
        )
        rows = self.db.execute(stmt).all()
        return {status: count for status, count in rows}

    def count_by_document_and_risk(self, document_id: int) -> dict[str, int]:
        stmt = (
            select(models.Comment.risk_level, func.count(models.Comment.id))
            .join(models.Clause, models.Comment.clause_id == models.Clause.id)
            .where(models.Clause.document_id == document_id)
            .group_by(models.Comment.risk_level)
        )
        rows = self.db.execute(stmt).all()
        return {level: count for level, count in rows}


class RiskTagRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, name: str, description: str) -> models.RiskTag:
        tag = models.RiskTag(name=name, description=description)
        self.db.add(tag)
        self.db.flush()
        return tag

    def get_by_id(self, tag_id: int) -> Optional[models.RiskTag]:
        return self.db.get(models.RiskTag, tag_id)

    def get_by_name(self, name: str) -> Optional[models.RiskTag]:
        stmt = select(models.RiskTag).where(models.RiskTag.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self) -> list[models.RiskTag]:
        stmt = select(models.RiskTag).order_by(models.RiskTag.id)
        return list(self.db.execute(stmt).scalars().all())


class TagBindingRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, clause_id: int, tag_id: int) -> models.TagBinding:
        binding = models.TagBinding(clause_id=clause_id, tag_id=tag_id)
        self.db.add(binding)
        self.db.flush()
        return binding

    def get_by_clause_and_tag(
        self, clause_id: int, tag_id: int
    ) -> Optional[models.TagBinding]:
        stmt = select(models.TagBinding).where(
            models.TagBinding.clause_id == clause_id,
            models.TagBinding.tag_id == tag_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_clause(self, clause_id: int) -> list[models.TagBinding]:
        stmt = select(models.TagBinding).where(models.TagBinding.clause_id == clause_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_tag(self, tag_id: int) -> list[models.TagBinding]:
        stmt = select(models.TagBinding).where(models.TagBinding.tag_id == tag_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_by_clause_ids(self, clause_ids: list[int]) -> list[models.TagBinding]:
        if not clause_ids:
            return []
        stmt = select(models.TagBinding).where(models.TagBinding.clause_id.in_(clause_ids))
        return list(self.db.execute(stmt).scalars().all())


class ProcessingRecordRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        comment_id: int,
        from_status: str,
        to_status: str,
        action: str,
        operator: str,
        note: str,
    ) -> models.ProcessingRecord:
        record = models.ProcessingRecord(
            comment_id=comment_id,
            from_status=from_status,
            to_status=to_status,
            action=action,
            operator=operator,
            note=note,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def list_by_comment(self, comment_id: int) -> list[models.ProcessingRecord]:
        stmt = (
            select(models.ProcessingRecord)
            .where(models.ProcessingRecord.comment_id == comment_id)
            .order_by(models.ProcessingRecord.created_at.asc(), models.ProcessingRecord.id.asc())
        )
        return list(self.db.execute(stmt).scalars().all())


class DocumentCopyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        source_document_id: int,
        target_document_id: int,
        copy_type: str = "version_copy",
    ) -> models.DocumentCopy:
        mapping = models.DocumentCopy(
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            copy_type=copy_type,
        )
        self.db.add(mapping)
        self.db.flush()
        return mapping

    def list_by_source(self, source_document_id: int) -> list[models.DocumentCopy]:
        stmt = select(models.DocumentCopy).where(
            models.DocumentCopy.source_document_id == source_document_id
        )
        return list(self.db.execute(stmt).scalars().all())

    def list_all(self) -> list[models.DocumentCopy]:
        stmt = select(models.DocumentCopy).order_by(models.DocumentCopy.id)
        return list(self.db.execute(stmt).scalars().all())
