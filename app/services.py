from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.enums import ImportMode, ProcessStatus, RiskLevel
from app.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
)
from app.repositories import (
    ClauseRepository,
    CommentRepository,
    DocumentCopyRepository,
    DocumentRepository,
    ProcessingRecordRepository,
    RiskTagRepository,
    TagBindingRepository,
)
from app.state_machine import requires_processing_record, validate_transition


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentRepository(db)

    def create_document(self, payload: schemas.DocumentCreate) -> models.Document:
        existing = self.documents.get_by_title_and_version(payload.title, payload.version_no)
        if existing is not None:
            raise ConflictError(
                "Document with the same title and version already exists",
                details={"title": payload.title, "version_no": payload.version_no},
            )
        doc = self.documents.create(
            title=payload.title,
            source_department=payload.source_department,
            version_no=payload.version_no,
            document_status=payload.document_status.value,
        )
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_document(self, document_id: int) -> models.Document:
        doc = self.documents.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                "Document not found",
                details={"document_id": document_id},
            )
        return doc

    def update_status(
        self, document_id: int, payload: schemas.DocumentStatusUpdate
    ) -> models.Document:
        doc = self.get_document(document_id)
        self.documents.update_status(doc, payload.document_status.value)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def list_documents(self) -> list[models.Document]:
        return self.documents.list_all()


class ClauseService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.clauses = ClauseRepository(db)
        self.documents = DocumentRepository(db)

    def _ensure_document(self, document_id: int) -> models.Document:
        doc = self.documents.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                "Document not found",
                details={"document_id": document_id},
            )
        return doc

    def batch_create(
        self, document_id: int, payload: schemas.ClauseBatchCreate
    ) -> list[models.Clause]:
        self._ensure_document(document_id)

        seen: set[str] = set()
        for item in payload.clauses:
            if item.clause_no in seen:
                raise ConflictError(
                    "Duplicate clause_no in request batch",
                    details={"clause_no": item.clause_no},
                )
            seen.add(item.clause_no)
            existing = self.clauses.get_by_document_and_no(document_id, item.clause_no)
            if existing is not None:
                raise ConflictError(
                    "clause_no already exists in document",
                    details={"document_id": document_id, "clause_no": item.clause_no},
                )

        created: list[models.Clause] = []
        for item in payload.clauses:
            clause = self.clauses.create(
                document_id=document_id,
                clause_no=item.clause_no,
                clause_text=item.clause_text,
                clause_type=item.clause_type,
                importance=item.importance,
            )
            created.append(clause)
        self.db.commit()
        for clause in created:
            self.db.refresh(clause)
        return created

    def idempotent_import(
        self, document_id: int, payload: schemas.ClauseImportRequest
    ) -> tuple[list[models.Clause], int, int, int, list[dict]]:
        self._ensure_document(document_id)

        seen: set[str] = set()
        for item in payload.clauses:
            if item.clause_no in seen:
                raise ConflictError(
                    "Duplicate clause_no in import batch",
                    details={"clause_no": item.clause_no},
                )
            seen.add(item.clause_no)

        created_count = 0
        updated_count = 0
        skipped_count = 0
        result: list[models.Clause] = []
        id_mapping: list[dict] = []

        for item in payload.clauses:
            existing = self.clauses.get_by_document_and_no(document_id, item.clause_no)
            if existing is None:
                clause = self.clauses.create(
                    document_id=document_id,
                    clause_no=item.clause_no,
                    clause_text=item.clause_text,
                    clause_type=item.clause_type,
                    importance=item.importance,
                )
                created_count += 1
                result.append(clause)
                id_mapping.append(
                    {
                        "clause_no": item.clause_no,
                        "old_id": None,
                        "final_id": clause.id,
                    }
                )
                continue

            if payload.mode == ImportMode.SKIP_EXISTING:
                skipped_count += 1
                result.append(existing)
                id_mapping.append(
                    {
                        "clause_no": item.clause_no,
                        "old_id": existing.id,
                        "final_id": existing.id,
                    }
                )
            elif payload.mode == ImportMode.UPDATE_EXISTING:
                self.clauses.update_fields(
                    existing,
                    clause_text=item.clause_text,
                    clause_type=item.clause_type,
                    importance=item.importance,
                )
                updated_count += 1
                result.append(existing)
                id_mapping.append(
                    {
                        "clause_no": item.clause_no,
                        "old_id": existing.id,
                        "final_id": existing.id,
                    }
                )

        self.db.commit()
        for clause in result:
            self.db.refresh(clause)
        return result, created_count, updated_count, skipped_count, id_mapping

    def deprecate(self, clause_id: int) -> models.Clause:
        clause = self.clauses.get_by_id(clause_id)
        if clause is None:
            raise NotFoundError(
                "Clause not found",
                details={"clause_id": clause_id},
            )
        if clause.deprecated:
            raise BusinessRuleError(
                "Clause is already deprecated",
                details={"clause_id": clause_id},
            )
        self.clauses.deprecate(clause)
        self.db.commit()
        self.db.refresh(clause)
        return clause

    def get_clause(self, clause_id: int) -> models.Clause:
        clause = self.clauses.get_by_id(clause_id)
        if clause is None:
            raise NotFoundError(
                "Clause not found",
                details={"clause_id": clause_id},
            )
        return clause

    def list_by_document(self, document_id: int) -> list[models.Clause]:
        self._ensure_document(document_id)
        return self.clauses.list_by_document(document_id)

    def list_by_document_with_latest_comments(
        self, document_id: int
    ) -> list[tuple[models.Clause, Optional[models.Comment]]]:
        self._ensure_document(document_id)
        clauses = self.clauses.list_by_document(document_id)
        comments_repo = CommentRepository(self.db)
        result: list[tuple[models.Clause, Optional[models.Comment]]] = []
        for clause in clauses:
            latest = comments_repo.get_latest_by_clause(clause.id)
            result.append((clause, latest))
        return result


class RiskTagService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tags = RiskTagRepository(db)

    def create_tag(self, payload: schemas.RiskTagCreate) -> models.RiskTag:
        existing = self.tags.get_by_name(payload.name)
        if existing is not None:
            raise ConflictError(
                "Risk tag with the same name already exists",
                details={"name": payload.name},
            )
        tag = self.tags.create(name=payload.name, description=payload.description)
        self.db.commit()
        self.db.refresh(tag)
        return tag

    def get_tag(self, tag_id: int) -> models.RiskTag:
        tag = self.tags.get_by_id(tag_id)
        if tag is None:
            raise NotFoundError(
                "Risk tag not found",
                details={"tag_id": tag_id},
            )
        return tag

    def list_tags(self) -> list[models.RiskTag]:
        return self.tags.list_all()


class CommentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.comments = CommentRepository(db)
        self.clauses = ClauseRepository(db)
        self.tags = RiskTagRepository(db)
        self.bindings = TagBindingRepository(db)
        self.records = ProcessingRecordRepository(db)

    def _get_clause(self, clause_id: int) -> models.Clause:
        clause = self.clauses.get_by_id(clause_id)
        if clause is None:
            raise NotFoundError(
                "Clause not found",
                details={"clause_id": clause_id},
            )
        return clause

    def add_comment(self, payload: schemas.CommentCreate, clause_id: int) -> models.Comment:
        clause = self._get_clause(clause_id)
        if clause.deprecated:
            raise BusinessRuleError(
                "Cannot add comment to a deprecated clause",
                details={"clause_id": clause_id},
            )
        comment = self.comments.create(
            clause_id=clause_id,
            reviewer_name=payload.reviewer_name,
            comment_text=payload.comment_text,
            risk_level=payload.risk_level.value,
            process_status=ProcessStatus.OPEN.value,
        )
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def bind_tag(self, clause_id: int, payload: schemas.TagBindRequest) -> models.TagBinding:
        clause = self._get_clause(clause_id)
        if clause.deprecated:
            raise BusinessRuleError(
                "Cannot bind tag to a deprecated clause",
                details={"clause_id": clause_id},
            )
        tag = self.tags.get_by_id(payload.tag_id)
        if tag is None:
            raise NotFoundError(
                "Risk tag not found",
                details={"tag_id": payload.tag_id},
            )
        existing = self.bindings.get_by_clause_and_tag(clause_id, payload.tag_id)
        if existing is not None:
            raise ConflictError(
                "Tag is already bound to this clause",
                details={"clause_id": clause_id, "tag_id": payload.tag_id},
            )
        binding = self.bindings.create(clause_id=clause_id, tag_id=payload.tag_id)
        self.db.commit()
        self.db.refresh(binding)
        return binding

    def change_status(
        self, comment_id: int, payload: schemas.CommentStatusUpdate
    ) -> tuple[models.Comment, Optional[models.ProcessingRecord]]:
        comment = self.comments.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                "Comment not found",
                details={"comment_id": comment_id},
            )

        clause = self.clauses.get_by_id(comment.clause_id)
        if clause is not None and clause.deprecated:
            raise BusinessRuleError(
                "Cannot change comment status for a deprecated clause",
                details={"clause_id": comment.clause_id, "comment_id": comment_id},
            )

        current_status = ProcessStatus(comment.process_status)
        target_status = payload.process_status

        validate_transition(current_status, target_status)

        record: Optional[models.ProcessingRecord] = None
        if requires_processing_record(current_status, target_status):
            record = self.records.create(
                comment_id=comment.id,
                from_status=current_status.value,
                to_status=target_status.value,
                action="status_transition",
                operator=payload.operator,
                note=payload.note,
            )

        self.comments.update_status(comment, target_status.value)
        self.db.commit()
        self.db.refresh(comment)
        if record is not None:
            self.db.refresh(record)
        return comment, record

    def add_processing_record(
        self, comment_id: int, payload: schemas.ProcessingRecordCreate
    ) -> models.ProcessingRecord:
        comment = self.comments.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                "Comment not found",
                details={"comment_id": comment_id},
            )
        current = ProcessStatus(comment.process_status)
        record = self.records.create(
            comment_id=comment.id,
            from_status=current.value,
            to_status=current.value,
            action=payload.action,
            operator=payload.operator,
            note=payload.note,
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_processing_history(self, comment_id: int) -> list[models.ProcessingRecord]:
        comment = self.comments.get_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                "Comment not found",
                details={"comment_id": comment_id},
            )
        return self.records.list_by_comment(comment_id)

    def list_unresolved_by_risk_level(self, risk_level: RiskLevel) -> list[models.Comment]:
        return self.comments.list_unresolved_by_risk_level(risk_level.value)

    def list_tags_for_clause(self, clause_id: int) -> list[models.TagBinding]:
        self._get_clause(clause_id)
        return self.bindings.list_by_clause(clause_id)


class DocumentCopyService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentRepository(db)
        self.clauses = ClauseRepository(db)
        self.comments = CommentRepository(db)
        self.bindings = TagBindingRepository(db)
        self.tags = RiskTagRepository(db)
        self.copies = DocumentCopyRepository(db)

    def _inherited_tags(self, source_clause_id: int) -> list[tuple[int, str]]:
        tags: list[tuple[int, str]] = []
        for binding in self.bindings.list_by_clause(source_clause_id):
            tag = self.tags.get_by_id(binding.tag_id)
            if tag is not None:
                tags.append((tag.id, tag.name))
        return tags

    def copy_document(
        self, source_document_id: int, payload: schemas.DocumentCopyRequest
    ) -> schemas.DocumentCopyResult:
        source = self.documents.get_by_id(source_document_id)
        if source is None:
            raise NotFoundError(
                "Source document not found",
                details={"source_document_id": source_document_id},
            )

        new_title = payload.new_title or source.title
        conflict = self.documents.get_by_title_and_version(new_title, payload.new_version_no)
        if conflict is not None:
            raise ConflictError(
                "Target document with same title and version already exists",
                details={"title": new_title, "version_no": payload.new_version_no},
            )

        target = self.documents.create(
            title=new_title,
            source_department=source.source_department,
            version_no=payload.new_version_no,
            document_status=source.document_status,
        )

        active_clauses = self.clauses.list_active_by_document(source_document_id)
        all_source_clauses = self.clauses.list_by_document(source_document_id)
        skipped_deprecated = [c for c in all_source_clauses if c.deprecated]

        clause_mappings: list[schemas.ClauseCopyMapping] = []
        copied_tag_count = 0
        total_skipped_resolved_comments = 0

        for src_clause in active_clauses:
            new_clause = self.clauses.create(
                document_id=target.id,
                clause_no=src_clause.clause_no,
                clause_text=src_clause.clause_text,
                clause_type=src_clause.clause_type,
                importance=src_clause.importance,
            )

            inherited_tags = self._inherited_tags(src_clause.id)
            for tag_id, _name in inherited_tags:
                self.bindings.create(clause_id=new_clause.id, tag_id=tag_id)
            copied_tag_count += len(inherited_tags)

            copied_comments = 0
            skipped_resolved = 0
            for src_comment in self.comments.list_by_clause(src_clause.id):
                if src_comment.process_status == ProcessStatus.RESOLVED.value:
                    skipped_resolved += 1
                    total_skipped_resolved_comments += 1
                    continue
                self.comments.create(
                    clause_id=new_clause.id,
                    reviewer_name=src_comment.reviewer_name,
                    comment_text=src_comment.comment_text,
                    risk_level=src_comment.risk_level,
                    process_status=src_comment.process_status,
                )
                copied_comments += 1

            clause_mappings.append(
                schemas.ClauseCopyMapping(
                    source_clause_id=src_clause.id,
                    target_clause_id=new_clause.id,
                    clause_no=src_clause.clause_no,
                    inherited_tags=[
                        schemas.InheritedTagOut(tag_id=tid, tag_name=tname)
                        for tid, tname in inherited_tags
                    ],
                    copied_comment_count=copied_comments,
                    skipped_resolved_comment_count=skipped_resolved,
                )
            )

        mapping = self.copies.create(
            source_document_id=source_document_id,
            target_document_id=target.id,
            copy_type="version_copy",
        )

        self.db.commit()
        self.db.refresh(target)
        self.db.refresh(mapping)

        return schemas.DocumentCopyResult(
            source_document_id=source_document_id,
            target_document_id=target.id,
            clause_mappings=clause_mappings,
            copied_tag_count=copied_tag_count,
            skipped_deprecated_count=len(skipped_deprecated),
            skipped_resolved_comment_count=total_skipped_resolved_comments,
            created_at=mapping.created_at,
        )

    def get_copy_detail(self, target_document_id: int) -> schemas.DocumentCopyDetail:
        target = self.documents.get_by_id(target_document_id)
        if target is None:
            raise NotFoundError(
                "Target document not found",
                details={"target_document_id": target_document_id},
            )

        mapping_record = None
        for copy in self.copies.list_all():
            if copy.target_document_id == target_document_id:
                mapping_record = copy
                break
        if mapping_record is None:
            raise NotFoundError(
                "No copy mapping found for target document",
                details={"target_document_id": target_document_id},
            )

        source_id = mapping_record.source_document_id
        source = self.documents.get_by_id(source_id)

        target_clauses = self.clauses.list_by_document(target_document_id)
        source_clauses = {
            c.clause_no: c for c in self.clauses.list_by_document(source_id)
        }

        clause_details: list[schemas.CopyClauseDetail] = []
        for t_clause in target_clauses:
            s_clause = source_clauses.get(t_clause.clause_no)
            if s_clause is None:
                continue

            inherited_tags = [
                schemas.InheritedTagOut(tag_id=tid, tag_name=tname)
                for tid, tname in self._inherited_tags(t_clause.id)
            ]

            copied_comments = [
                schemas.CommentOut.model_validate(c)
                for c in self.comments.list_by_clause(t_clause.id)
            ]

            skipped_reasons: list[str] = []
            for src_comment in self.comments.list_by_clause(s_clause.id):
                if src_comment.process_status == ProcessStatus.RESOLVED.value:
                    skipped_reasons.append(
                        f"comment {src_comment.id} skipped: resolved"
                    )

            clause_details.append(
                schemas.CopyClauseDetail(
                    source_clause_id=s_clause.id,
                    target_clause_id=t_clause.id,
                    clause_no=t_clause.clause_no,
                    source_clause_text=s_clause.clause_text,
                    target_clause_text=t_clause.clause_text,
                    inherited_tags=inherited_tags,
                    copied_comments=copied_comments,
                    skipped_reasons=skipped_reasons,
                )
            )

        skipped_deprecated = [
            schemas.DeprecatedClauseSkip(
                source_clause_id=c.id,
                clause_no=c.clause_no,
            )
            for c in source_clauses.values()
            if c.deprecated
        ]

        return schemas.DocumentCopyDetail(
            source_document_id=source_id,
            target_document_id=target_document_id,
            copy_type=mapping_record.copy_type,
            created_at=mapping_record.created_at,
            clauses=clause_details,
            skipped_deprecated_clauses=skipped_deprecated,
        )

    def list_copy_mappings(self) -> list[models.DocumentCopy]:
        return self.copies.list_all()

    def list_by_source(self, source_document_id: int) -> list[models.DocumentCopy]:
        source = self.documents.get_by_id(source_document_id)
        if source is None:
            raise NotFoundError(
                "Source document not found",
                details={"source_document_id": source_document_id},
            )
        return self.copies.list_by_source(source_document_id)


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.documents = DocumentRepository(db)
        self.clauses = ClauseRepository(db)
        self.comments = CommentRepository(db)
        self.bindings = TagBindingRepository(db)
        self.tags = RiskTagRepository(db)

    def document_dashboard(self, document_id: int) -> schemas.DashboardSummary:
        doc = self.documents.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                "Document not found",
                details={"document_id": document_id},
            )

        clauses = self.clauses.list_by_document(document_id)
        total_clauses = len(clauses)
        deprecated_clauses = sum(1 for c in clauses if c.deprecated)

        comments = self.comments.list_by_document(document_id)
        total_comments = len(comments)

        status_counts = {
            ProcessStatus.OPEN.value: 0,
            ProcessStatus.ACCEPTED.value: 0,
            ProcessStatus.REJECTED.value: 0,
            ProcessStatus.RESOLVED.value: 0,
        }
        risk_counts = {
            RiskLevel.LOW.value: 0,
            RiskLevel.MEDIUM.value: 0,
            RiskLevel.HIGH.value: 0,
            RiskLevel.CRITICAL.value: 0,
        }

        critical_unresolved = 0
        for comment in comments:
            status_counts[comment.process_status] = status_counts.get(
                comment.process_status, 0
            ) + 1
            risk_counts[comment.risk_level] = risk_counts.get(comment.risk_level, 0) + 1
            if (
                comment.risk_level == RiskLevel.CRITICAL.value
                and comment.process_status
                not in (
                    ProcessStatus.RESOLVED.value,
                    ProcessStatus.REJECTED.value,
                )
            ):
                critical_unresolved += 1

        return schemas.DashboardSummary(
            document_id=document_id,
            total_clauses=total_clauses,
            deprecated_clauses=deprecated_clauses,
            total_comments=total_comments,
            open_comments=status_counts[ProcessStatus.OPEN.value],
            accepted_comments=status_counts[ProcessStatus.ACCEPTED.value],
            rejected_comments=status_counts[ProcessStatus.REJECTED.value],
            resolved_comments=status_counts[ProcessStatus.RESOLVED.value],
            risk_distribution=risk_counts,
            critical_unresolved=critical_unresolved,
        )

    def risk_distribution_by_tag(self) -> list[schemas.RiskDistributionItem]:
        tags = self.tags.list_all()
        all_bindings = {tag.id: self.bindings.list_by_tag(tag.id) for tag in tags}

        result: list[schemas.RiskDistributionItem] = []
        for tag in tags:
            bindings = all_bindings[tag.id]
            counts = {
                RiskLevel.LOW.value: 0,
                RiskLevel.MEDIUM.value: 0,
                RiskLevel.HIGH.value: 0,
                RiskLevel.CRITICAL.value: 0,
            }
            total = 0
            for binding in bindings:
                clause = self.clauses.get_by_id(binding.clause_id)
                if clause is None or clause.deprecated:
                    continue
                comments = self.comments.list_by_clause(clause.id)
                counted_comment_ids: set[int] = set()
                for comment in comments:
                    if comment.id in counted_comment_ids:
                        continue
                    if comment.process_status == ProcessStatus.RESOLVED.value:
                        continue
                    counted_comment_ids.add(comment.id)
                    counts[comment.risk_level] = counts.get(comment.risk_level, 0) + 1
                    total += 1

            result.append(
                schemas.RiskDistributionItem(
                    tag_id=tag.id,
                    tag_name=tag.name,
                    low=counts[RiskLevel.LOW.value],
                    medium=counts[RiskLevel.MEDIUM.value],
                    high=counts[RiskLevel.HIGH.value],
                    critical=counts[RiskLevel.CRITICAL.value],
                    total=total,
                )
            )
        return result

    @staticmethod
    def _risk_rank(level: str) -> int:
        order = {
            RiskLevel.LOW.value: 1,
            RiskLevel.MEDIUM.value: 2,
            RiskLevel.HIGH.value: 3,
            RiskLevel.CRITICAL.value: 4,
        }
        return order.get(level, 0)

    def risk_dashboard(
        self, document_id: int, include_deprecated: bool = False
    ) -> schemas.RiskDashboard:
        doc = self.documents.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(
                "Document not found",
                details={"document_id": document_id},
            )

        all_clauses = self.clauses.list_by_document(document_id)
        if include_deprecated:
            clauses = all_clauses
        else:
            clauses = [c for c in all_clauses if not c.deprecated]

        unresolved_by_risk = {
            RiskLevel.LOW.value: 0,
            RiskLevel.MEDIUM.value: 0,
            RiskLevel.HIGH.value: 0,
            RiskLevel.CRITICAL.value: 0,
        }
        resolved_by_risk = {
            RiskLevel.LOW.value: 0,
            RiskLevel.MEDIUM.value: 0,
            RiskLevel.HIGH.value: 0,
            RiskLevel.CRITICAL.value: 0,
        }

        tagged_clause_ids: set[int] = set()
        clause_stats: list[dict] = []

        for clause in clauses:
            bindings = self.bindings.list_by_clause(clause.id)
            tag_names: list[str] = []
            if bindings:
                tagged_clause_ids.add(clause.id)
                for binding in bindings:
                    tag = self.tags.get_by_id(binding.tag_id)
                    if tag is not None:
                        tag_names.append(tag.name)

            comments = self.comments.list_by_clause(clause.id)
            unresolved_count = 0
            highest_rank = 0
            highest_level: Optional[str] = None

            for comment in comments:
                if comment.process_status in (
                    ProcessStatus.RESOLVED.value,
                    ProcessStatus.REJECTED.value,
                ):
                    resolved_by_risk[comment.risk_level] = (
                        resolved_by_risk.get(comment.risk_level, 0) + 1
                    )
                    continue
                unresolved_by_risk[comment.risk_level] = (
                    unresolved_by_risk.get(comment.risk_level, 0) + 1
                )
                unresolved_count += 1
                rank = self._risk_rank(comment.risk_level)
                if rank > highest_rank:
                    highest_rank = rank
                    highest_level = comment.risk_level

            clause_stats.append(
                {
                    "clause": clause,
                    "tag_names": tag_names,
                    "unresolved_count": unresolved_count,
                    "highest_level": highest_level,
                    "has_tags": bool(bindings),
                }
            )

        top_risk_clauses: list[schemas.TopRiskClauseItem] = []
        active_stats = [s for s in clause_stats if s["highest_level"] is not None]
        active_stats.sort(
            key=lambda s: (
                self._risk_rank(s["highest_level"]),
                s["unresolved_count"],
            ),
            reverse=True,
        )
        for stat in active_stats[:10]:
            clause = stat["clause"]
            top_risk_clauses.append(
                schemas.TopRiskClauseItem(
                    clause_id=clause.id,
                    clause_no=clause.clause_no,
                    clause_text=clause.clause_text,
                    highest_risk_level=RiskLevel(stat["highest_level"]),
                    unresolved_comment_count=stat["unresolved_count"],
                    tag_names=stat["tag_names"],
                )
            )

        high_ranks = {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value}
        untagged_high_risk: list[schemas.UntaggedHighRiskClauseItem] = []
        for stat in clause_stats:
            if (
                not stat["has_tags"]
                and stat["highest_level"] in high_ranks
                and stat["unresolved_count"] > 0
            ):
                clause = stat["clause"]
                untagged_high_risk.append(
                    schemas.UntaggedHighRiskClauseItem(
                        clause_id=clause.id,
                        clause_no=clause.clause_no,
                        clause_text=clause.clause_text,
                        highest_risk_level=RiskLevel(stat["highest_level"]),
                        unresolved_comment_count=stat["unresolved_count"],
                    )
                )

        total_unresolved = sum(unresolved_by_risk.values())
        total_resolved = sum(resolved_by_risk.values())

        return schemas.RiskDashboard(
            document_id=document_id,
            include_deprecated=include_deprecated,
            total_clauses=len(clauses),
            tagged_clause_count=len(tagged_clause_ids),
            untagged_clause_count=len(clauses) - len(tagged_clause_ids),
            unresolved_by_risk=unresolved_by_risk,
            resolved_by_risk=resolved_by_risk,
            total_unresolved=total_unresolved,
            total_resolved=total_resolved,
            top_risk_clauses=top_risk_clauses,
            untagged_high_risk_clauses=untagged_high_risk,
        )
