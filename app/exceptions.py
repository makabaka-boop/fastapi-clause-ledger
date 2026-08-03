"""统一业务异常定义。所有异常最终渲染为
{"error_code": "...", "message": "...", "details": {...}}
"""

from typing import Any, Dict, Optional


class AppError(Exception):
    error_code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    error_code = "not_found"
    http_status = 404


class ValidationError(AppError):
    error_code = "validation_error"
    http_status = 422


class ConflictError(AppError):
    error_code = "conflict"
    http_status = 409


class DuplicateClauseNoError(ConflictError):
    error_code = "duplicate_clause_no"


class ClauseDeprecatedError(ConflictError):
    error_code = "clause_deprecated"


class InvalidStatusTransitionError(ConflictError):
    error_code = "invalid_status_transition"


class InvalidImportModeError(ValidationError):
    error_code = "invalid_import_mode"


class DuplicateBindingError(ConflictError):
    error_code = "duplicate_tag_binding"
