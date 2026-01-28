"""
Sync Trigger Service.
Triggers the Sync Service to push newly created data to Notion immediately.
"""

import os
import logging
import httpx
import asyncio
from app.core.config import settings

logger = logging.getLogger('Jarvis.Intelligence.SyncTrigger')

# Sync service base URL
SYNC_SERVICE_URL = settings.SYNC_SERVICE_URL

# Internal API key for authenticating with other services
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds


def _get_sync_headers() -> dict:
    """Get authentication headers for sync service requests."""
    headers = {}
    if INTERNAL_API_KEY:
        headers["X-API-Key"] = INTERNAL_API_KEY
    return headers


async def trigger_sync(sync_type: str) -> bool:
    """
    Trigger a specific sync to run.
    
    Args:
        sync_type: One of 'tasks', 'meetings', 'reflections', 'journals'
    
    Returns:
        True if sync was triggered successfully, False otherwise
    """
    if not SYNC_SERVICE_URL:
        logger.warning("SYNC_SERVICE_URL not configured, skipping sync trigger")
        return False
    
    endpoint_map = {
        "tasks": "/sync/tasks",
        "meetings": "/sync/meetings",
        "reflections": "/sync/reflections",
        "journals": "/sync/reflections",  # Journals sync with reflections for now
    }
    
    endpoint = endpoint_map.get(sync_type)
    if not endpoint:
        logger.warning(f"Unknown sync type: {sync_type}")
        return False
    
    url = f"{SYNC_SERVICE_URL.rstrip('/')}{endpoint}"
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if attempt == 0:
                    logger.info(f"Triggering sync: {url}")
                else:
                    logger.info(f"Retrying sync {sync_type} (attempt {attempt + 1}/{MAX_RETRIES})")

                response = await client.post(url, headers=_get_sync_headers())
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"Sync {sync_type} completed: {result}")
                    return True
                elif response.status_code >= 500:
                    # Server error - retry
                    last_error = f"Server error: {response.status_code}"
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                else:
                    logger.error(f"Sync {sync_type} failed: {response.status_code} - {response.text}")
                    return False
                    
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
            last_error = str(e)
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Sync {sync_type} attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(RETRY_DELAYS[attempt])
            else:
                logger.error(f"Sync {sync_type} failed after {MAX_RETRIES} attempts: {e}")
        except Exception as e:
            logger.error(f"Error triggering {sync_type} sync: {e}")
            return False
    
    logger.error(f"Sync {sync_type} failed after {MAX_RETRIES} retries: {last_error}")
    return False


async def trigger_syncs_for_records(db_records: dict) -> dict:
    """
    Trigger syncs based on what was created.

    Args:
        db_records: Dict with lists of created IDs (task_ids, meeting_ids, etc.)

    Returns:
        Dict with sync results
    """
    results = {}

    # Determine which syncs to trigger based on what was created
    if db_records.get("task_ids"):
        results["tasks"] = await trigger_sync("tasks")

    if db_records.get("meeting_ids"):
        results["meetings"] = await trigger_sync("meetings")

    if db_records.get("reflection_ids"):
        results["reflections"] = await trigger_sync("reflections")

    if db_records.get("journal_ids"):
        results["journals"] = await trigger_sync("journals")

    return results


async def trigger_quick_sync(entity_type: str, hours: int = 1) -> dict:
    """
    Trigger a quick incremental sync for a single entity.

    This is designed for when the user wants to quickly sync recent changes
    (e.g., after making a change in Notion and wanting it in Supabase).

    Args:
        entity_type: One of 'meetings', 'tasks', 'reflections', 'journals', 'contacts',
                     'books', 'highlights', 'calendar', 'gmail'
        hours: How many hours to look back (default 1 for quick sync)

    Returns:
        Dict with sync result including elapsed time
    """
    import time

    if not SYNC_SERVICE_URL:
        return {"success": False, "error": "SYNC_SERVICE_URL not configured"}

    # Map entity types to endpoints
    endpoint_map = {
        "meetings": "/sync/meetings",
        "tasks": "/sync/tasks",
        "reflections": "/sync/reflections",
        "journals": "/sync/reflections",
        "contacts": "/sync/contacts",
        "books": "/sync/books",
        "highlights": "/sync/highlights",
        "calendar": "/sync/calendar",
        "gmail": "/sync/gmail",
    }

    endpoint = endpoint_map.get(entity_type.lower())
    if not endpoint:
        return {
            "success": False,
            "error": f"Unknown entity type: {entity_type}. Valid types: {', '.join(endpoint_map.keys())}"
        }

    # Build URL with parameters for incremental sync
    url = f"{SYNC_SERVICE_URL.rstrip('/')}{endpoint}"
    params = {"hours": hours, "full": "false"}

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(f"Quick sync: {entity_type} (last {hours}h)")
            response = await client.post(url, params=params, headers=_get_sync_headers())

            elapsed_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Quick sync {entity_type} completed in {elapsed_ms}ms")
                return {
                    "success": True,
                    "entity_type": entity_type,
                    "elapsed_ms": elapsed_ms,
                    "data": result
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"Quick sync {entity_type} failed: {error_msg}")
                return {
                    "success": False,
                    "entity_type": entity_type,
                    "elapsed_ms": elapsed_ms,
                    "error": error_msg
                }

    except httpx.TimeoutException:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "success": False,
            "entity_type": entity_type,
            "elapsed_ms": elapsed_ms,
            "error": "Request timed out"
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.error(f"Quick sync {entity_type} error: {e}")
        return {
            "success": False,
            "entity_type": entity_type,
            "elapsed_ms": elapsed_ms,
            "error": str(e)
        }
