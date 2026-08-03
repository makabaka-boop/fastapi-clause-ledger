from typing import List

from fastapi import APIRouter, Depends, status

from app.api.deps import get_process_service
from app.schemas.process_record import ProcessRecordCreate, ProcessRecordOut
from app.services.process_service import ProcessService

router = APIRouter(prefix="/comments", tags=["process"])


@router.post(
    "/{comment_id}/process-records",
    response_model=ProcessRecordOut,
    status_code=status.HTTP_201_CREATED,
)
def add_process_record(
    comment_id: int,
    payload: ProcessRecordCreate,
    service: ProcessService = Depends(get_process_service),
):
    return service.add_record(comment_id, payload)


@router.get(
    "/{comment_id}/process-records",
    response_model=List[ProcessRecordOut],
)
def list_process_history(
    comment_id: int,
    service: ProcessService = Depends(get_process_service),
):
    return service.list_history(comment_id)
