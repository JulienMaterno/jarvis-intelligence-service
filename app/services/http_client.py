"""
Shared HTTP Client Manager with Connection Pooling.

Provides a centralized, pooled httpx.AsyncClient for efficient HTTP connections
across the intelligence service. Creating a new AsyncClient for each request is
inefficient and wastes resources on connection setup/teardown.

This module provides:
- A singleton client manager with connection pooling
- Configurable connection limits
- Proper lifecycle management (startup/shutdown)
- Support for different client configurations (default, with auth headers, etc.)

Usage:
    from app.services.http_client import http_client_manager

    # Get the default shared client
    client = await http_client_manager.get_client()
    response = await client.get("https://api.example.com/endpoint")

    # Or use the context manager for one-off requests with custom config
    async with http_client_manager.get_client_context(timeout=60.0) as client:
        response = await client.get("https://slow-api.example.com")

Lifecycle:
    # In main.py lifespan
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await http_client_manager.startup()
        yield
        await http_client_manager.shutdown()
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger("Jarvis.HTTP.Client")


class HTTPClientManager:
    """
    Manages shared httpx.AsyncClient instances with connection pooling.

    Features:
    - Connection pooling for efficient resource usage
    - Configurable limits (max connections, keepalive connections)
    - Singleton pattern for shared client access
    - Proper cleanup on shutdown

    Configuration:
    - max_connections: Maximum total connections (default: 100)
    - max_keepalive_connections: Max idle connections to keep (default: 20)
    - default_timeout: Default request timeout in seconds (default: 30.0)
    """

    def __init__(
        self,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        default_timeout: float = 30.0,
    ):
        """
        Initialize the HTTP client manager.

        Args:
            max_connections: Maximum number of concurrent connections
            max_keepalive_connections: Maximum number of idle keepalive connections
            default_timeout: Default timeout for requests in seconds
        """
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._default_timeout = default_timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    @property
    def limits(self) -> httpx.Limits:
        """Get the connection limits configuration."""
        return httpx.Limits(
            max_connections=self._max_connections,
            max_keepalive_connections=self._max_keepalive_connections,
        )

    async def startup(self) -> None:
        """
        Initialize the shared HTTP client.

        Should be called during application startup.
        Creates the pooled AsyncClient with configured limits.
        """
        if self._initialized:
            logger.warning("HTTP client manager already initialized")
            return

        self._client = httpx.AsyncClient(
            limits=self.limits,
            timeout=httpx.Timeout(self._default_timeout),
            follow_redirects=True,
        )
        self._initialized = True
        logger.info(
            f"HTTP client manager initialized "
            f"(max_connections={self._max_connections}, "
            f"max_keepalive={self._max_keepalive_connections})"
        )

    async def shutdown(self) -> None:
        """
        Close the shared HTTP client and release all connections.

        Should be called during application shutdown.
        Ensures all connections are properly closed.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._initialized = False
            logger.info("HTTP client manager shut down")

    async def get_client(self) -> httpx.AsyncClient:
        """
        Get the shared HTTP client.

        Returns the singleton pooled client. If not initialized,
        initializes it automatically (though explicit startup is preferred).

        Returns:
            The shared httpx.AsyncClient instance
        """
        if self._client is None or not self._initialized:
            logger.warning(
                "HTTP client accessed before startup - initializing now. "
                "Consider calling startup() during app initialization."
            )
            await self.startup()
        return self._client

    @asynccontextmanager
    async def get_client_context(
        self,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
    ):
        """
        Get a context-managed client with custom configuration.

        Use this for requests that need different timeout or headers
        than the default shared client. This creates a new client
        that still uses the same connection pool limits.

        Args:
            timeout: Custom timeout in seconds (default: use manager default)
            headers: Custom headers to include in all requests
            base_url: Base URL for the client

        Yields:
            httpx.AsyncClient configured with the specified options

        Example:
            async with http_client_manager.get_client_context(
                timeout=60.0,
                headers={"Authorization": "Bearer token"}
            ) as client:
                response = await client.get("/endpoint")
        """
        client_kwargs: Dict[str, Any] = {
            "limits": self.limits,
            "timeout": httpx.Timeout(timeout or self._default_timeout),
            "follow_redirects": True,
        }

        if headers:
            client_kwargs["headers"] = headers
        if base_url:
            client_kwargs["base_url"] = base_url

        async with httpx.AsyncClient(**client_kwargs) as client:
            yield client

    def create_client(
        self,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        base_url: Optional[str] = None,
    ) -> httpx.AsyncClient:
        """
        Create a new client with custom configuration (not managed).

        Use this when you need a client with specific configuration
        that you'll manage yourself (including cleanup).

        IMPORTANT: The caller is responsible for closing this client!

        Args:
            timeout: Custom timeout in seconds
            headers: Custom headers to include
            base_url: Base URL for the client

        Returns:
            A new httpx.AsyncClient (caller must close it)
        """
        client_kwargs: Dict[str, Any] = {
            "limits": self.limits,
            "timeout": httpx.Timeout(timeout or self._default_timeout),
            "follow_redirects": True,
        }

        if headers:
            client_kwargs["headers"] = headers
        if base_url:
            client_kwargs["base_url"] = base_url

        return httpx.AsyncClient(**client_kwargs)

    @property
    def is_initialized(self) -> bool:
        """Check if the client manager has been initialized."""
        return self._initialized


# Global singleton instance
http_client_manager = HTTPClientManager(
    max_connections=100,
    max_keepalive_connections=20,
    default_timeout=30.0,
)


# Convenience function for getting the shared client
async def get_http_client() -> httpx.AsyncClient:
    """
    Get the shared HTTP client.

    Convenience function that returns the shared pooled client.
    Equivalent to: await http_client_manager.get_client()

    Returns:
        The shared httpx.AsyncClient instance
    """
    return await http_client_manager.get_client()
