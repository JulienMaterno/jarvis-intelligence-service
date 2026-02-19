"""
Sync Tools for Chat.

This module contains tools for triggering data synchronization between
Supabase, Notion, and external services.
"""

import httpx
import logging
from typing import Dict, List, Any, Optional

from .base import _get_sync_service_headers, _get_sync_service_url, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

SYNC_TOOLS = [
    {
        "name": "quick_sync",
        "description": """Quickly sync a single entity type between Notion and Supabase.

Use when user says:
- "Sync my meetings now"
- "Update my tasks from Notion"
- "I just changed something in Notion, sync it"
- "Sync [entity] please"

This triggers a fast incremental sync (< 2 seconds) for just the specified entity type.
Much faster than waiting for the full scheduled sync cycle.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["meetings", "tasks", "reflections", "journals", "contacts", "books", "highlights", "calendar", "gmail"],
                    "description": "The type of data to sync"
                },
                "hours": {
                    "type": "integer",
                    "description": "How many hours to look back (default 1)",
                    "default": 1
                }
            },
            "required": ["entity_type"]
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _quick_sync(params: Dict[str, Any]) -> Dict[str, Any]:
    """Quickly sync a single entity type."""
    entity_type = params.get("entity_type")
    hours = params.get("hours", 1)

    if not entity_type:
        return {"error": "Missing required field: entity_type"}

    valid_entities = ["meetings", "tasks", "reflections", "journals", "contacts",
                      "books", "highlights", "calendar", "gmail"]

    if entity_type not in valid_entities:
        return {"error": f"Invalid entity_type. Must be one of: {valid_entities}"}

    sync_service_url = _get_sync_service_url()
    headers = _get_sync_service_headers(content_type=True)

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{sync_service_url}/sync/quick",
                headers=headers,
                json={
                    "entity_type": entity_type,
                    "hours": hours
                }
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "entity_type": entity_type,
                    "synced_count": result.get("synced_count", 0),
                    "direction": result.get("direction", "bidirectional"),
                    "message": f"Synced {result.get('synced_count', 0)} {entity_type} in {result.get('duration_ms', 0)}ms"
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Quick sync failed: {error_detail}"}

    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for quick sync")
        return {"error": "Sync service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error in quick sync: {e}")
        return {"error": str(e)}
