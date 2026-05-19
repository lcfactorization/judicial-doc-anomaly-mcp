"""Structured error codes for judicial-lint-mcp v0.5.1.

Provides consistent error responses with error codes, retryable flags, and details.
"""

from enum import Enum


class ErrorCode(str, Enum):
    SKILL_NOT_FOUND = "SKILL_404"
    PIPELINE_NOT_FOUND = "PIPELINE_404"
    SESSION_NOT_FOUND = "SESSION_404"
    TOKEN_OVERFLOW = "TOKEN_500"
    PARSE_FAILED = "PARSE_400"
    INVALID_PARAMS = "PARAM_400"
    RENDER_FAILED = "RENDER_500"
    STATE_ERROR = "STATE_500"
    INTERNAL_ERROR = "INTERNAL_500"


_RETRYABLE_CODES = {
    ErrorCode.TOKEN_OVERFLOW,
    ErrorCode.RENDER_FAILED,
    ErrorCode.STATE_ERROR,
}


def make_error(
    code: ErrorCode,
    message: str,
    details: dict | None = None,
) -> str:
    import json

    error_obj = {
        "code": code.value,
        "message": message,
        "retryable": code in _RETRYABLE_CODES,
    }
    if details:
        error_obj["details"] = details
    return json.dumps({"success": False, "error": error_obj}, ensure_ascii=False, indent=2)
