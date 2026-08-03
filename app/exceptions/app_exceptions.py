from typing import Any, Dict, Optional


class AppException(Exception):
    error_code: str = "internal_error"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        self.message = message
        self.details = details or {}
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    error_code = "not_found"
    status_code = 404


class ValidationConflictError(AppException):
    error_code = "validation_conflict"
    status_code = 409


class InvalidStateTransitionError(AppException):
    error_code = "invalid_state_transition"
    status_code = 409


class BusinessRuleError(AppException):
    error_code = "business_rule_violation"
    status_code = 422


class DuplicateError(AppException):
    error_code = "duplicate"
    status_code = 409
