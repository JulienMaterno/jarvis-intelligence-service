"""
Task Tools for Chat.

This module contains tools for task/to-do operations including creating,
updating, completing, and managing tasks.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from app.core.database import supabase
from .base import logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TASK_TOOLS = [
    {
        "name": "get_tasks",
        "description": "Get tasks/to-dos, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done", "all"],
                    "description": "Filter by status",
                    "default": "pending"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max tasks to return",
                    "default": 100
                }
            },
            "required": []
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task/to-do item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "description": {
                    "type": "string",
                    "description": "Optional description"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "default": "medium"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "update_task",
        "description": "Update an existing task's details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task UUID or title to search"
                },
                "title": {
                    "type": "string",
                    "description": "New title"
                },
                "description": {
                    "type": "string",
                    "description": "New description"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "done"]
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"]
                },
                "due_date": {
                    "type": "string",
                    "description": "New due date (YYYY-MM-DD)"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "complete_task",
        "description": "Mark a task as complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task UUID or title to search"
                }
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "delete_task",
        "description": "Delete a task permanently.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task UUID or title to search"
                }
            },
            "required": ["task_id"]
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _get_tasks(status: str = "pending", limit: int = 100) -> Dict[str, Any]:
    """Get tasks/to-dos."""
    try:
        query = supabase.table("tasks").select(
            "id, title, description, status, priority, due_date, completed_at, "
            "project, tags, origin_type, created_at"
        )

        if status != "all":
            query = query.eq("status", status)

        result = query.order("due_date", nullsfirst=False).limit(limit).execute()

        tasks = []
        for t in result.data or []:
            tasks.append({
                "id": t.get("id"),
                "title": t.get("title"),
                "description": t.get("description"),
                "status": t.get("status"),
                "priority": t.get("priority"),
                "due_date": t.get("due_date"),
                "project": t.get("project"),
                "tags": t.get("tags")
            })

        return {"tasks": tasks, "count": len(tasks), "status_filter": status}
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        return {"error": str(e)}


def _create_task(input: Dict) -> Dict[str, Any]:
    """Create a new task."""
    try:
        title = input.get("title", "").strip()
        if not title:
            return {"error": "title is required"}

        task_data = {
            "title": title,
            "description": input.get("description", "").strip() or None,
            "priority": input.get("priority", "medium"),
            "status": "pending",
            "due_date": input.get("due_date") or None,
            "last_sync_source": "supabase"
        }

        # Remove None values
        task_data = {k: v for k, v in task_data.items() if v is not None}

        result = supabase.table("tasks").insert(task_data).execute()

        if result.data:
            task = result.data[0]
            logger.info(f"Created task via chat: {title}")
            return {
                "success": True,
                "task_id": task["id"],
                "title": title,
                "message": f"Created task: {title}"
            }
        return {"error": "Failed to create task"}
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        return {"error": str(e)}


def _update_task(input: Dict) -> Dict[str, Any]:
    """Update an existing task."""
    try:
        task_id = input.get("task_id", "").strip()
        if not task_id:
            return {"error": "task_id is required"}

        # Try to find task by ID or title
        if len(task_id) == 36 and "-" in task_id:  # UUID format
            result = supabase.table("tasks").select("id, title").eq("id", task_id).execute()
        else:
            result = supabase.table("tasks").select("id, title").ilike(
                "title", f"%{task_id}%"
            ).eq("status", "pending").limit(1).execute()

        if not result.data:
            return {"error": "Task not found"}

        task = result.data[0]
        task_id = task["id"]

        # Build update fields
        update_fields = {}
        if input.get("title"):
            update_fields["title"] = input["title"].strip()
        if input.get("description"):
            update_fields["description"] = input["description"].strip()
        if input.get("status"):
            update_fields["status"] = input["status"]
            if input["status"] == "done":
                update_fields["completed_at"] = datetime.now(timezone.utc).isoformat()
        if input.get("priority"):
            update_fields["priority"] = input["priority"]
        if input.get("due_date"):
            update_fields["due_date"] = input["due_date"]

        if not update_fields:
            return {"error": "No fields to update"}

        # Add metadata
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_fields["last_sync_source"] = "supabase"

        supabase.table("tasks").update(update_fields).eq("id", task_id).execute()

        logger.info(f"Updated task via chat: {task['title']}")
        return {
            "success": True,
            "task_id": task_id,
            "title": task["title"],
            "updated_fields": list(update_fields.keys()),
            "message": f"Updated task: {task['title']}"
        }
    except Exception as e:
        logger.error(f"Error updating task: {e}")
        return {"error": str(e)}


def _complete_task(input: Dict) -> Dict[str, Any]:
    """Mark a task as complete."""
    try:
        task_id = input.get("task_id", "").strip()
        if not task_id:
            return {"error": "task_id is required"}

        # Try to find task by ID or title
        if len(task_id) == 36 and "-" in task_id:
            result = supabase.table("tasks").select("id, title, status").eq("id", task_id).execute()
        else:
            result = supabase.table("tasks").select("id, title, status").ilike(
                "title", f"%{task_id}%"
            ).neq("status", "done").limit(1).execute()

        if not result.data:
            return {"error": "Task not found or already completed"}

        task = result.data[0]
        task_id = task["id"]

        if task["status"] == "done":
            return {"message": f"Task '{task['title']}' is already completed"}

        supabase.table("tasks").update({
            "status": "done",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_source": "supabase"
        }).eq("id", task_id).execute()

        logger.info(f"Completed task via chat: {task['title']}")
        return {
            "success": True,
            "task_id": task_id,
            "title": task["title"],
            "message": f"Completed task: {task['title']}"
        }
    except Exception as e:
        logger.error(f"Error completing task: {e}")
        return {"error": str(e)}


def _delete_task(input: Dict) -> Dict[str, Any]:
    """Delete a task permanently."""
    try:
        task_id = input.get("task_id", "").strip()
        if not task_id:
            return {"error": "task_id is required"}

        # Try to find task by ID or title
        if len(task_id) == 36 and "-" in task_id:
            result = supabase.table("tasks").select("id, title").eq("id", task_id).execute()
        else:
            result = supabase.table("tasks").select("id, title").ilike(
                "title", f"%{task_id}%"
            ).limit(1).execute()

        if not result.data:
            return {"error": "Task not found"}

        task = result.data[0]
        task_id = task["id"]

        supabase.table("tasks").delete().eq("id", task_id).execute()

        logger.info(f"Deleted task via chat: {task['title']}")
        return {
            "success": True,
            "task_id": task_id,
            "title": task["title"],
            "message": f"Deleted task: {task['title']}"
        }
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        return {"error": str(e)}
