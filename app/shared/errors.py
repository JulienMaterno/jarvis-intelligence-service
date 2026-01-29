"""
Standardized error response helpers for Jarvis services.

Provides consistent error formatting across all API endpoints with
correlation ID tracking for distributed debugging.

Usage:
    from app.shared.errors import (
        ErrorResponse, ErrorCode,
        error_response, validation_error, not_found_error, internal_error
    )

    # In exception handler:
    return error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message="Invalid input",
        details={"field": "email", "reason": "invalid format"},
        correlation_id=request.state.correlation_id
    )
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel
from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode(str, Enum):
    """Standard error codes used across all Jarvis services."""

    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    BAD_REQUEST = "BAD_REQUEST"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT = "TIMEOUT"

    # Domain-specific errors
    SYNC_ERROR = "SYNC_ERROR"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class ErrorDetail(BaseModel):
    """Structured error detail model."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    correlation_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""
    error: ErrorDetail


def get_correlation_id(request: Optional[Request] = None) -> Optional[str]:
    """
    Extract correlation ID from request state.

    Args:
        request: FastAPI request object (optional)

    Returns:
        Correlation ID string or None if not available
    """
    if request is None:
        return None
    return getattr(request.state, "correlation_id", None)


def error_response(
    code: ErrorCode,
    message: str,
    status_code: int,
    details: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a standardized JSON error response.

    Args:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        status_code: HTTP status code
        details: Optional additional error details
        correlation_id: Request correlation ID for tracing

    Returns:
        JSONResponse with standardized error format
    """
    error_detail = ErrorDetail(
        code=code.value,
        message=message,
        details=details,
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": error_detail.model_dump(exclude_none=True)},
    )


def validation_error(
    message: str,
    details: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 400 validation error response.

    Args:
        message: Description of what validation failed
        details: Field-level validation errors
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 400 status
    """
    return error_response(
        code=ErrorCode.VALIDATION_ERROR,
        message=message,
        status_code=400,
        details=details,
        correlation_id=correlation_id,
    )


def not_found_error(
    message: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 404 not found error response.

    Args:
        message: Description of what was not found
        resource_type: Type of resource (e.g., "contact", "meeting")
        resource_id: ID of the missing resource
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 404 status
    """
    details = {}
    if resource_type:
        details["resource_type"] = resource_type
    if resource_id:
        details["resource_id"] = resource_id

    return error_response(
        code=ErrorCode.NOT_FOUND,
        message=message,
        status_code=404,
        details=details if details else None,
        correlation_id=correlation_id,
    )


def unauthorized_error(
    message: str = "Authentication required",
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 401 unauthorized error response.

    Args:
        message: Description of auth failure
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 401 status
    """
    return error_response(
        code=ErrorCode.UNAUTHORIZED,
        message=message,
        status_code=401,
        correlation_id=correlation_id,
    )


def forbidden_error(
    message: str = "Access denied",
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 403 forbidden error response.

    Args:
        message: Description of why access is denied
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 403 status
    """
    return error_response(
        code=ErrorCode.FORBIDDEN,
        message=message,
        status_code=403,
        correlation_id=correlation_id,
    )


def internal_error(
    message: str = "Internal server error",
    details: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 500 internal error response.

    Note: Be careful not to expose sensitive internal details to clients.

    Args:
        message: User-safe error message
        details: Safe-to-expose details only
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 500 status
    """
    return error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message=message,
        status_code=500,
        details=details,
        correlation_id=correlation_id,
    )


def service_unavailable_error(
    message: str = "Service temporarily unavailable",
    retry_after: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 503 service unavailable error response.

    Args:
        message: Description of why service is unavailable
        retry_after: Suggested retry time in seconds
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 503 status
    """
    details = {"retry_after_seconds": retry_after} if retry_after else None
    return error_response(
        code=ErrorCode.SERVICE_UNAVAILABLE,
        message=message,
        status_code=503,
        details=details,
        correlation_id=correlation_id,
    )


def external_service_error(
    service_name: str,
    message: str,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 502 bad gateway error for external service failures.

    Args:
        service_name: Name of the failing external service
        message: Description of the failure
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 502 status
    """
    return error_response(
        code=ErrorCode.EXTERNAL_SERVICE_ERROR,
        message=message,
        status_code=502,
        details={"service": service_name},
        correlation_id=correlation_id,
    )


def database_error(
    message: str = "Database operation failed",
    operation: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> JSONResponse:
    """
    Create a 500 database error response.

    Args:
        message: User-safe error message
        operation: Type of operation that failed (e.g., "insert", "query")
        correlation_id: Request correlation ID

    Returns:
        JSONResponse with 500 status
    """
    details = {"operation": operation} if operation else None
    return error_response(
        code=ErrorCode.DATABASE_ERROR,
        message=message,
        status_code=500,
        details=details,
        correlation_id=correlation_id,
    )
