"""
Base utilities and shared imports for chat tools.

This module contains common imports, constants, and helper functions
used across all tool modules.
"""

import logging
import os
import asyncio
import concurrent.futures
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase

logger = logging.getLogger("Jarvis.Chat.Tools")


# =============================================================================
# MCP DELEGATION CONFIGURATION
# =============================================================================

USE_MCP_DELEGATION = os.getenv("USE_MCP_DELEGATION", "false").lower() == "true"

# Lazy import MCP client to avoid circular imports
_mcp_client = None


def _get_mcp_client():
    """Lazy load the MCP client."""
    global _mcp_client
    if _mcp_client is None and USE_MCP_DELEGATION:
        try:
            from app.services.mcp_client import mcp_client
            _mcp_client = mcp_client
            logger.info("MCP delegation enabled - tools will use jarvis-mcp-server")
        except ImportError as e:
            logger.warning(f"MCP client not available: {e}")
    return _mcp_client


# Tool name mapping: intelligence-service name -> MCP tool name
MCP_DELEGATED_TOOLS = {
    # Contacts
    "search_contacts": "contacts_search",
    "get_contact_history": "contacts_get",
    "create_contact": "contacts_create",
    "update_contact": "contacts_update",

    # Tasks
    "get_tasks": "tasks_search",
    "create_task": "tasks_create",
    "update_task": "tasks_update",
    "complete_task": "tasks_complete",
    "delete_task": "tasks_delete",

    # Meetings
    "search_meetings": "meetings_search",
    "create_meeting": "meetings_create",

    # Reflections
    "get_reflections": "reflections_search",
    "create_reflection": "reflections_create",

    # Journals
    "get_journals": "journals_search",

    # Transcripts
    "search_transcripts": "transcripts_search",
    "get_full_transcript": "transcripts_get",

    # Calendar
    "get_upcoming_events": "calendar_search",

    # Database
    "query_database": "query",
    "query_knowledge": "search",
}


# =============================================================================
# SERVICE-TO-SERVICE AUTHENTICATION
# =============================================================================

def _get_identity_token(audience: str) -> Optional[str]:
    """
    Get Google Cloud identity token for service-to-service authentication.

    In Cloud Run, this uses the metadata server to get a token.
    Locally, returns None (calls will fail with 403 on protected endpoints).

    Args:
        audience: The URL of the service to authenticate to (e.g., sync service URL)

    Returns:
        Identity token string, or None if not running in Cloud Run
    """
    import requests
    try:
        # Try Cloud Run metadata server (works in Cloud Run)
        metadata_url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
        response = requests.get(
            metadata_url,
            params={"audience": audience},
            headers={"Metadata-Flavor": "Google"},
            timeout=2
        )
        if response.status_code == 200:
            logger.debug("Got identity token from metadata server")
            return response.text
    except requests.exceptions.RequestException:
        logger.debug("Metadata server not available (not running in Cloud Run)")

    # Try google-auth library as fallback (for local dev with Application Default Credentials)
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        auth_request = google.auth.transport.requests.Request()
        token = google.oauth2.id_token.fetch_id_token(auth_request, audience)
        logger.debug("Got identity token from google-auth library")
        return token
    except Exception as e:
        logger.debug(f"Could not get identity token from google-auth: {e}")

    logger.warning(f"Could not obtain identity token for {audience} - requests may fail with 403")
    return None


# =============================================================================
# ASYNC HELPERS
# =============================================================================

def _run_async(coro):
    """Safely run async code from sync context.

    This handles the case where we're called from an async context (FastAPI)
    but need to run async code synchronously (Claude tool execution).

    The key challenge is that httpx.AsyncClient creates connections tied to
    an event loop. If we use asyncio.run(), it closes the loop before the
    client cleanup completes, causing "Event loop is closed" errors.

    Solution: Create a new event loop, run the coroutine, and let it complete
    fully (including cleanup) before closing.
    """
    def run_in_new_loop(coro):
        """Run coroutine in a new event loop, ensuring proper cleanup."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            # Give pending tasks time to complete
            try:
                # Cancel any pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # Wait for cancellation to complete
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                loop.close()

    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We are - run in a separate thread to avoid blocking
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop, coro)
            return future.result(timeout=60)  # Increased timeout for API calls
    except RuntimeError:
        # No running loop - safe to run directly
        return run_in_new_loop(coro)


# =============================================================================
# RESEARCH TOOLS HANDLER (Lazy import)
# =============================================================================

async def _handle_research_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle research tool calls (LinkedIn, Web Search)."""
    from app.features.research import handle_research_tool
    return await handle_research_tool(tool_name, tool_input)


# =============================================================================
# WRITABLE/READONLY TABLE LISTS
# =============================================================================

# Tables that can be modified via tools
WRITABLE_TABLES = [
    "contacts", "meetings", "tasks", "journals", "reflections",
    "applications", "linkedin_posts", "books", "highlights"
]

# Tables that should NOT be modified (sync-managed)
READONLY_TABLES = [
    "calendar_events", "emails", "beeper_chats", "beeper_messages",
    "transcripts", "sync_logs", "sync_state", "pipeline_logs"
]

# Tables managed by sync (need last_sync_source flag)
SYNC_MANAGED_TABLES = [
    "applications", "meetings", "tasks", "journals",
    "reflections", "contacts", "linkedin_posts"
]
