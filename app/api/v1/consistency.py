from fastapi import APIRouter, Depends

from app.api.deps import get_consistency_service
from app.schemas.consistency import ConsistencyReport
from app.services.consistency_service import ConsistencyService

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.get("/check", response_model=ConsistencyReport)
def run_consistency_checks(
    service: ConsistencyService = Depends(get_consistency_service),
):
    return service.run_all_checks()
