import json
from typing import List, Optional

from sqlalchemy.orm import Session

from ..exceptions import NotFoundError
from ..models import CopyItem, DocumentCopyMapping
from ..repositories.clauses import ClauseRepository
from ..repositories.copies import CopyMappingRepository
from ..repositories.documents import DocumentRepository
from ..repositories.reviews import ReviewRepository
from ..repositories.tags import TagRepository
from ..schemas import (
    ClauseCopyMappingItem,
    ClauseCreate,
    CopyClauseDetail,
    CopyDetailsOut,
    CopyResultOut,
    CopySkippedItem,
    DocumentCopyCreate,
    RiskTagOut,
)
from .document_service import DocumentService


class CopyService:
    """复制文档版本：只复制未废弃条款及其风险标签绑定与未解决意见；
    已废弃条款与已解决（resolved）意见不复制，并记录逐条明细。

    标签语义沿用首轮定义：风险标签绑定在条款上，表示条款的风险分类，
    与意见的处理状态无关，复制时随条款一起继承。
    """

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.clause_repo = ClauseRepository(db)
        self.review_repo = ReviewRepository(db)
        self.tag_repo = TagRepository(db)
        self.mapping_repo = CopyMappingRepository(db)
        self.doc_service = DocumentService(db)

    def copy_document(self, document_id: int, data: DocumentCopyCreate) -> CopyResultOut:
        source = self.doc_service.get_or_404(document_id)
        target = self.doc_repo.create(
            title=data.title or f"{source.title} (copy)",
            source_department=source.source_department,
            version_no=data.version_no,
        )
        mapping = self.mapping_repo.create(
            source_document_id=source.id, target_document_id=target.id
        )

        clause_mappings: List[ClauseCopyMappingItem] = []
        copied_reviews = 0
        copied_tags = 0
        skipped_deprecated = 0
        skipped_resolved = 0

        for clause in self.clause_repo.list_by_document(source.id):
            if clause.deprecated:
                skipped_deprecated += 1
                self.mapping_repo.add_item(
                    mapping.id,
                    item_type="clause",
                    action="skipped",
                    source_clause_id=clause.id,
                    clause_no=clause.clause_no,
                    reason="deprecated_clause",
                )
                continue

            new_clause = self.clause_repo.create(
                target.id,
                ClauseCreate(
                    clause_no=clause.clause_no,
                    clause_text=clause.clause_text,
                    clause_type=clause.clause_type,
                    importance=clause.importance,
                ),
            )

            # 复制风险标签绑定（条款级风险分类，随条款继承）
            bindings = self.tag_repo.list_bindings_for_clause(clause.id)
            tag_ids = [b.tag_id for b in bindings]
            for tag_id in tag_ids:
                self.tag_repo.bind(new_clause.id, tag_id)
                copied_tags += 1

            # 复制未解决意见；resolved 意见不复制并记录原因
            for review in self.review_repo.list_by_clause(clause.id):
                if review.process_status == "resolved":
                    skipped_resolved += 1
                    self.mapping_repo.add_item(
                        mapping.id,
                        item_type="review",
                        action="skipped",
                        source_clause_id=clause.id,
                        target_clause_id=new_clause.id,
                        source_review_id=review.id,
                        clause_no=clause.clause_no,
                        reason="resolved_review",
                    )
                    continue
                new_review = self.review_repo.create(
                    new_clause.id, review.reviewer_name, review.comment_text, review.risk_level
                )
                self.review_repo.update_status(new_review, review.process_status)
                copied_reviews += 1

            self.mapping_repo.add_item(
                mapping.id,
                item_type="clause",
                action="copied",
                source_clause_id=clause.id,
                target_clause_id=new_clause.id,
                clause_no=clause.clause_no,
                inherited_tag_ids=json.dumps(tag_ids),
            )
            clause_mappings.append(
                ClauseCopyMappingItem(
                    source_clause_id=clause.id,
                    target_clause_id=new_clause.id,
                    source_clause_no=clause.clause_no,
                    target_clause_no=new_clause.clause_no,
                    inherited_tag_ids=tag_ids,
                )
            )

        mapping.copied_clause_count = len(clause_mappings)
        mapping.skipped_deprecated_clause_count = skipped_deprecated
        mapping.copied_review_count = copied_reviews
        mapping.skipped_resolved_review_count = skipped_resolved
        mapping.copied_tag_binding_count = copied_tags
        self.db.flush()
        self.db.commit()

        return CopyResultOut(
            source_document_id=source.id,
            target_document_id=target.id,
            clause_mappings=clause_mappings,
            copied_clause_count=len(clause_mappings),
            copied_review_count=copied_reviews,
            copied_tag_count=copied_tags,
            skipped_deprecated_count=skipped_deprecated,
            skipped_resolved_comment_count=skipped_resolved,
        )

    def copy_details(self, target_document_id: int) -> CopyDetailsOut:
        """按目标文档查看复制详情：每个新条款对应的原条款、
        继承的风险标签与未复制原因摘要。"""
        self.doc_service.get_or_404(target_document_id)
        mapping = self.mapping_repo.get_by_target_document(target_document_id)
        if mapping is None:
            raise NotFoundError(
                f"文档 {target_document_id} 不是复制产生的目标文档",
                {"target_document_id": target_document_id},
            )
        items = self.mapping_repo.list_items(mapping.id)

        clauses: List[CopyClauseDetail] = []
        skipped_by_target: dict = {}
        skipped_clauses: List[CopySkippedItem] = []

        for item in items:
            if item.action == "skipped":
                skipped = self._to_skipped(item)
                if item.item_type == "clause":
                    skipped_clauses.append(skipped)
                else:
                    skipped_by_target.setdefault(item.target_clause_id, []).append(skipped)
                continue
            tag_ids = json.loads(item.inherited_tag_ids or "[]")
            clauses.append(
                CopyClauseDetail(
                    target_clause_id=item.target_clause_id,
                    target_clause_no=item.clause_no,
                    source_clause_id=item.source_clause_id,
                    source_clause_no=item.clause_no,
                    inherited_tags=self._tags_by_ids(tag_ids),
                    skipped_items=skipped_by_target.get(item.target_clause_id, []),
                )
            )

        return CopyDetailsOut(
            source_document_id=mapping.source_document_id,
            target_document_id=mapping.target_document_id,
            clauses=clauses,
            skipped_clauses=skipped_clauses,
        )

    @staticmethod
    def _to_skipped(item: CopyItem) -> CopySkippedItem:
        return CopySkippedItem(
            item_type=item.item_type,
            source_clause_id=item.source_clause_id,
            clause_no=item.clause_no,
            source_review_id=item.source_review_id,
            reason=item.reason,
        )

    def _tags_by_ids(self, tag_ids: List[int]) -> List[RiskTagOut]:
        tags = []
        for tag_id in tag_ids:
            tag = self.tag_repo.get(tag_id)
            if tag is not None:
                tags.append(RiskTagOut.model_validate(tag))
        return tags

    def list_mappings(self, document_id: Optional[int] = None) -> List[DocumentCopyMapping]:
        return self.mapping_repo.list_all(document_id)
