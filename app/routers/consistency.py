from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import ConsistencyReport
from ..services.consistency_service import ConsistencyService

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get("/checks", response_model=ConsistencyReport)
def run_consistency_checks(db: Session = Depends(get_db)):
    """台账一致性自检：按 checks 数组返回各检查项的通过状态、问题数量与明细。"""
    return ConsistencyService(db).run()
