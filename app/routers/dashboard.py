from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/documents/{document_id}",
    response_model=schemas.DashboardSummary,
)
def document_dashboard(
    document_id: int,
    db: Session = Depends(get_db),
) -> schemas.DashboardSummary:
    service = services.DashboardService(db)
    return service.document_dashboard(document_id)


@router.get(
    "/documents/{document_id}/risk",
    response_model=schemas.RiskDashboard,
)
def risk_dashboard(
    document_id: int,
    include_deprecated: bool = Query(
        False,
        description="When true, include deprecated clauses in the dashboard",
    ),
    db: Session = Depends(get_db),
) -> schemas.RiskDashboard:
    service = services.DashboardService(db)
    return service.risk_dashboard(document_id, include_deprecated=include_deprecated)


@router.get(
    "/risk-distribution",
    response_model=list[schemas.RiskDistributionItem],
)
def risk_distribution_by_tag(
    db: Session = Depends(get_db),
) -> list[schemas.RiskDistributionItem]:
    service = services.DashboardService(db)
    return service.risk_distribution_by_tag()
