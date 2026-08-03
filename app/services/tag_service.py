from typing import List

from sqlalchemy.orm import Session

from ..constants import RISK_LEVELS
from ..exceptions import ConflictError, DuplicateBindingError, NotFoundError
from ..models import ClauseTagBinding, RiskTag
from ..repositories.tags import TagRepository
from ..schemas import RiskTagCreate, TagRiskDistributionItem
from .clause_service import ClauseService


class TagService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TagRepository(db)
        self.clause_service = ClauseService(db)

    def get_or_404(self, tag_id: int) -> RiskTag:
        tag = self.repo.get(tag_id)
        if tag is None:
            raise NotFoundError(f"风险标签不存在: {tag_id}", {"tag_id": tag_id})
        return tag

    def create_tag(self, data: RiskTagCreate) -> RiskTag:
        if self.repo.get_by_name(data.tag_name):
            raise ConflictError(
                f"标签名称已存在: {data.tag_name}", {"tag_name": data.tag_name}
            )
        tag = self.repo.create(data.tag_name, data.description)
        self.db.commit()
        return tag

    def bind_tag(self, clause_id: int, tag_id: int) -> ClauseTagBinding:
        clause = self.clause_service.get_or_404(clause_id)
        self.clause_service.ensure_not_deprecated(clause)
        self.get_or_404(tag_id)
        if self.repo.get_binding(clause_id, tag_id):
            raise DuplicateBindingError(
                "该条款已绑定此标签", {"clause_id": clause_id, "tag_id": tag_id}
            )
        binding = self.repo.bind(clause_id, tag_id)
        self.db.commit()
        return binding

    def risk_distribution(self, tag_id: int) -> List[TagRiskDistributionItem]:
        self.get_or_404(tag_id)
        rows = self.repo.risk_distribution(tag_id)
        agg = {}
        for row in rows:
            item = agg.setdefault(row["risk_level"], {"open": 0, "total": 0})
            item["total"] += row["count"]
            if row["process_status"] == "open":
                item["open"] += row["count"]
        return [
            TagRiskDistributionItem(
                risk_level=level,
                open_count=agg.get(level, {}).get("open", 0),
                total_count=agg.get(level, {}).get("total", 0),
            )
            for level in RISK_LEVELS
        ]
