"""
Calendar Tools for Chat.

This module contains tools for calendar operations including viewing events,
creating events, updating events, and declining invitations.
"""

import httpx
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase
from .base import _get_sync_service_headers, _get_sync_service_url, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

CALENDAR_TOOLS = [
    {
        "name": "get_upcoming_events",
        "description": "Get upcoming calendar events for the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead",
                    "default": 7
                }
            },
            "required": []
        }
    },
    {
        "name": "create_calendar_event",
        "description": """Create a new event in the user's Google Calendar.
Use this when user asks to:
- Schedule a meeting
- Create a calendar event
- Block time for something
- Set up a reminder event
- Add something to their calendar

TIME RULES (CRITICAL):
1. ALWAYS call get_current_time FIRST to get the user's current date/time and timezone
2. Use the USER'S TIMEZONE from get_current_time for all calculations (NOT UTC)
3. SNAP times to 30-minute intervals: :00 or :30 only
   - "in an hour" at 1:43pm -> start at 2:30pm or 3:00pm (next half-hour after 2:43)
   - "at 3" -> 3:00pm
   - "in 30 minutes" at 2:10pm -> start at 2:30pm
4. DEFAULT DURATION: 30 minutes unless user specifies
   - "meeting at 3pm" -> 3:00pm - 3:30pm
   - "1 hour meeting" -> specified start - 1 hour later
   - "meeting from 2-4" -> 2:00pm - 4:00pm

NOTE: The sync service will apply the user's timezone. Just provide clean ISO times.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/summary"
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format. MUST be snapped to :00 or :30 (e.g., '2025-01-20T14:00:00' or '2025-01-20T14:30:00')"
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format. Default 30min after start. MUST be snapped to :00 or :30"
                },
                "description": {
                    "type": "string",
                    "description": "Event description/notes (optional)"
                },
                "location": {
                    "type": "string",
                    "description": "Event location (optional)"
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses (optional)"
                }
            },
            "required": ["title", "start_time", "end_time"]
        }
    },
    {
        "name": "update_calendar_event",
        "description": """Update/reschedule an existing calendar event.
Use this when user asks to:
- Reschedule a meeting
- Move a calendar event to a different time
- Change meeting details (location, description)
- Add a reason for rescheduling

First use query_database to find the event_id from calendar_events table using the event title or time.
Then update it with new details.

IMPORTANT:
- This notifies all attendees by default
- Add reschedule reason to description field
- Only the event organizer can reschedule""",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event ID (query calendar_events.google_event_id to find this)"
                },
                "title": {
                    "type": "string",
                    "description": "New event title (optional)"
                },
                "start_time": {
                    "type": "string",
                    "description": "New start time in ISO 8601 format (optional)"
                },
                "end_time": {
                    "type": "string",
                    "description": "New end time in ISO 8601 format (optional)"
                },
                "description": {
                    "type": "string",
                    "description": "Updated description - use this to add reschedule reason like 'Rescheduled due to conflict' (optional)"
                },
                "location": {
                    "type": "string",
                    "description": "New location (optional)"
                },
                "send_updates": {
                    "type": "string",
                    "enum": ["all", "externalOnly", "none"],
                    "description": "Who to notify about the update (default: 'all')"
                }
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "decline_calendar_event",
        "description": """Decline a calendar invitation that someone else sent you.
Use this when user asks to:
- Decline a meeting invitation
- Say no to an event
- Suggest an alternative time for a meeting they were invited to

First use query_database to find the event_id from calendar_events table.
Optionally include a comment with the decline (e.g., alternative time suggestion).

NOTE: This is for events you're INVITED to, not events you organized.
To cancel your own event, use update_calendar_event to change the status.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event ID (query calendar_events.google_event_id to find this)"
                },
                "comment": {
                    "type": "string",
                    "description": "Optional message to send with decline (e.g., 'Can we do 3pm instead?')"
                }
            },
            "required": ["event_id"]
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _get_upcoming_events(days: int = 7) -> Dict[str, Any]:
    """Get upcoming calendar events."""
    try:
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days)

        result = supabase.table("calendar_events").select(
            "id, google_event_id, summary, description, start_time, end_time, "
            "location, status, attendees, contact_id"
        ).gte("start_time", now.isoformat()).lte("start_time", end.isoformat()
        ).neq("status", "cancelled"
        ).order("start_time").limit(50).execute()

        events = []
        for e in result.data or []:
            events.append({
                "id": e.get("google_event_id"),
                "title": e.get("summary"),
                "start": e.get("start_time"),
                "end": e.get("end_time"),
                "location": e.get("location"),
                "status": e.get("status"),
                "attendees": e.get("attendees")
            })

        return {
            "events": events,
            "count": len(events),
            "period": f"Next {days} days"
        }
    except Exception as e:
        logger.error(f"Error getting upcoming events: {e}")
        return {"error": str(e)}


def _create_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a calendar event via the sync service."""
    title = params.get("title")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    description = params.get("description")
    location = params.get("location")
    attendees = params.get("attendees", [])

    if not title or not start_time or not end_time:
        return {"error": "Missing required fields: title, start_time, end_time"}

    sync_service_url = _get_sync_service_url()
    headers = _get_sync_service_headers(content_type=True)

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/create",
                headers=headers,
                json={
                    "summary": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description,
                    "location": location,
                    "attendees": attendees
                }
            )

            if response.status_code == 200:
                result = response.json()
                event_link = result.get("html_link", "")
                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": f"Calendar event '{title}' created successfully!",
                    "details": {
                        "title": title,
                        "start": start_time,
                        "end": end_time,
                        "location": location,
                        "attendees": attendees,
                        "link": event_link
                    }
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to create calendar event: {error_detail}"}

    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar creation")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return {"error": str(e)}


def _update_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Update/reschedule an existing calendar event."""
    event_id = params.get("event_id")
    title = params.get("title")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    description = params.get("description")
    location = params.get("location")
    send_updates = params.get("send_updates", "all")

    if not event_id:
        return {"error": "Missing required field: event_id"}

    sync_service_url = _get_sync_service_url()
    headers = _get_sync_service_headers(content_type=True)

    try:
        payload = {"event_id": event_id, "send_updates": send_updates}
        if title:
            payload["summary"] = title
        if start_time:
            payload["start_time"] = start_time
        if end_time:
            payload["end_time"] = end_time
        if description:
            payload["description"] = description
        if location:
            payload["location"] = location

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/update",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                result = response.json()
                event_link = result.get("html_link", "")

                changes = []
                if start_time or end_time:
                    changes.append("time")
                if description:
                    changes.append("details")
                if location:
                    changes.append("location")

                change_desc = " and ".join(changes) if changes else "meeting"

                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": f"Calendar event rescheduled! Updated {change_desc}. All attendees have been notified.",
                    "details": {
                        "title": result.get("summary"),
                        "start": result.get("start"),
                        "end": result.get("end"),
                        "link": event_link
                    }
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to update calendar event: {error_detail}"}

    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar update")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error updating calendar event: {e}")
        return {"error": str(e)}


def _decline_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Decline a calendar invitation."""
    event_id = params.get("event_id")
    comment = params.get("comment")

    if not event_id:
        return {"error": "Missing required field: event_id"}

    sync_service_url = _get_sync_service_url()
    headers = _get_sync_service_headers(content_type=True)

    try:
        payload = {"event_id": event_id}
        if comment:
            payload["comment"] = comment

        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/decline",
                headers=headers,
                json=payload
            )

            if response.status_code == 200:
                result = response.json()

                msg = f"Declined the calendar invitation for '{result.get('summary', 'the meeting')}'"
                if comment:
                    msg += f" with message: '{comment}'"
                msg += ". The organizer has been notified."

                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": msg,
                    "response_status": "declined"
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to decline calendar event: {error_detail}"}

    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar decline")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error declining calendar event: {e}")
        return {"error": str(e)}
