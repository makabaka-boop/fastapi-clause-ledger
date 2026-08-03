from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions.app_exceptions import AppException


def _error_response(error_code: str, message: str, details: dict, status_code: int):
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "details": details,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(_: Request, exc: AppException):
        return _error_response(
            exc.error_code, exc.message, exc.details, exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError):
        return _error_response(
            "validation_error",
            "Request validation failed",
            {"errors": exc.errors()},
            422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException):
        return _error_response(
            "http_error",
            str(exc.detail),
            {},
            exc.status_code,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception):
        return _error_response(
            "internal_error",
            "Internal server error",
            {"type": type(exc).__name__},
            500,
        )
