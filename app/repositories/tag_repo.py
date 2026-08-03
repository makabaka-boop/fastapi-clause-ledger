from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.tag import Tag
from app.models.tag_binding import TagBinding
from app.repositories.base import BaseRepository


class TagRepository(BaseRepository[Tag]):
    def __init__(self, db: Session):
        super().__init__(Tag, db)

    def get_by_id(self, tag_id: int) -> Optional[Tag]:
        return self.db.get(Tag, tag_id)

    def get_by_ids(self, tag_ids: List[int]) -> List[Tag]:
        if not tag_ids:
            return []
        stmt = select(Tag).where(Tag.id.in_(tag_ids)).order_by(Tag.id)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_name(self, name: str) -> Optional[Tag]:
        stmt = select(Tag).where(Tag.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def list_all(self) -> List[Tag]:
        return list(self.db.execute(select(Tag).order_by(Tag.id)).scalars().all())

    def create(self, name: str) -> Tag:
        tag = Tag(name=name)
        return self.add(tag)

    def get_binding(
        self, clause_id: int, tag_id: int
    ) -> Optional[TagBinding]:
        stmt = select(TagBinding).where(
            TagBinding.clause_id == clause_id,
            TagBinding.tag_id == tag_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create_binding(self, clause_id: int, tag_id: int) -> TagBinding:
        binding = TagBinding(clause_id=clause_id, tag_id=tag_id)
        self.db.add(binding)
        self.db.flush()
        self.db.refresh(binding)
        return binding

    def list_bindings_by_clause(self, clause_id: int) -> List[TagBinding]:
        stmt = select(TagBinding).where(TagBinding.clause_id == clause_id)
        return list(self.db.execute(stmt).scalars().all())

    def list_bindings_by_document(self, document_id: int) -> List[TagBinding]:
        from app.models.clause import Clause

        stmt = (
            select(TagBinding)
            .join(Clause, Clause.id == TagBinding.clause_id)
            .where(Clause.document_id == document_id)
        )
        return list(self.db.execute(stmt).scalars().all())
