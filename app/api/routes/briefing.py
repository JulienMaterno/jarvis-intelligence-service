"""
Briefing API Routes

Provides endpoints for:
- Generating meeting briefings on-demand
- Checking for upcoming meetings that need briefings
- Hourly scheduling with notifications 15 min before meetings
- Manual trigger for testing

SCHEDULING APPROACH:
- `/briefings/schedule-hourly` runs every hour via Cloud Scheduler
- It scans for meetings in the next hour and schedules briefings
- It stores scheduled briefings in the `scheduled_briefings` table
- `/briefings/send-due` runs every minute to send due notifications
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import httpx

from app.api.dependencies import get_database, get_memory
from app.services.llm import ClaudeMultiAnalyzer
from app.features.briefing.meeting_briefing import (
    get_upcoming_events_for_briefing,
    generate_meeting_briefing,
    format_briefing_for_telegram,
    MeetingBriefing,
)
from app.shared.constants import TELEGRAM_BOT_URL
import os

router = APIRouter(tags=["Briefing"])
logger = logging.getLogger("Jarvis.Intelligence.API.Briefing")

# Default chat ID for briefing notifications
DEFAULT_TELEGRAM_CHAT_ID = os.getenv("DEFAULT_TELEGRAM_CHAT_ID")

# Minutes before meeting to send briefing
BRIEFING_LEAD_TIME_MINUTES = 15


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class BriefingResponse(BaseModel):
    """Response for a single briefing."""
    status: str
    event_id: str
    event_title: str
    event_start: str
    contact_name: Optional[str] = None
    contact_company: Optional[str] = None
    previous_meetings_count: int = 0
    recent_emails_count: int = 0
    previous_events_count: int = 0
    beeper_messages_count: int = 0
    messaging_platforms: Optional[List[str]] = None
    briefing_text: str
    notification_sent: bool = False


class CheckBriefingsResponse(BaseModel):
    """Response for checking upcoming briefings."""
    status: str
    events_checked: int
    briefings_generated: int
    briefings: List[BriefingResponse]


class ScheduleHourlyResponse(BaseModel):
    """Response for hourly scheduling."""
    status: str
    events_scanned: int
    briefings_scheduled: int
    scheduled_times: List[str]


class SendDueResponse(BaseModel):
    """Response for sending due briefings."""
    status: str
    briefings_sent: int
    briefings_failed: int
    sent_event_ids: List[str]


class TriggerBriefingRequest(BaseModel):
    """Request to manually trigger a briefing for a specific event."""
    event_id: str
    send_notification: bool = True
    chat_id: Optional[int] = None  # Override default chat


class ManualBriefingRequest(BaseModel):
    """Request to generate a briefing for an event by title/contact."""
    event_title: Optional[str] = None
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    send_notification: bool = True


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def send_telegram_notification(message: str, chat_id: Optional[int] = None) -> bool:
    """Send a briefing notification via Telegram."""
    if not TELEGRAM_BOT_URL:
        logger.warning("TELEGRAM_BOT_URL not configured, skipping notification")
        return False
    
    # Use provided chat_id or fall back to default
    target_chat_id = chat_id
    if not target_chat_id and DEFAULT_TELEGRAM_CHAT_ID:
        try:
            target_chat_id = int(DEFAULT_TELEGRAM_CHAT_ID)
        except ValueError:
            logger.error(f"Invalid DEFAULT_TELEGRAM_CHAT_ID: {DEFAULT_TELEGRAM_CHAT_ID}")
            return False
    
    if not target_chat_id:
        logger.warning("No chat_id provided and no DEFAULT_TELEGRAM_CHAT_ID configured")
        return False
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "chat_id": target_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = await client.post(
                f"{TELEGRAM_BOT_URL}/send_message",
                json=payload
            )
            
            if response.status_code == 200:
                logger.info(f"Telegram notification sent successfully to chat {target_chat_id}")
                return True
            else:
                logger.warning(f"Telegram notification failed: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending Telegram notification: {e}")
        return False


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/briefings/upcoming", response_model=CheckBriefingsResponse)
async def check_upcoming_briefings(
    minutes_ahead: int = 30,
    send_notifications: bool = False
):
    """
    Check for upcoming meetings and generate briefings.
    
    Args:
        minutes_ahead: Look for events starting within this many minutes (default 30)
        send_notifications: Whether to send Telegram notifications
    
    Returns:
        List of briefings for upcoming events
    """
    db = get_database()
    llm = ClaudeMultiAnalyzer()
    memory = get_memory()
    
    try:
        # Get upcoming events
        events = get_upcoming_events_for_briefing(db, minutes_ahead=minutes_ahead)
        logger.info(f"Found {len(events)} upcoming events within {minutes_ahead} minutes")
        
        briefings = []
        for event in events:
            try:
                briefing = await generate_meeting_briefing(db, llm, event, memory)
                if briefing:
                    notification_sent = False
                    
                    if send_notifications:
                        telegram_text = format_briefing_for_telegram(briefing)
                        notification_sent = await send_telegram_notification(telegram_text)
                    
                    briefings.append(BriefingResponse(
                        status="success",
                        event_id=briefing.event_id,
                        event_title=briefing.event_title,
                        event_start=briefing.event_start,
                        contact_name=briefing.contact_name,
                        contact_company=briefing.contact_company,
                        previous_meetings_count=briefing.previous_meetings_count,
                        recent_emails_count=briefing.recent_emails_count,
                        previous_events_count=briefing.previous_events_count,
                        beeper_messages_count=briefing.beeper_messages_count,
                        messaging_platforms=briefing.messaging_platforms,
                        briefing_text=briefing.briefing_text,
                        notification_sent=notification_sent
                    ))
            except Exception as e:
                logger.error(f"Error generating briefing for event {event.get('id')}: {e}")
                continue
        
        return CheckBriefingsResponse(
            status="success",
            events_checked=len(events),
            briefings_generated=len(briefings),
            briefings=briefings
        )
        
    except Exception as e:
        logger.exception("Failed to check upcoming briefings")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/briefings/trigger", response_model=BriefingResponse)
async def trigger_briefing(request: TriggerBriefingRequest):
    """
    Manually trigger a briefing for a specific calendar event.
    
    This endpoint is useful for testing or when you want a briefing
    outside the normal time window.
    """
    db = get_database()
    llm = ClaudeMultiAnalyzer()
    memory = get_memory()
    
    try:
        # Fetch the event
        event_result = db.client.table("calendar_events").select("*").eq(
            "id", request.event_id
        ).single().execute()
        
        if not event_result.data:
            raise HTTPException(status_code=404, detail=f"Event {request.event_id} not found")
        
        event = event_result.data
        
        # Generate briefing
        briefing = await generate_meeting_briefing(db, llm, event, memory)
        
        if not briefing:
            raise HTTPException(status_code=500, detail="Failed to generate briefing")
        
        notification_sent = False
        if request.send_notification:
            telegram_text = format_briefing_for_telegram(briefing)
            notification_sent = await send_telegram_notification(
                telegram_text, 
                chat_id=request.chat_id
            )
        
        return BriefingResponse(
            status="success",
            event_id=briefing.event_id,
            event_title=briefing.event_title,
            event_start=briefing.event_start,
            contact_name=briefing.contact_name,
            contact_company=briefing.contact_company,
            previous_meetings_count=briefing.previous_meetings_count,
            recent_emails_count=briefing.recent_emails_count,
            previous_events_count=briefing.previous_events_count,
            beeper_messages_count=briefing.beeper_messages_count,
            messaging_platforms=briefing.messaging_platforms,
            briefing_text=briefing.briefing_text,
            notification_sent=notification_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to trigger briefing for event {request.event_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/briefings/contact/{contact_id}", response_model=BriefingResponse)
async def generate_contact_briefing(
    contact_id: str,
    send_notification: bool = False
):
    """
    Generate a briefing for a contact (useful before calling/meeting them).
    
    This creates a briefing based on all history with the contact,
    not tied to a specific calendar event.
    """
    db = get_database()
    llm = ClaudeMultiAnalyzer()
    memory = get_memory()
    
    try:
        # Create a pseudo-event for the contact
        contact_result = db.client.table("contacts").select("*").eq(
            "id", contact_id
        ).single().execute()
        
        if not contact_result.data:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        
        contact = contact_result.data
        contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        
        # Create a pseudo-event
        pseudo_event = {
            "id": f"manual-{contact_id}",
            "summary": f"Meeting with {contact_name}",
            "title": f"Meeting with {contact_name}",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "contact_id": contact_id,
            "attendees": [contact.get("email")] if contact.get("email") else []
        }
        
        # Generate briefing
        briefing = await generate_meeting_briefing(db, llm, pseudo_event, memory)
        
        if not briefing:
            raise HTTPException(status_code=500, detail="Failed to generate briefing")
        
        notification_sent = False
        if send_notification:
            telegram_text = format_briefing_for_telegram(briefing)
            notification_sent = await send_telegram_notification(telegram_text)
        
        return BriefingResponse(
            status="success",
            event_id=briefing.event_id,
            event_title=briefing.event_title,
            event_start=briefing.event_start,
            contact_name=briefing.contact_name,
            contact_company=briefing.contact_company,
            previous_meetings_count=briefing.previous_meetings_count,
            recent_emails_count=briefing.recent_emails_count,
            previous_events_count=briefing.previous_events_count,
            beeper_messages_count=briefing.beeper_messages_count,
            messaging_platforms=briefing.messaging_platforms,
            briefing_text=briefing.briefing_text,
            notification_sent=notification_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate contact briefing for {contact_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/briefings/next")
async def get_next_meeting_briefing(send_notification: bool = False):
    """
    Get a briefing for the next upcoming meeting.
    
    Convenience endpoint that finds the next meeting and generates a briefing.
    """
    db = get_database()
    llm = ClaudeMultiAnalyzer()
    memory = get_memory()
    
    try:
        # Get the next event
        now = datetime.now(timezone.utc).isoformat()
        event_result = db.client.table("calendar_events").select("*").gte(
            "start_time", now
        ).neq(
            "status", "cancelled"
        ).order(
            "start_time", desc=False
        ).limit(1).execute()
        
        if not event_result.data:
            return {
                "status": "no_upcoming_events",
                "message": "No upcoming calendar events found"
            }
        
        event = event_result.data[0]
        
        # Generate briefing
        briefing = await generate_meeting_briefing(db, llm, event, memory)
        
        if not briefing:
            raise HTTPException(status_code=500, detail="Failed to generate briefing")
        
        notification_sent = False
        if send_notification:
            telegram_text = format_briefing_for_telegram(briefing)
            notification_sent = await send_telegram_notification(telegram_text)
        
        return BriefingResponse(
            status="success",
            event_id=briefing.event_id,
            event_title=briefing.event_title,
            event_start=briefing.event_start,
            contact_name=briefing.contact_name,
            contact_company=briefing.contact_company,
            previous_meetings_count=briefing.previous_meetings_count,
            recent_emails_count=briefing.recent_emails_count,
            previous_events_count=briefing.previous_events_count,
            beeper_messages_count=briefing.beeper_messages_count,
            messaging_platforms=briefing.messaging_platforms,
            briefing_text=briefing.briefing_text,
            notification_sent=notification_sent
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get next meeting briefing")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HOURLY SCHEDULING ENDPOINTS
# ============================================================================

@router.post("/briefings/schedule-hourly", response_model=ScheduleHourlyResponse)
async def schedule_hourly_briefings():
    """
    Scan for meetings in the next hour and schedule briefings.
    
    This endpoint should be called every hour by Cloud Scheduler.
    It finds all meetings starting in the next 60-75 minutes and:
    1. Pre-generates the briefing content
    2. Stores it in scheduled_briefings with a send_at time (15 min before meeting)
    3. The /briefings/send-due endpoint sends them when it's time
    
    This approach:
    - Saves resources (no 5-min polling)
    - Allows pre-generation of briefings
    - Ensures notifications arrive exactly 15 min before
    """
    db = get_database()
    llm = ClaudeMultiAnalyzer()
    memory = get_memory()
    
    try:
        now = datetime.now(timezone.utc)
        # Look for events starting 15 min to 75 min from now
        # (so we schedule briefings for events happening in the next hour)
        window_start = now + timedelta(minutes=BRIEFING_LEAD_TIME_MINUTES)
        window_end = now + timedelta(minutes=75)
        
        # Get upcoming events
        events_result = db.client.table("calendar_events").select("*").gte(
            "start_time", window_start.isoformat()
        ).lte(
            "start_time", window_end.isoformat()
        ).neq(
            "status", "cancelled"
        ).order(
            "start_time", desc=False
        ).execute()
        
        events = events_result.data or []
        logger.info(f"[Hourly Schedule] Found {len(events)} events in next hour")
        
        # Filter out all-day events (they have midnight UTC as start time)
        # All-day events from Google Calendar have 'date' instead of 'dateTime',
        # which gets stored as T00:00:00+00:00 in our database
        def is_all_day_event(event: dict) -> bool:
            """Check if event is an all-day event by detecting midnight UTC time."""
            start_time = event.get("start_time", "")
            # All-day events have T00:00:00 as their time (date-only from Google)
            return "T00:00:00" in start_time
        
        def is_real_meeting(event: dict) -> bool:
            """
            Determine if event is a real meeting worth briefing for.
            
            A real meeting either:
            1. Has at least one attendee besides yourself (email without 'self': True)
            2. OR title contains meeting indicators: "&", "<>", " x ", " X ", "|"
            
            Filters out:
            - Solo calendar blocks
            - Birthday reminders
            - Focus time / work blocks
            """
            title = event.get("summary", "") or ""
            attendees = event.get("attendees") or []
            
            # Check title for meeting indicators
            # " x " or " X " need spaces to avoid matching words like "next" or "text"
            meeting_title_markers = ["&", "<>", " x ", " X ", "|"]
            has_meeting_marker = any(marker in title for marker in meeting_title_markers)
            
            if has_meeting_marker:
                return True
            
            # Check for external attendees (not self)
            external_attendees = [
                a for a in attendees 
                if not a.get("self", False)  # Not yourself
            ]
            
            if len(external_attendees) > 0:
                return True
            
            return False
        
        timed_events = [e for e in events if not is_all_day_event(e)]
        all_day_count = len(events) - len(timed_events)
        if all_day_count > 0:
            logger.info(f"[Hourly Schedule] Skipping {all_day_count} all-day events")
        
        # Filter to only real meetings (with other people or meeting indicators in title)
        real_meetings = [e for e in timed_events if is_real_meeting(e)]
        solo_count = len(timed_events) - len(real_meetings)
        if solo_count > 0:
            logger.info(f"[Hourly Schedule] Skipping {solo_count} solo/non-meeting events")
        events = real_meetings
        
        scheduled_count = 0
        scheduled_times = []
        
        for event in events:
            event_id = event.get("id")
            event_start = event.get("start_time")
            
            # Check if already scheduled
            existing = db.client.table("scheduled_briefings").select("id").eq(
                "event_id", event_id
            ).eq(
                "status", "pending"
            ).execute()
            
            if existing.data:
                logger.info(f"[Hourly Schedule] Event {event_id} already scheduled, skipping")
                continue
            
            try:
                # Generate briefing now (pre-compute)
                briefing = await generate_meeting_briefing(db, llm, event, memory)
                
                if briefing:
                    # Calculate when to send (15 min before meeting)
                    event_start_dt = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                    send_at = event_start_dt - timedelta(minutes=BRIEFING_LEAD_TIME_MINUTES)
                    
                    # Store scheduled briefing
                    telegram_text = format_briefing_for_telegram(briefing)
                    
                    db.client.table("scheduled_briefings").insert({
                        "event_id": event_id,
                        "event_title": briefing.event_title,
                        "event_start": event_start,
                        "send_at": send_at.isoformat(),
                        "briefing_text": telegram_text,
                        "contact_id": briefing.contact_id,
                        "contact_name": briefing.contact_name,
                        "status": "pending",
                        "created_at": now.isoformat()
                    }).execute()
                    
                    scheduled_count += 1
                    scheduled_times.append(send_at.isoformat())
                    logger.info(f"[Hourly Schedule] Scheduled briefing for {briefing.event_title} at {send_at}")
                    
            except Exception as e:
                logger.error(f"[Hourly Schedule] Error scheduling briefing for event {event_id}: {e}")
                continue
        
        return ScheduleHourlyResponse(
            status="success",
            events_scanned=len(events),
            briefings_scheduled=scheduled_count,
            scheduled_times=scheduled_times
        )
        
    except Exception as e:
        logger.exception("Failed to schedule hourly briefings")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/briefings/send-due", response_model=SendDueResponse)
async def send_due_briefings():
    """
    Send all briefings that are due now.
    
    This endpoint should be called every minute by Cloud Scheduler.
    It checks for scheduled_briefings where send_at <= now and status = 'pending',
    sends the notification, and marks them as 'sent'.
    
    This is the lightweight operation that can run frequently.
    """
    db = get_database()
    
    try:
        now = datetime.now(timezone.utc)
        
        # Get due briefings
        due_result = db.client.table("scheduled_briefings").select("*").lte(
            "send_at", now.isoformat()
        ).eq(
            "status", "pending"
        ).execute()
        
        due_briefings = due_result.data or []
        
        if not due_briefings:
            logger.debug("[Send Due] No briefings due")
            return SendDueResponse(
                status="success",
                briefings_sent=0,
                briefings_failed=0,
                sent_event_ids=[]
            )
        
        logger.info(f"[Send Due] Found {len(due_briefings)} due briefings")
        
        sent_count = 0
        failed_count = 0
        sent_event_ids = []
        
        for briefing in due_briefings:
            briefing_id = briefing.get("id")
            event_id = briefing.get("event_id")
            briefing_text = briefing.get("briefing_text")
            
            try:
                # Send notification
                success = await send_telegram_notification(briefing_text)
                
                if success:
                    # Mark as sent
                    db.client.table("scheduled_briefings").update({
                        "status": "sent",
                        "sent_at": now.isoformat()
                    }).eq("id", briefing_id).execute()
                    
                    sent_count += 1
                    sent_event_ids.append(event_id)
                    logger.info(f"[Send Due] Sent briefing for event {event_id}")
                else:
                    # Mark as failed
                    db.client.table("scheduled_briefings").update({
                        "status": "failed",
                        "error_message": "Telegram notification failed"
                    }).eq("id", briefing_id).execute()
                    
                    failed_count += 1
                    logger.warning(f"[Send Due] Failed to send briefing for event {event_id}")
                    
            except Exception as e:
                logger.error(f"[Send Due] Error sending briefing {briefing_id}: {e}")
                
                # Mark as failed
                db.client.table("scheduled_briefings").update({
                    "status": "failed",
                    "error_message": str(e)[:500]
                }).eq("id", briefing_id).execute()
                
                failed_count += 1
        
        return SendDueResponse(
            status="success",
            briefings_sent=sent_count,
            briefings_failed=failed_count,
            sent_event_ids=sent_event_ids
        )
        
    except Exception as e:
        logger.exception("Failed to send due briefings")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/briefings/scheduled")
async def get_scheduled_briefings(status: Optional[str] = None, limit: int = 100):
    """
    Get all scheduled briefings, optionally filtered by status.
    
    Useful for debugging and monitoring the scheduling system.
    
    Args:
        status: Filter by status ('pending', 'sent', 'failed')
        limit: Maximum number of results (default 100)
    """
    db = get_database()
    
    try:
        query = db.client.table("scheduled_briefings").select("*").order(
            "send_at", desc=False
        )
        
        if status:
            query = query.eq("status", status)
        
        result = query.limit(limit).execute()
        
        return {
            "status": "success",
            "count": len(result.data or []),
            "briefings": result.data or []
        }
        
    except Exception as e:
        logger.exception("Failed to get scheduled briefings")
        raise HTTPException(status_code=500, detail=str(e))
