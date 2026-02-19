"""
Meeting Tools for Chat.

This module contains tools for meeting operations including searching,
creating, and managing meeting records.
"""

from typing import Dict, Any
from datetime import datetime, timezone

from app.core.database import supabase
from .base import logger, _sanitize_ilike


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

MEETING_TOOLS = [
    {
        "name": "search_meetings",
        "description": "Search for past meetings by title, attendee, or topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (title, attendee name, topic)"
                },
                "days": {
                    "type": "integer",
                    "description": "Search within last N days (default: all time)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_meeting",
        "description": "Create a new meeting record in the database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Meeting title"
                },
                "date": {
                    "type": "string",
                    "description": "Meeting date (ISO format or YYYY-MM-DD)"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Name of the main contact (will be linked)"
                },
                "summary": {
                    "type": "string",
                    "description": "Meeting summary/notes"
                },
                "topics_discussed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics covered in the meeting"
                },
                "action_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Action items from the meeting"
                },
                "location": {
                    "type": "string",
                    "description": "Meeting location (optional)"
                }
            },
            "required": ["title", "date"]
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _search_meetings(input: Dict) -> Dict[str, Any]:
    """Search for past meetings."""
    try:
        query = input.get("query", "").strip()
        days = input.get("days")
        limit = input.get("limit", 10)

        if not query:
            return {"error": "Search query is required"}

        safe_query = _sanitize_ilike(query)
        search_query = supabase.table("meetings").select(
            "id, title, date, location, summary, contact_name, topics_discussed, action_items"
        ).is_("deleted_at", "null").or_(
            f"title.ilike.%{safe_query}%,summary.ilike.%{safe_query}%,contact_name.ilike.%{safe_query}%"
        )

        if days:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            search_query = search_query.gte("date", cutoff)

        result = search_query.order("date", desc=True).limit(limit).execute()

        meetings = []
        for m in result.data or []:
            meetings.append({
                "id": m.get("id"),
                "title": m.get("title"),
                "date": m.get("date"),
                "location": m.get("location"),
                "contact": m.get("contact_name"),
                "summary": m.get("summary"),
                "topics": m.get("topics_discussed"),
                "action_items": m.get("action_items")
            })

        return {"meetings": meetings, "count": len(meetings)}
    except Exception as e:
        logger.error(f"Error searching meetings: {e}")
        return {"error": str(e)}


def _create_meeting(input: Dict) -> Dict[str, Any]:
    """Create a new meeting record."""
    try:
        title = input.get("title", "").strip()
        date_str = input.get("date", "").strip()
        contact_name = input.get("contact_name", "").strip()
        summary = input.get("summary", "").strip()
        topics_discussed = input.get("topics_discussed", [])
        action_items = input.get("action_items", [])
        location = input.get("location", "").strip()

        if not title:
            return {"error": "title is required"}
        if not date_str:
            return {"error": "date is required"}

        # Parse and validate date
        try:
            if "T" in date_str:
                meeting_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                meeting_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return {"error": f"Invalid date format: {date_str}. Use YYYY-MM-DD or ISO format."}

        # Look up contact if name provided
        contact_id = None
        if contact_name:
            safe_contact = _sanitize_ilike(contact_name)
            contact_result = supabase.table("contacts").select("id").or_(
                f"first_name.ilike.%{safe_contact}%,last_name.ilike.%{safe_contact}%"
            ).is_("deleted_at", "null").limit(1).execute()

            if contact_result.data:
                contact_id = contact_result.data[0]["id"]

        # Create meeting record
        meeting_data = {
            "title": title,
            "date": meeting_date.isoformat(),
            "contact_name": contact_name or None,
            "contact_id": contact_id,
            "summary": summary or None,
            "topics_discussed": topics_discussed if topics_discussed else None,
            "action_items": action_items if action_items else None,
            "location": location or None,
            "last_sync_source": "supabase"
        }

        # Remove None values
        meeting_data = {k: v for k, v in meeting_data.items() if v is not None}

        result = supabase.table("meetings").insert(meeting_data).execute()

        if result.data:
            meeting = result.data[0]
            logger.info(f"Created meeting via chat: {title}")

            # Create tasks from action items
            tasks_created = []
            if action_items:
                for item in action_items:
                    if isinstance(item, str) and item.strip():
                        task_data = {
                            "title": item.strip(),
                            "status": "pending",
                            "origin_type": "meeting",
                            "origin_id": meeting["id"],
                            "last_sync_source": "supabase"
                        }
                        task_result = supabase.table("tasks").insert(task_data).execute()
                        if task_result.data:
                            tasks_created.append(task_result.data[0]["title"])

            return {
                "success": True,
                "meeting_id": meeting["id"],
                "title": title,
                "date": date_str,
                "contact_linked": contact_id is not None,
                "tasks_created": tasks_created,
                "message": f"Created meeting: {title}" + (
                    f" with {len(tasks_created)} task(s)" if tasks_created else ""
                )
            }
        return {"error": "Failed to create meeting"}
    except Exception as e:
        logger.error(f"Error creating meeting: {e}")
        return {"error": str(e)}
