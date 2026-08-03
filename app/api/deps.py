from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.comment_service import CommentService
from app.services.clause_service import ClauseService
from app.services.consistency_service import ConsistencyService
from app.services.copy_service import CopyService
from app.services.dashboard_service import DashboardService
from app.services.document_service import DocumentService
from app.services.process_service import ProcessService
from app.services.tag_service import TagService


def get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    return DocumentService(db)


def get_clause_service(db: Session = Depends(get_db)) -> ClauseService:
    return ClauseService(db)


def get_comment_service(db: Session = Depends(get_db)) -> CommentService:
    return CommentService(db)


def get_tag_service(db: Session = Depends(get_db)) -> TagService:
    return TagService(db)


def get_process_service(db: Session = Depends(get_db)) -> ProcessService:
    return ProcessService(db)


def get_copy_service(db: Session = Depends(get_db)) -> CopyService:
    return CopyService(db)


def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return DashboardService(db)


def get_consistency_service(db: Session = Depends(get_db)) -> ConsistencyService:
    return ConsistencyService(db)
