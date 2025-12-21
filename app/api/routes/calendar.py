import logging
from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_database
from app.api.models import (
    CalendarEventResponse,
    CreateCalendarEventRequest,
    LinkCalendarEventRequest,
)

router = APIRouter(tags=["Calendar"])
logger = logging.getLogger("Jarvis.Intelligence.API.Calendar")


@router.post("/calendar-events", response_model=CalendarEventResponse)
async def create_calendar_event(request: CreateCalendarEventRequest) -> CalendarEventResponse:
    """Create a calendar event with CRM links."""
    db = get_database()

    try:
        logger.info("Creating calendar event %s", request.title)

        event_id, event_url = db.create_calendar_event(
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            organizer_email=request.organizer_email,
            organizer_name=request.organizer_name,
            attendees=request.attendees,
            all_day=request.all_day,
            status=request.status,
            contact_id=request.contact_id,
            contact_name=request.contact_name,
            meeting_id=request.meeting_id,
            email_id=request.email_id,
            event_type=request.event_type,
            tags=request.tags,
            meeting_url=request.meeting_url,
            is_recurring=request.is_recurring,
            recurrence_rule=request.recurrence_rule,
            source_provider=request.source_provider,
            source_event_id=request.source_event_id,
            raw_data=request.raw_data,
        )

        contact_name = None
        if request.contact_id:
            try:
                contact = (
                    db.client.table("contacts")
                    .select("first_name, last_name")
                    .eq("id", request.contact_id)
                    .single()
                    .execute()
                )
                if contact.data:
                    first_name = contact.data.get("first_name", "")
                    last_name = contact.data.get("last_name", "")
                    contact_name = f"{first_name} {last_name}".strip()
            except Exception as exc:
                logger.warning("Unable to fetch contact %s: %s", request.contact_id, exc)

        return CalendarEventResponse(
            status="success",
            event_id=event_id,
            event_url=event_url,
            contact_id=request.contact_id,
            contact_name=contact_name,
        )

    except Exception as exc:
        logger.exception("Failed creating calendar event %s", request.title)
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/calendar-events/{event_id}/link")
async def link_calendar_event(event_id: str, request: LinkCalendarEventRequest):
    """Link a calendar event to meetings or contacts."""
    db = get_database()

    try:
        logger.info("Linking calendar event %s", event_id)

        update_data: dict[str, str] = {}
        if request.meeting_id:
            db.link_calendar_event_to_meeting(event_id, request.meeting_id)
            update_data["meeting_id"] = request.meeting_id

        if request.contact_id:
            db.client.table("calendar_events").update({"contact_id": request.contact_id}).eq(
                "id", event_id
            ).execute()
            update_data["contact_id"] = request.contact_id

        return {"status": "success", "event_id": event_id, **update_data}

    except Exception as exc:
        logger.exception("Failed to link calendar event %s", event_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/calendar-events/upcoming")
async def get_upcoming_events(limit: int = 20):
    """Fetch upcoming events for the dashboard."""
    db = get_database()

    try:
        events = db.get_upcoming_events(limit=limit)
        return {
            "status": "success",
            "event_count": len(events),
            "events": events,
        }

    except Exception as exc:
        logger.exception("Failed to fetch upcoming events")
        raise HTTPException(status_code=500, detail=str(exc))
