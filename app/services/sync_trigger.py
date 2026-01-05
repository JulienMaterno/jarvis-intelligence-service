"""
Sync Trigger Service.
Triggers the Sync Service to push newly created data to Notion immediately.
"""

import logging
import httpx
import asyncio
from app.core.config import settings

logger = logging.getLogger('Jarvis.Intelligence.SyncTrigger')

# Sync service base URL
SYNC_SERVICE_URL = settings.SYNC_SERVICE_URL

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds


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
                    
                response = await client.post(url)
                
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
