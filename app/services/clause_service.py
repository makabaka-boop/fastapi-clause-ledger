from typing import List

from sqlalchemy.orm import Session

from ..exceptions import (
    ClauseDeprecatedError,
    DuplicateClauseNoError,
    InvalidImportModeError,
    NotFoundError,
)
from ..constants import IMPORT_MODES
from ..models import Clause
from ..repositories.clauses import ClauseRepository
from ..schemas import ClauseBatchCreate, ClauseImport
from .document_service import DocumentService


class ClauseService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ClauseRepository(db)
        self.doc_service = DocumentService(db)

    def get_or_404(self, clause_id: int) -> Clause:
        clause = self.repo.get(clause_id)
        if clause is None:
            raise NotFoundError(f"条款不存在: {clause_id}", {"clause_id": clause_id})
        return clause

    def batch_create(self, document_id: int, data: ClauseBatchCreate) -> List[Clause]:
        self.doc_service.get_or_404(document_id)
        created: List[Clause] = []
        seen = set()
        for item in data.clauses:
            if item.clause_no in seen or self.repo.get_by_no(document_id, item.clause_no):
                self.db.rollback()
                raise DuplicateClauseNoError(
                    f"同一文档下 clause_no 不允许重复: {item.clause_no}",
                    {"document_id": document_id, "clause_no": item.clause_no},
                )
            seen.add(item.clause_no)
            created.append(self.repo.create(document_id, item))
        self.db.commit()
        return created

    def import_clauses(self, document_id: int, data: ClauseImport) -> dict:
        """幂等导入。mode 仅允许 skip_existing / update_existing。"""
        self.doc_service.get_or_404(document_id)
        if data.mode not in IMPORT_MODES:
            raise InvalidImportModeError(
                f"mode 只能是 {list(IMPORT_MODES)} 之一", {"mode": data.mode}
            )
        created, updated, skipped = [], [], []
        mapping = []
        for item in data.clauses:
            existing = self.repo.get_by_no(document_id, item.clause_no)
            if existing is None:
                clause = self.repo.create(document_id, item)
                created.append(clause)
                mapping.append({"old_clause_id": None, "final_clause_id": clause.id, "action": "created"})
            elif data.mode == "skip_existing":
                skipped.append(existing)
                mapping.append({"old_clause_id": existing.id, "final_clause_id": existing.id, "action": "skipped"})
            else:  # update_existing
                clause = self.repo.update(existing, item)
                updated.append(clause)
                mapping.append({"old_clause_id": existing.id, "final_clause_id": clause.id, "action": "updated"})
        self.db.commit()
        return {
            "mode": data.mode,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "clause_id_mapping": mapping,
        }

    def deprecate(self, clause_id: int) -> Clause:
        clause = self.get_or_404(clause_id)
        clause = self.repo.deprecate(clause)
        self.db.commit()
        return clause

    def ensure_not_deprecated(self, clause: Clause) -> None:
        if clause.deprecated:
            raise ClauseDeprecatedError(
                f"条款 {clause.id} 已废弃，不能新增意见、绑定新标签或变更意见状态",
                {"clause_id": clause.id},
            )
