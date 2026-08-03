from fastapi import APIRouter

from app.api.v1 import (
    comments,
    consistency,
    copy,
    clauses,
    dashboard,
    documents,
    health,
    process,
    tags,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(clauses.router)
api_router.include_router(comments.router)
api_router.include_router(tags.router)
api_router.include_router(process.router)
api_router.include_router(copy.router)
api_router.include_router(dashboard.router)
api_router.include_router(consistency.router)
