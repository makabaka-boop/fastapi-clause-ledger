from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.consistency import ConsistencyService
from app.deps import get_db

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get(
    "/check",
    response_model=schemas.ConsistencyReport,
)
def run_consistency_checks(
    db: Session = Depends(get_db),
) -> schemas.ConsistencyReport:
    service = ConsistencyService(db)
    return service.run_checks()
