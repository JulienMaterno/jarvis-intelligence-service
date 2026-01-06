"""
Tasks Repository - Task data access operations.

Handles all task-related database operations including:
- Creating tasks from meetings/journals/reflections
- Getting pending tasks
- Completing tasks
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("Jarvis.Database.Tasks")


class TasksRepository:
    """Repository for task operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
    
    def create(
        self,
        title: str,
        description: str = None,
        priority: str = "medium",
        due_date: str = None,
        origin_id: str = None,
        origin_type: str = None,
        contact_id: str = None,
    ) -> Optional[str]:
        """
        Create a single task.
        
        Returns:
            Task ID if successful, None otherwise
        """
        try:
            # Check for existing task with same title
            existing = self.client.table("tasks").select("id").eq(
                "title", title
            ).is_("deleted_at", "null").limit(1).execute()
            
            if existing.data:
                logger.info(f"Task already exists, skipping: {title}")
                return existing.data[0]["id"]
            
            payload = {
                "title": title,
                "description": description or "",
                "status": "pending",
                "priority": priority.lower() if priority else "medium",
                "due_date": due_date,
                "origin_type": origin_type,
                "origin_id": origin_id,
                "contact_id": contact_id,
                "last_sync_source": "supabase",
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            result = self.client.table("tasks").insert(payload).execute()
            task_id = result.data[0]["id"]
            logger.info(f"Created task: {title}")
            return task_id
            
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None
    
    def create_batch(
        self,
        tasks_data: List[Dict],
        origin_id: str,
        origin_type: str = "meeting",
        contact_id: str = None,
    ) -> List[str]:
        """
        Create multiple tasks linked to an origin.
        
        Returns:
            List of created task IDs
        """
        created_ids = []
        if not tasks_data:
            return created_ids
        
        logger.info(f"Creating {len(tasks_data)} tasks linked to {origin_type} {origin_id}")
        
        for task in tasks_data:
            # Support both 'title' and 'task' keys
            title = task.get('title') or task.get('task', 'Untitled Task')
            
            task_id = self.create(
                title=title,
                description=task.get('description', ''),
                priority=task.get('priority', 'medium'),
                due_date=task.get('due_date'),
                origin_id=origin_id,
                origin_type=origin_type,
                contact_id=contact_id,
            )
            
            if task_id:
                created_ids.append(task_id)
        
        return created_ids
    
    def get_pending(self, limit: int = 20) -> List[Dict]:
        """Get pending tasks."""
        try:
            result = self.client.table("tasks").select("*").eq(
                "status", "pending"
            ).is_("deleted_at", "null").order(
                "due_date", desc=False, nullsfirst=False
            ).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting pending tasks: {e}")
            return []
    
    def get_by_id(self, task_id: str) -> Optional[Dict]:
        """Get a task by ID."""
        try:
            result = self.client.table("tasks").select("*").eq("id", task_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            return None
    
    def complete(self, task_id: str) -> bool:
        """Mark a task as completed."""
        try:
            self.client.table("tasks").update({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "last_sync_source": "supabase",
            }).eq("id", task_id).execute()
            logger.info(f"Completed task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}")
            return False
    
    def get_by_origin(self, origin_id: str, origin_type: str = None) -> List[Dict]:
        """Get tasks linked to a specific origin (meeting, journal, etc.)."""
        try:
            query = self.client.table("tasks").select("*").eq("origin_id", origin_id)
            if origin_type:
                query = query.eq("origin_type", origin_type)
            result = query.is_("deleted_at", "null").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting tasks for origin {origin_id}: {e}")
            return []
    
    def get_overdue(self) -> List[Dict]:
        """Get overdue tasks."""
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            result = self.client.table("tasks").select("*").eq(
                "status", "pending"
            ).lt("due_date", today).is_("deleted_at", "null").execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting overdue tasks: {e}")
            return []
    
    def update(self, task_id: str, updates: Dict) -> bool:
        """Update a task."""
        try:
            updates["last_sync_source"] = "supabase"
            self.client.table("tasks").update(updates).eq("id", task_id).execute()
            logger.info(f"Updated task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            return False
