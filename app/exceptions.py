"""Application exception hierarchy and FastAPI handlers.

Every error the API returns follows one fixed envelope::

    {"error_code": "...", "message": "...", "details": {...}}

``AppException`` carries the HTTP status plus that payload. The handlers wire
our own exceptions, FastAPI request-validation errors and any uncaught
exception into the same shape so clients only ever parse one format.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base class for all business/validation errors raised by the service."""

    status_code: int = 400
    error_code: str = "bad_request"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class NotFoundError(AppException):
    status_code = 404
    error_code = "not_found"


class ConflictError(AppException):
    """Uniqueness / duplicate violations (e.g. duplicate clause_no)."""

    status_code = 409
    error_code = "conflict"


class ValidationError(AppException):
    """Business-rule validation failures (distinct from schema validation)."""

    status_code = 422
    error_code = "validation_error"


class StateTransitionError(AppException):
    """Illegal process_status transition."""

    status_code = 409
    error_code = "invalid_transition"


class RuleViolationError(AppException):
    """Domain guard rails (e.g. acting on a deprecated clause)."""

    status_code = 409
    error_code = "rule_violation"


def register_exception_handlers(app) -> None:
    """Attach handlers that normalise every error to the fixed envelope."""

    @app.exception_handler(AppException)
    async def _app_exception_handler(_: Request, exc: AppException):
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError):
        # Pydantic errors carry non-JSON-serialisable objects; stringify them.
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "validation_error",
                "message": "Request payload failed validation.",
                "details": {"errors": _jsonable_errors(exc.errors())},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "internal_error",
                "message": "An unexpected error occurred.",
                "details": {"reason": str(exc)},
            },
        )


def _jsonable_errors(errors: list) -> list:
    """Strip Pydantic error entries down to JSON-safe primitives."""
    cleaned = []
    for err in errors:
        cleaned.append(
            {
                "loc": [str(part) for part in err.get("loc", [])],
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    return cleaned
