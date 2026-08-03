from fastapi import APIRouter, Depends, Query

from app.api.deps import get_dashboard_service
from app.schemas.dashboard import DocumentDashboard, RiskDashboard
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDashboard,
)
def document_dashboard(
    document_id: int,
    service: DashboardService = Depends(get_dashboard_service),
):
    return service.document_dashboard(document_id)


@router.get(
    "/documents/{document_id}/risk",
    response_model=RiskDashboard,
)
def risk_dashboard(
    document_id: int,
    include_deprecated: bool = Query(False),
    service: DashboardService = Depends(get_dashboard_service),
):
    return service.risk_dashboard(
        document_id, include_deprecated=include_deprecated
    )
