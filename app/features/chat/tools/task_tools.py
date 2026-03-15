"""
Task Tools for Chat.

This module contains tools for task/to-do operations including creating,
updating, completing, and managing tasks. Supports time-specific reminders
via Google Cloud Tasks for exact-time delivery.
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.database import supabase
from .base import logger

# Cloud Tasks configuration for scheduled reminders
GCP_PROJECT = os.getenv("GCP_PROJECT", "jarvis-478401")
GCP_LOCATION = os.getenv("GCP_LOCATION", "asia-southeast1")
CLOUD_TASKS_QUEUE = os.getenv("CLOUD_TASKS_QUEUE", "jarvis-reminders")
SYNC_SERVICE_URL = os.getenv(
    "SYNC_SERVICE_URL",
    "https://jarvis-sync-service-776871804948.asia-southeast1.run.app"
)
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


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
                    "enum": ["pending", "in_progress", "completed", "all"],
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
                },
                "remind_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime for when to send a reminder notification (e.g. '2026-02-25T15:30:00+08:00'). Use get_current_time first to calculate absolute time from relative requests like 'in 2 hours'."
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
                    "enum": ["pending", "in_progress", "completed"]
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"]
                },
                "due_date": {
                    "type": "string",
                    "description": "New due date (YYYY-MM-DD)"
                },
                "remind_at": {
                    "type": "string",
                    "description": "New reminder time in ISO 8601 format. Set to reschedule a reminder."
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
        ).is_("deleted_at", "null")

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


def _schedule_cloud_task(task_id: str, remind_at: datetime, title: str) -> Optional[str]:
    """Schedule a Google Cloud Task to deliver a reminder at the specified time.

    Returns the Cloud Task name on success, or None on failure.
    """
    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(GCP_PROJECT, GCP_LOCATION, CLOUD_TASKS_QUEUE)

        # Build the HTTP request that Cloud Tasks will fire at remind_at
        url = f"{SYNC_SERVICE_URL}/deliver-reminder/{task_id}"
        payload = json.dumps({"task_id": task_id, "title": title}).encode()

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=url,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": INTERNAL_API_KEY,
                },
                body=payload,
            ),
            schedule_time=timestamp_pb2.Timestamp(
                seconds=int(remind_at.timestamp())
            ),
        )

        created = client.create_task(parent=parent, task=task)
        logger.info(f"Scheduled Cloud Task for reminder: task_id={task_id}, remind_at={remind_at.isoformat()}, cloud_task={created.name}")
        return created.name

    except ImportError:
        logger.warning("google-cloud-tasks not installed - reminder will not fire automatically")
        return None
    except Exception as e:
        logger.error(f"Failed to schedule Cloud Task for task_id={task_id}: {e}")
        return None


def _create_task(input: Dict) -> Dict[str, Any]:
    """Create a new task, optionally with a scheduled reminder."""
    try:
        title = input.get("title", "").strip()
        if not title:
            return {"error": "title is required"}

        # Dedup check: prevent creating tasks with identical titles
        existing = supabase.table("tasks").select("id, title, status").eq(
            "title", title
        ).is_("deleted_at", "null").neq("status", "cancelled").limit(1).execute()
        if existing.data:
            existing_task = existing.data[0]
            logger.info(f"Task already exists, skipping duplicate: '{title}' (id={existing_task['id']})")
            return {
                "success": False,
                "task_id": existing_task["id"],
                "title": title,
                "message": f"Task '{title}' already exists (status: {existing_task['status']}). Use update_task to modify it.",
                "duplicate": True
            }

        task_data = {
            "title": title,
            "description": input.get("description", "").strip() or None,
            "priority": input.get("priority", "medium"),
            "status": "pending",
            "due_date": input.get("due_date") or None,
            "last_sync_source": "supabase"
        }

        # Parse remind_at if provided
        remind_at_str = input.get("remind_at")
        remind_at_dt = None
        if remind_at_str:
            try:
                remind_at_dt = datetime.fromisoformat(remind_at_str)
                if remind_at_dt.tzinfo is None:
                    remind_at_dt = remind_at_dt.replace(tzinfo=timezone.utc)
                task_data["remind_at"] = remind_at_dt.isoformat()
            except ValueError as e:
                logger.warning(f"Invalid remind_at format '{remind_at_str}': {e}")

        # Remove None values
        task_data = {k: v for k, v in task_data.items() if v is not None}

        result = supabase.table("tasks").insert(task_data).execute()

        if result.data:
            task = result.data[0]
            task_id = task["id"]

            # Verify the task was actually persisted
            verify = supabase.table("tasks").select("id").eq("id", task_id).execute()
            if not verify.data:
                logger.error(f"PHANTOM CREATE: Task insert returned data but verification failed for '{title}' (id={task_id})")
                return {"error": f"Task creation failed verification - please try again"}

            # Schedule Cloud Task for reminder delivery
            cloud_task_name = None
            if remind_at_dt:
                cloud_task_name = _schedule_cloud_task(task_id, remind_at_dt, title)

            logger.info(f"Created task via chat: {title} (id={task_id}, remind_at={remind_at_str})")

            response = {
                "success": True,
                "task_id": task_id,
                "title": title,
                "message": f"Created task: {title}"
            }
            if remind_at_dt:
                response["remind_at"] = remind_at_dt.isoformat()
                response["reminder_scheduled"] = cloud_task_name is not None
                if cloud_task_name:
                    response["message"] += f" (reminder scheduled for {remind_at_dt.strftime('%b %d at %H:%M')})"
                else:
                    response["message"] += " (reminder saved but automatic scheduling failed - will still appear in digests)"
            return response
        return {"error": "Failed to create task - no data returned from insert"}
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
            result = supabase.table("tasks").select("id, title").eq("id", task_id).is_("deleted_at", "null").execute()
        else:
            result = supabase.table("tasks").select("id, title").ilike(
                "title", f"%{task_id}%"
            ).neq("status", "completed").is_("deleted_at", "null").limit(1).execute()

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
            if input["status"] == "completed":
                update_fields["completed_at"] = datetime.now(timezone.utc).isoformat()
        if input.get("priority"):
            update_fields["priority"] = input["priority"]
        if input.get("due_date"):
            update_fields["due_date"] = input["due_date"]

        # Handle remind_at (reschedule reminder)
        remind_at_dt = None
        if input.get("remind_at"):
            try:
                remind_at_dt = datetime.fromisoformat(input["remind_at"])
                if remind_at_dt.tzinfo is None:
                    remind_at_dt = remind_at_dt.replace(tzinfo=timezone.utc)
                update_fields["remind_at"] = remind_at_dt.isoformat()
                update_fields["reminded_at"] = None  # Reset so new reminder fires
            except ValueError as e:
                logger.warning(f"Invalid remind_at in update: {e}")

        if not update_fields:
            return {"error": "No fields to update"}

        # Add metadata
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_fields["last_sync_source"] = "supabase"

        update_result = supabase.table("tasks").update(update_fields).eq("id", task_id).execute()
        if not update_result.data:
            return {"error": "Task update failed - no data returned"}

        # Schedule new Cloud Task if remind_at was updated
        if remind_at_dt:
            task_title = input.get("title", task["title"]).strip()
            _schedule_cloud_task(task_id, remind_at_dt, task_title)

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
            result = supabase.table("tasks").select("id, title, status").eq("id", task_id).is_("deleted_at", "null").execute()
        else:
            result = supabase.table("tasks").select("id, title, status").ilike(
                "title", f"%{task_id}%"
            ).neq("status", "completed").is_("deleted_at", "null").limit(1).execute()

        if not result.data:
            return {"error": "Task not found or already completed"}

        task = result.data[0]
        task_id = task["id"]

        if task["status"] == "completed":
            return {"message": f"Task '{task['title']}' is already completed"}

        supabase.table("tasks").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_source": "supabase"
        }).eq("id", task_id).execute()

        # Verify the completion actually persisted
        verify = supabase.table("tasks").select("id, status").eq("id", task_id).execute()
        if verify.data and verify.data[0].get("status") != "completed":
            logger.error(f"PHANTOM COMPLETE: Task {task_id} update returned but status is still '{verify.data[0].get('status')}'")
            return {"error": f"Task completion failed verification - status did not update. Please try again."}

        logger.info(f"Completed task via chat: {task['title']} (id={task_id})")
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
            result = supabase.table("tasks").select("id, title").eq("id", task_id).is_("deleted_at", "null").execute()
        else:
            result = supabase.table("tasks").select("id, title").ilike(
                "title", f"%{task_id}%"
            ).is_("deleted_at", "null").limit(1).execute()

        if not result.data:
            return {"error": "Task not found"}

        task = result.data[0]
        task_id = task["id"]

        supabase.table("tasks").update({
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_source": "supabase"
        }).eq("id", task_id).execute()

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
