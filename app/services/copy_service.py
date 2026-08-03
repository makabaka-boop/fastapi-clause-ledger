from typing import Dict, List

from sqlalchemy.orm import Session

from app.exceptions.app_exceptions import NotFoundError
from app.models.copy_mapping import CopyMapping
from app.repositories.clause_repo import ClauseRepository
from app.repositories.comment_repo import CommentRepository
from app.repositories.copy_repo import CopyMappingRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.tag_repo import TagRepository
from app.schemas.copy import DocumentCopyRequest


class CopyService:
    def __init__(self, db: Session):
        self.db = db
        self.document_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.tag_repo = TagRepository(db)
        self.copy_repo = CopyMappingRepository(db)
        self.comment_repo = CommentRepository(db)

    def copy_document(
        self, source_document_id: int, payload: DocumentCopyRequest
    ) -> dict:
        source = self.document_repo.get_by_id(source_document_id)
        if source is None:
            raise NotFoundError(
                message="Source document not found",
                details={"document_id": source_document_id},
            )

        target = self.document_repo.create(
            title=source.title,
            source_department=source.source_department,
            version_no=payload.new_version_no,
            document_status=payload.target_status.value,
        )
        self.db.flush()

        mapping = self.copy_repo.create(
            source_document_id=source.id,
            target_document_id=target.id,
            copied_by=payload.copied_by,
        )
        self.db.flush()

        active_clauses = self.clause_repo.list_active_by_document(source.id)
        deprecated_clauses = self.clause_repo.list_deprecated_by_document(
            source.id
        )

        active_ids = [c.id for c in active_clauses]
        resolved_counts = self.comment_repo.count_resolved_by_clauses(
            active_ids
        )
        skipped_resolved_comment_count = sum(resolved_counts.values())

        copied_clauses = 0
        copied_tag_count = 0
        clause_mappings = []

        for src_clause in active_clauses:
            new_clause = self.clause_repo.create(
                document_id=target.id,
                clause_no=src_clause.clause_no,
                clause_text=src_clause.clause_text,
                clause_type=src_clause.clause_type,
                importance=src_clause.importance,
            )
            self.db.flush()
            copied_clauses += 1

            self.copy_repo.add_clause_mapping(
                copy_mapping_id=mapping.id,
                source_clause_id=src_clause.id,
                target_clause_id=new_clause.id,
            )

            bindings = self.tag_repo.list_bindings_by_clause(src_clause.id)
            copied_tag_ids = []
            for binding in bindings:
                self.tag_repo.create_binding(
                    clause_id=new_clause.id,
                    tag_id=binding.tag_id,
                )
                copied_tag_ids.append(binding.tag_id)
                copied_tag_count += 1

            clause_mappings.append(
                {
                    "source_clause_id": src_clause.id,
                    "target_clause_id": new_clause.id,
                    "clause_no": src_clause.clause_no,
                    "copied_tag_ids": copied_tag_ids,
                }
            )

        self.db.commit()
        self.db.refresh(mapping)

        return {
            "source_document_id": source.id,
            "target_document_id": target.id,
            "copied_clauses": copied_clauses,
            "copied_tag_count": copied_tag_count,
            "skipped_deprecated_count": len(deprecated_clauses),
            "skipped_resolved_comment_count": skipped_resolved_comment_count,
            "copy_mapping_id": mapping.id,
            "clause_mappings": clause_mappings,
        }

    def get_copy_detail(self, target_document_id: int) -> dict:
        target = self.document_repo.get_by_id(target_document_id)
        if target is None:
            raise NotFoundError(
                message="Target document not found",
                details={"document_id": target_document_id},
            )

        mappings = self.copy_repo.list_by_target_document(target_document_id)
        if not mappings:
            raise NotFoundError(
                message="No copy mapping found for target document",
                details={"target_document_id": target_document_id},
            )
        mapping = mappings[0]
        source_document_id = mapping.source_document_id

        deprecated_clauses = self.clause_repo.list_deprecated_by_document(
            source_document_id
        )
        skipped_clauses = [
            {
                "source_clause_id": c.id,
                "clause_no": c.clause_no,
                "reason": "deprecated",
            }
            for c in deprecated_clauses
        ]

        all_source_clauses = {
            c.id: c
            for c in self.clause_repo.list_by_document(source_document_id)
        }
        all_target_clauses = {
            c.id: c
            for c in self.clause_repo.list_by_document(target_document_id)
        }

        active_source_ids = [
            cm.source_clause_id for cm in mapping.clause_mappings
        ]
        resolved_counts = self.comment_repo.count_resolved_by_clauses(
            active_source_ids
        )

        tag_cache: Dict[int, dict] = {}

        copied_clauses = []
        for cm in mapping.clause_mappings:
            src = all_source_clauses.get(cm.source_clause_id)
            tgt = all_target_clauses.get(cm.target_clause_id)
            if src is None or tgt is None:
                continue

            bindings = self.tag_repo.list_bindings_by_clause(tgt.id)
            tag_ids = [b.tag_id for b in bindings]
            for tid in tag_ids:
                if tid not in tag_cache:
                    tag = self.tag_repo.get_by_id(tid)
                    tag_cache[tid] = (
                        {"tag_id": tag.id, "tag_name": tag.name}
                        if tag is not None
                        else {"tag_id": tid, "tag_name": ""}
                    )

            inherited_tags = [tag_cache[tid] for tid in tag_ids]

            copied_clauses.append(
                {
                    "source_clause_id": cm.source_clause_id,
                    "target_clause_id": cm.target_clause_id,
                    "clause_no": tgt.clause_no,
                    "clause_text": tgt.clause_text,
                    "clause_type": tgt.clause_type,
                    "importance": tgt.importance,
                    "inherited_tags": inherited_tags,
                    "source_resolved_comment_count": resolved_counts.get(
                        cm.source_clause_id, 0
                    ),
                }
            )

        summary = {
            "copied_clauses": len(copied_clauses),
            "skipped_deprecated_count": len(skipped_clauses),
            "copied_tag_count": sum(
                len(c["inherited_tags"]) for c in copied_clauses
            ),
            "skipped_resolved_comment_count": sum(
                c["source_resolved_comment_count"] for c in copied_clauses
            ),
        }

        return {
            "source_document_id": source_document_id,
            "target_document_id": target_document_id,
            "copy_mapping_id": mapping.id,
            "copied_clauses": copied_clauses,
            "skipped_clauses": skipped_clauses,
            "summary": summary,
        }

    def get_mapping(self, mapping_id: int) -> CopyMapping:
        mapping = self.copy_repo.get_by_id(mapping_id)
        if mapping is None:
            raise NotFoundError(
                message="Copy mapping not found",
                details={"copy_mapping_id": mapping_id},
            )
        return mapping

    def list_mappings(
        self,
        source_document_id: int = None,
        target_document_id: int = None,
    ) -> List[CopyMapping]:
        if source_document_id is not None:
            return self.copy_repo.list_by_source_document(source_document_id)
        if target_document_id is not None:
            return self.copy_repo.list_by_target_document(target_document_id)
        return self.copy_repo.list_all()
