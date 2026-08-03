from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        service=settings.APP_NAME,
        timestamp=datetime.now(timezone.utc),
    )
