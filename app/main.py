"""FastAPI application factory and entrypoint.

Run with::

    python -m app.main
    # or
    uvicorn app.main:app --host 0.0.0.0 --port 18103
"""

from fastapi import FastAPI

from . import config
from .database import init_db
from .exceptions import register_exception_handlers
from .routers import (
    clauses_router,
    documents_router,
    reports_router,
    reviews_router,
    tags_router,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Compliance Clause-Review Ledger",
        version="1.0.0",
        description=(
            "Structured service for compliance clause reviews: documents, "
            "clauses, review comments, risk tags, handling records, version "
            "copies and risk dashboards."
        ),
    )

    # Ensure the schema exists before the first request is served.
    init_db()

    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    for router in (documents_router, clauses_router, reviews_router,
                   tags_router, reports_router):
        app.include_router(router, prefix=config.API_PREFIX)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT)
