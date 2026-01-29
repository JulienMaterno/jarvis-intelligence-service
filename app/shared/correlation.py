"""
Correlation ID middleware and utilities for distributed request tracing.

Provides middleware that generates or propagates correlation IDs across
service boundaries, enabling end-to-end request tracing.

Usage:
    from app.shared.correlation import CorrelationMiddleware, get_correlation_id

    # In main.py:
    app.add_middleware(CorrelationMiddleware)

    # In any code:
    correlation_id = get_correlation_id()

The correlation ID is:
- Read from X-Correlation-ID or X-Request-ID header if present
- Generated as a new UUID if not present
- Stored in request.state.correlation_id for endpoint access
- Added to response headers for client debugging
- Made available via get_correlation_id() for logging
"""

import uuid
import contextvars
from typing import Optional, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# Context variable to store correlation ID for the current request
# This allows access to the correlation ID from anywhere in the code
_correlation_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id",
    default=None,
)


# Header names for correlation ID (check multiple for compatibility)
CORRELATION_HEADERS = [
    "X-Correlation-ID",
    "X-Request-ID",
    "X-Trace-ID",
]

# Response header name
RESPONSE_HEADER = "X-Correlation-ID"


def get_correlation_id() -> Optional[str]:
    """
    Get the correlation ID for the current request context.

    This can be called from anywhere in the code during request processing
    to get the current request's correlation ID for logging or propagation.

    Returns:
        The correlation ID string, or None if not in a request context
    """
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current context.

    This is typically called by middleware, but can also be used in
    background tasks or other contexts where a correlation ID needs
    to be established.

    Args:
        correlation_id: The correlation ID to set
    """
    _correlation_id_ctx.set(correlation_id)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID.

    Uses UUID4 truncated to 8 characters for brevity while maintaining
    sufficient uniqueness for debugging purposes.

    Returns:
        A new correlation ID string
    """
    return str(uuid.uuid4())[:8]


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle correlation IDs for request tracing.

    For each incoming request:
    1. Checks for existing correlation ID in headers
    2. Generates a new one if not present
    3. Stores it in request.state and context variable
    4. Adds it to response headers

    This enables distributed tracing across service calls.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Process request and handle correlation ID.

        Args:
            request: The incoming request
            call_next: The next middleware/endpoint in the chain

        Returns:
            The response with correlation ID header added
        """
        # Try to get existing correlation ID from headers
        correlation_id = None
        for header in CORRELATION_HEADERS:
            correlation_id = request.headers.get(header)
            if correlation_id:
                break

        # Generate new ID if not found
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Store in request state for endpoint access
        request.state.correlation_id = correlation_id

        # Store in context variable for logging access
        token = _correlation_id_ctx.set(correlation_id)

        try:
            # Process the request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[RESPONSE_HEADER] = correlation_id

            return response
        finally:
            # Reset context variable
            _correlation_id_ctx.reset(token)


def propagate_correlation_headers(
    headers: Optional[dict] = None,
    correlation_id: Optional[str] = None,
) -> dict:
    """
    Build headers dict with correlation ID for outgoing requests.

    Use this when making HTTP calls to other services to propagate
    the correlation ID for distributed tracing.

    Args:
        headers: Existing headers dict to add to (optional)
        correlation_id: Specific correlation ID to use (optional).
                       If not provided, uses current context's ID.

    Returns:
        Headers dict with X-Correlation-ID added

    Example:
        async with httpx.AsyncClient() as client:
            headers = propagate_correlation_headers()
            response = await client.get(url, headers=headers)
    """
    if headers is None:
        headers = {}
    else:
        headers = dict(headers)  # Don't modify original

    # Get correlation ID
    cid = correlation_id or get_correlation_id()
    if cid:
        headers[RESPONSE_HEADER] = cid

    return headers


class CorrelationContext:
    """
    Context manager for setting correlation ID in non-request contexts.

    Useful for background tasks, scheduled jobs, or tests where there's
    no HTTP request to provide the correlation ID.

    Example:
        with CorrelationContext("background-task-123"):
            logger.info("Processing batch")  # Will include correlation_id
            do_work()
    """

    def __init__(self, correlation_id: Optional[str] = None):
        """
        Initialize the context.

        Args:
            correlation_id: The correlation ID to use. If not provided,
                          a new one will be generated.
        """
        self.correlation_id = correlation_id or generate_correlation_id()
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> str:
        """Set the correlation ID and return it."""
        self._token = _correlation_id_ctx.set(self.correlation_id)
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Reset the correlation ID context."""
        if self._token is not None:
            _correlation_id_ctx.reset(self._token)


async def async_correlation_context(
    correlation_id: Optional[str] = None,
):
    """
    Async context manager for setting correlation ID.

    Same as CorrelationContext but as an async context manager.

    Example:
        async with async_correlation_context("job-456"):
            await process_batch()
    """
    cid = correlation_id or generate_correlation_id()
    token = _correlation_id_ctx.set(cid)
    try:
        yield cid
    finally:
        _correlation_id_ctx.reset(token)
