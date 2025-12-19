"""
Sync Trigger Service.
Triggers the Sync Service to push newly created data to Notion immediately.
"""

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger('Jarvis.Intelligence.SyncTrigger')

# Sync service base URL
SYNC_SERVICE_URL = settings.SYNC_SERVICE_URL


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
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(f"Triggering sync: {url}")
            response = await client.post(url)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Sync {sync_type} completed: {result}")
                return True
            else:
                logger.error(f"Sync {sync_type} failed: {response.status_code} - {response.text}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"Sync {sync_type} timed out")
        return False
    except Exception as e:
        logger.error(f"Error triggering {sync_type} sync: {e}")
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
