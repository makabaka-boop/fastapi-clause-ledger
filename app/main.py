from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from .database import init_db
from .exceptions import AppError
from .routers import clauses, consistency, documents, reviews, tags


def create_app() -> FastAPI:
    app = FastAPI(title="Clause Ledger API", version="1.0.0")
    init_db()

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_error",
                "message": "请求参数校验失败",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(clauses.router, prefix="/api/v1")
    app.include_router(reviews.router, prefix="/api/v1")
    app.include_router(tags.router, prefix="/api/v1")
    app.include_router(consistency.router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return app


app = create_app()
