from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code: int = 400
    error_code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"


class StateTransitionError(AppError):
    status_code = 409
    error_code = "invalid_state_transition"


class BusinessRuleError(AppError):
    status_code = 409
    error_code = "business_rule_violation"
