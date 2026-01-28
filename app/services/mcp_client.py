"""
MCP Client - HTTP client for jarvis-mcp-server.

This module provides a unified interface to call the MCP server's tools.
It allows the intelligence-service to delegate database operations to the
MCP server, providing a single source of truth for tool implementations.

Architecture:
- Claude Desktop → jarvis-mcp-server (stdio) → DB
- Intelligence Service → this client → jarvis-mcp-server (HTTP) → DB

Usage:
    from app.services.mcp_client import mcp_client

    # Execute a tool
    result = await mcp_client.execute_tool("contacts_search", {"query": "John"})

    # Get available tools
    tools = await mcp_client.list_tools()
"""
from app.core.logging_utils import sanitize_for_logging

import os
import logging
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("Jarvis.MCP.Client")

# MCP Server URL (Cloud Run deployed)
MCP_SERVER_URL = os.getenv(
    "MCP_SERVER_URL",
    "https://jarvis-mcp-server-776871804948.asia-southeast1.run.app"
)

# MCP API key for authenticating with the MCP server
MCP_API_KEY = os.getenv("MCP_API_KEY", "")


class MCPClient:
    """HTTP client for jarvis-mcp-server."""

    def __init__(self, base_url: str = MCP_SERVER_URL, timeout: float = 30.0):
        """Initialize the MCP client.

        Args:
            base_url: Base URL of the MCP server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Content-Type": "application/json",
                "X-Client-Name": "jarvis-intelligence-service",
            }
            if MCP_API_KEY:
                headers["X-API-Key"] = MCP_API_KEY
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> Dict[str, Any]:
        """Check MCP server health.

        Returns:
            Health status dict with server info
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"MCP health check failed: {e}")
            return {"status": "error", "error": str(e)}

    async def list_tools(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """List available tools from MCP server.

        Args:
            refresh: Force refresh cache

        Returns:
            List of tool definitions
        """
        # Check cache
        if not refresh and self._tools_cache and self._cache_time:
            age = (datetime.now() - self._cache_time).total_seconds()
            if age < self._cache_ttl:
                return self._tools_cache

        try:
            client = await self._get_client()
            response = await client.get("/tools/definitions")
            response.raise_for_status()
            data = response.json()
            self._tools_cache = data.get("tools", [])
            self._cache_time = datetime.now()
            logger.debug(f"Loaded {len(self._tools_cache)} tools from MCP server")
            return self._tools_cache
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}")
            return self._tools_cache or []

    async def execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool via the MCP server.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Tool parameters

        Returns:
            Tool result dict with structure:
            - ok: bool - whether the call succeeded
            - data: Any - the result data (if ok=True)
            - error: dict - error info (if ok=False)
            - meta: dict - metadata (timing, etc.)
        """
        start_time = datetime.now()

        try:
            client = await self._get_client()
            response = await client.post(
                "/api/tool",
                json={
                    "tool": tool_name,
                    "input": tool_input,
                }
            )

            result = response.json()
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000

            if result.get("ok"):
                logger.debug(f"MCP tool {tool_name} succeeded in {duration_ms:.0f}ms")
            else:
                error = result.get("error", {})
                logger.warning(
                    f"MCP tool {tool_name} failed: {error.get('type')} - {error.get('message')}"
                )

            return result

        except httpx.TimeoutException:
            logger.error(f"MCP tool {tool_name} timed out after {self.timeout}s")
            return {
                "ok": False,
                "error": {
                    "type": "TIMEOUT",
                    "message": f"Tool execution timed out after {self.timeout}s"
                }
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"MCP tool {tool_name} HTTP error: {e.response.status_code}")
            return {
                "ok": False,
                "error": {
                    "type": "HTTP_ERROR",
                    "message": f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                }
            }
        except Exception as e:
            logger.error(f"MCP tool {tool_name} error: {e}")
            return {
                "ok": False,
                "error": {
                    "type": "CLIENT_ERROR",
                    "message": str(e)
                }
            }

    # ==================== Convenience Methods ====================
    # These map to specific MCP tools for cleaner code

    async def search_contacts(
        self,
        query: Optional[str] = None,
        company: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search contacts via MCP."""
        return await self.execute_tool("contacts_search", {
            "query": query,
            "company": company,
            "limit": limit,
        })

    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get a contact by ID via MCP."""
        return await self.execute_tool("contacts_get", {"id": contact_id})

    async def search_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search tasks via MCP."""
        return await self.execute_tool("tasks_search", {
            "status": status,
            "priority": priority,
            "limit": limit,
        })

    async def search_meetings(
        self,
        query: Optional[str] = None,
        contact_name: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search meetings via MCP."""
        return await self.execute_tool("meetings_search", {
            "query": query,
            "contact_name": contact_name,
            "limit": limit,
        })

    async def search_reflections(
        self,
        query: Optional[str] = None,
        topic: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search reflections via MCP."""
        return await self.execute_tool("reflections_search", {
            "query": query,
            "topic": topic,
            "limit": limit,
        })

    async def query_database(self, sql: str) -> Dict[str, Any]:
        """Execute a read-only SQL query via MCP."""
        return await self.execute_tool("query", {"sql": sql})

    async def write_preview(
        self,
        operation: str,
        table: str,
        data: Dict[str, Any],
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Preview a write operation via MCP."""
        return await self.execute_tool("write_preview", {
            "operation": operation,
            "table": table,
            "data": data,
            "where": where,
        })

    async def write_execute(self, token: str) -> Dict[str, Any]:
        """Execute a previously previewed write operation via MCP."""
        return await self.execute_tool("write_execute", {"token": token})

    async def semantic_search(
        self,
        query: str,
        tables: Optional[List[str]] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Semantic search across tables via MCP."""
        return await self.execute_tool("search", {
            "query": query,
            "tables": tables,
            "limit": limit,
        })


# Global client instance
mcp_client = MCPClient()


# ==================== Tool Mapping ====================
# Maps intelligence-service tool names to MCP tool names
# This allows gradual migration without breaking existing code

MCP_TOOL_MAPPING = {
    # Contacts
    "search_contacts": "contacts_search",
    "get_contact_history": "contacts_get",  # May need adjustment
    "create_contact": "contacts_create",
    "update_contact": "contacts_update",

    # Tasks
    "get_tasks": "tasks_search",
    "create_task": "tasks_create",
    "update_task": "tasks_update",
    "complete_task": "tasks_complete",

    # Meetings
    "get_meetings": "meetings_search",
    "create_meeting": "meetings_create",

    # Reflections
    "get_reflections": "reflections_search",
    "create_reflection": "reflections_create",

    # Journals
    "get_journals": "journals_search",
    "create_journal": "journals_create",

    # Calendar
    "get_upcoming_events": "calendar_search",

    # Generic
    "query_database": "query",
    "query_knowledge": "search",  # Semantic search
}


async def execute_via_mcp(tool_name: str, tool_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Try to execute a tool via MCP if it's mapped.

    Args:
        tool_name: Intelligence-service tool name
        tool_input: Tool parameters

    Returns:
        MCP result if tool is mapped, None if not mapped
    """
    mcp_tool = MCP_TOOL_MAPPING.get(tool_name)
    if not mcp_tool:
        return None

    result = await mcp_client.execute_tool(mcp_tool, tool_input)

    # Convert MCP result format to intelligence-service format
    if result.get("ok"):
        return {
            "success": True,
            "data": result.get("data"),
            "source": "mcp",
        }
    else:
        error = result.get("error", {})
        return {
            "success": False,
            "error": error.get("message", "Unknown MCP error"),
            "source": "mcp",
        }
