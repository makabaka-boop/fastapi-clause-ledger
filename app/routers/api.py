from fastapi import APIRouter

from app.routers import (
    clauses,
    comments,
    consistency,
    copies,
    dashboard,
    documents,
    tags,
)

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(clauses.router)
api_router.include_router(comments.router)
api_router.include_router(tags.router)
api_router.include_router(copies.router)
api_router.include_router(dashboard.router)
api_router.include_router(consistency.router)
