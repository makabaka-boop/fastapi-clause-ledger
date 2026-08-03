from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.exceptions.app_exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
)
from app.models.comment import Comment
from app.models.clause import Clause
from app.models.tag import Tag
from app.models.tag_binding import TagBinding
from app.repositories.clause_repo import ClauseRepository
from app.repositories.tag_repo import TagRepository
from app.schemas.tag import TagCreate, TagBindRequest


class TagService:
    def __init__(self, db: Session):
        self.db = db
        self.tag_repo = TagRepository(db)
        self.clause_repo = ClauseRepository(db)

    def create_tag(self, payload: TagCreate) -> Tag:
        existing = self.tag_repo.get_by_name(payload.name)
        if existing is not None:
            raise DuplicateError(
                message="Tag name already exists",
                details={"name": payload.name},
            )
        tag = self.tag_repo.create(payload.name)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def get_tag(self, tag_id: int) -> Tag:
        tag = self.tag_repo.get_by_id(tag_id)
        if tag is None:
            raise NotFoundError(
                message="Tag not found",
                details={"tag_id": tag_id},
            )
        return tag

    def list_tags(self) -> List[Tag]:
        return self.tag_repo.list_all()

    def bind_tag(self, payload: TagBindRequest) -> TagBinding:
        clause = self.clause_repo.get_by_id(payload.clause_id)
        if clause is None:
            raise NotFoundError(
                message="Clause not found",
                details={"clause_id": payload.clause_id},
            )
        if clause.deprecated:
            raise BusinessRuleError(
                message="Cannot bind tag to a deprecated clause",
                details={"clause_id": payload.clause_id},
            )

        tag = self.tag_repo.get_by_id(payload.tag_id)
        if tag is None:
            raise NotFoundError(
                message="Tag not found",
                details={"tag_id": payload.tag_id},
            )

        existing = self.tag_repo.get_binding(
            payload.clause_id, payload.tag_id
        )
        if existing is not None:
            raise DuplicateError(
                message="Tag is already bound to clause",
                details={
                    "clause_id": payload.clause_id,
                    "tag_id": payload.tag_id,
                },
            )

        binding = self.tag_repo.create_binding(
            payload.clause_id, payload.tag_id
        )
        self.db.commit()
        self.db.refresh(binding)
        return binding

    def risk_distribution(
        self, document_id: int = None
    ) -> List[Dict]:
        from sqlalchemy import select

        stmt = (
            select(
                Tag.id.label("tag_id"),
                Tag.name.label("tag_name"),
                Comment.risk_level.label("risk_level"),
                func.count(Comment.id).label("cnt"),
            )
            .join(TagBinding, TagBinding.tag_id == Tag.id)
            .join(Clause, Clause.id == TagBinding.clause_id)
            .outerjoin(Comment, Comment.clause_id == Clause.id)
            .group_by(Tag.id, Tag.name, Comment.risk_level)
            .order_by(Tag.id)
        )
        if document_id is not None:
            stmt = stmt.where(Clause.document_id == document_id)

        rows = self.db.execute(stmt).all()

        aggregated: Dict[int, Dict] = {}
        for row in rows:
            tag_id = row.tag_id
            if tag_id not in aggregated:
                aggregated[tag_id] = {
                    "tag_id": tag_id,
                    "tag_name": row.tag_name,
                    "low": 0,
                    "medium": 0,
                    "high": 0,
                    "critical": 0,
                    "total": 0,
                }
            if row.risk_level is not None:
                aggregated[tag_id][row.risk_level] = row.cnt or 0

        result = []
        for item in aggregated.values():
            item["total"] = (
                item["low"] + item["medium"] + item["high"] + item["critical"]
            )
            result.append(item)
        return result
