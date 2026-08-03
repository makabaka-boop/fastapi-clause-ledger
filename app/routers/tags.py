from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

router = APIRouter(prefix="/risk-tags", tags=["risk-tags"])


@router.post(
    "",
    response_model=schemas.RiskTagOut,
    status_code=status.HTTP_201_CREATED,
)
def create_risk_tag(
    payload: schemas.RiskTagCreate,
    db: Session = Depends(get_db),
) -> schemas.RiskTagOut:
    service = services.RiskTagService(db)
    tag = service.create_tag(payload)
    return schemas.RiskTagOut.model_validate(tag)


@router.get(
    "",
    response_model=list[schemas.RiskTagOut],
)
def list_risk_tags(
    db: Session = Depends(get_db),
) -> list[schemas.RiskTagOut]:
    service = services.RiskTagService(db)
    tags = service.list_tags()
    return [schemas.RiskTagOut.model_validate(t) for t in tags]


@router.post(
    "/clauses/{clause_id}/bindings",
    response_model=schemas.TagBindingOut,
    status_code=status.HTTP_201_CREATED,
)
def bind_tag_to_clause(
    clause_id: int,
    payload: schemas.TagBindRequest,
    db: Session = Depends(get_db),
) -> schemas.TagBindingOut:
    service = services.CommentService(db)
    binding = service.bind_tag(clause_id, payload)
    return schemas.TagBindingOut.model_validate(binding)


@router.get(
    "/clauses/{clause_id}/bindings",
    response_model=list[schemas.TagBindingOut],
)
def list_bindings_for_clause(
    clause_id: int,
    db: Session = Depends(get_db),
) -> list[schemas.TagBindingOut]:
    service = services.CommentService(db)
    bindings = service.list_tags_for_clause(clause_id)
    return [schemas.TagBindingOut.model_validate(b) for b in bindings]
