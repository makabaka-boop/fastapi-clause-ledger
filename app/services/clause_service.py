from typing import List

from sqlalchemy.orm import Session

from app.enums import ImportMode
from app.exceptions.app_exceptions import (
    BusinessRuleError,
    DuplicateError,
    NotFoundError,
)
from app.models.clause import Clause
from app.repositories.clause_repo import ClauseRepository
from app.repositories.document_repo import DocumentRepository
from app.schemas.clause import (
    ClauseBatchCreate,
    ClauseImportRequest,
)


class ClauseService:
    def __init__(self, db: Session):
        self.db = db
        self.clause_repo = ClauseRepository(db)
        self.document_repo = DocumentRepository(db)

    def _ensure_document_exists(self, document_id: int):
        doc = self.document_repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                message="Document not found",
                details={"document_id": document_id},
            )
        return doc

    def batch_create(
        self, document_id: int, payload: ClauseBatchCreate
    ) -> dict:
        self._ensure_document_exists(document_id)

        seen = set()
        clause_ids = []
        for item in payload.clauses:
            if item.clause_no in seen:
                raise DuplicateError(
                    message="Duplicate clause_no in request",
                    details={"clause_no": item.clause_no},
                )
            seen.add(item.clause_no)

            existing = self.clause_repo.get_by_document_and_no(
                document_id, item.clause_no
            )
            if existing is not None:
                raise DuplicateError(
                    message="clause_no already exists in document",
                    details={
                        "document_id": document_id,
                        "clause_no": item.clause_no,
                    },
                )

            clause = self.clause_repo.create(
                document_id=document_id,
                clause_no=item.clause_no,
                clause_text=item.clause_text,
                clause_type=item.clause_type,
                importance=item.importance,
            )
            clause_ids.append(clause.id)

        self.db.commit()
        return {"created": len(clause_ids), "clause_ids": clause_ids}

    def idempotent_import(
        self, document_id: int, payload: ClauseImportRequest
    ) -> dict:
        self._ensure_document_exists(document_id)

        seen = set()
        created = 0
        updated = 0
        skipped = 0
        clause_ids = []
        id_mappings = []

        for item in payload.clauses:
            if item.clause_no in seen:
                raise DuplicateError(
                    message="Duplicate clause_no in import request",
                    details={"clause_no": item.clause_no},
                )
            seen.add(item.clause_no)

            existing = self.clause_repo.get_by_document_and_no(
                document_id, item.clause_no
            )

            if existing is not None:
                old_id = existing.id
                if payload.mode == ImportMode.SKIP_EXISTING:
                    skipped += 1
                    clause_ids.append(existing.id)
                    id_mappings.append(
                        {
                            "clause_no": item.clause_no,
                            "old_clause_id": old_id,
                            "final_clause_id": existing.id,
                            "action": "skipped",
                        }
                    )
                    continue
                existing.clause_text = item.clause_text
                existing.clause_type = item.clause_type
                existing.importance = item.importance
                self.db.flush()
                updated += 1
                clause_ids.append(existing.id)
                id_mappings.append(
                    {
                        "clause_no": item.clause_no,
                        "old_clause_id": old_id,
                        "final_clause_id": existing.id,
                        "action": "updated",
                    }
                )
            else:
                clause = self.clause_repo.create(
                    document_id=document_id,
                    clause_no=item.clause_no,
                    clause_text=item.clause_text,
                    clause_type=item.clause_type,
                    importance=item.importance,
                )
                created += 1
                clause_ids.append(clause.id)
                id_mappings.append(
                    {
                        "clause_no": item.clause_no,
                        "old_clause_id": None,
                        "final_clause_id": clause.id,
                        "action": "created",
                    }
                )

        self.db.commit()
        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "clause_ids": clause_ids,
            "id_mappings": id_mappings,
        }

    def deprecate(self, document_id: int, clause_id: int) -> Clause:
        self._ensure_document_exists(document_id)
        clause = self.clause_repo.get_by_id(clause_id)
        if clause is None or clause.document_id != document_id:
            raise NotFoundError(
                message="Clause not found in document",
                details={
                    "document_id": document_id,
                    "clause_id": clause_id,
                },
            )
        if clause.deprecated:
            raise BusinessRuleError(
                message="Clause is already deprecated",
                details={"clause_id": clause_id},
            )
        self.clause_repo.deprecate(clause)
        self.db.commit()
        self.db.refresh(clause)
        return clause

    def list_by_document(self, document_id: int) -> List[Clause]:
        self._ensure_document_exists(document_id)
        return self.clause_repo.list_by_document(document_id)
