"""
Meeting Briefing Feature

Generates pre-meeting briefings by:
1. Checking upcoming calendar events
2. Looking up the contact for each meeting
3. Finding previous meetings/interactions with that contact
4. Fetching recent emails with the contact
5. Getting previous calendar events with the contact
6. Using Claude to generate a personalized briefing

The briefing includes:
- What you discussed last time
- Recent email exchanges
- Upcoming/past calendar events
- Suggested conversation topics
- Key information about the contact
- Any follow-ups or open items
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger("Jarvis.Intelligence.Briefing")


@dataclass
class MeetingBriefing:
    """Data class for a meeting briefing."""
    event_id: str
    event_title: str
    event_start: str
    contact_id: Optional[str]
    contact_name: Optional[str]
    contact_company: Optional[str]
    previous_meetings_count: int
    last_meeting_date: Optional[str]
    last_meeting_summary: Optional[str]
    suggested_topics: List[str]
    open_items: List[str]
    briefing_text: str
    attendees: List[str]
    recent_emails_count: int = 0
    previous_events_count: int = 0


def get_upcoming_events_for_briefing(
    db,
    minutes_ahead: int = 30,
    minutes_buffer: int = 5
) -> List[Dict]:
    """
    Get calendar events starting within the specified time window.
    
    Args:
        db: Database client
        minutes_ahead: Look for events starting within this many minutes
        minutes_buffer: Don't include events that already started (buffer)
    
    Returns: List of calendar events needing briefings
    """
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=minutes_buffer)
    window_end = now + timedelta(minutes=minutes_ahead)
    
    try:
        result = db.client.table("calendar_events").select("*").gte(
            "start_time", window_start.isoformat()
        ).lte(
            "start_time", window_end.isoformat()
        ).neq(
            "status", "cancelled"
        ).order(
            "start_time", desc=False
        ).execute()
        
        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching upcoming events: {e}")
        return []


def get_emails_for_contact(db, contact_id: str, contact_email: str = None, limit: int = 10) -> List[Dict]:
    """
    Get recent emails with a contact.
    
    Args:
        db: Database client
        contact_id: Contact UUID
        contact_email: Contact's email address (for fallback search)
        limit: Maximum number of emails to return
    
    Returns: List of recent emails
    """
    try:
        # First try by contact_id
        result = db.client.table("emails").select("*").eq(
            "contact_id", contact_id
        ).order(
            "date", desc=True
        ).limit(limit).execute()
        
        if result.data:
            return result.data
        
        # Fallback: search by email address in sender/recipient
        if contact_email:
            result = db.client.table("emails").select("*").or_(
                f"sender.ilike.%{contact_email}%,recipient.ilike.%{contact_email}%"
            ).order(
                "date", desc=True
            ).limit(limit).execute()
            
            return result.data or []
        
        return []
    except Exception as e:
        logger.error(f"Error fetching emails for contact {contact_id}: {e}")
        return []


def get_calendar_events_for_contact(db, contact_id: str, contact_email: str = None, limit: int = 10) -> List[Dict]:
    """
    Get previous calendar events with a contact.
    
    Args:
        db: Database client
        contact_id: Contact UUID
        contact_email: Contact's email address (for attendee search)
        limit: Maximum number of events to return
    
    Returns: List of past calendar events
    """
    now = datetime.now(timezone.utc)
    
    try:
        # Get events linked to this contact
        result = db.client.table("calendar_events").select("*").eq(
            "contact_id", contact_id
        ).lt(
            "start_time", now.isoformat()
        ).neq(
            "status", "cancelled"
        ).order(
            "start_time", desc=True
        ).limit(limit).execute()
        
        if result.data:
            return result.data
        
        # Fallback: search in attendees JSON if email provided
        # Note: This is a simple approach - JSONB queries can be more complex
        if contact_email:
            # Get all past events and filter by attendee email
            all_events = db.client.table("calendar_events").select("*").lt(
                "start_time", now.isoformat()
            ).neq(
                "status", "cancelled"
            ).order(
                "start_time", desc=True
            ).limit(50).execute()
            
            matched = []
            for event in (all_events.data or []):
                attendees = event.get("attendees") or []
                if isinstance(attendees, list):
                    for att in attendees:
                        att_email = att.get("email", str(att)) if isinstance(att, dict) else str(att)
                        if contact_email.lower() in att_email.lower():
                            matched.append(event)
                            break
                if len(matched) >= limit:
                    break
            
            return matched
        
        return []
    except Exception as e:
        logger.error(f"Error fetching calendar events for contact {contact_id}: {e}")
        return []


def get_contact_context(db, contact_id: str) -> Dict[str, Any]:
    """
    Get comprehensive context about a contact for briefing.
    
    Returns:
        Dict with contact info, previous meetings, emails, calendar events, and open items
    """
    context = {
        "contact": None,
        "previous_meetings": [],
        "last_meeting": None,
        "open_tasks": [],
        "notes": [],
        "recent_emails": [],
        "previous_events": []
    }
    
    try:
        # Get contact details
        contact_result = db.client.table("contacts").select("*").eq(
            "id", contact_id
        ).single().execute()
        
        if contact_result.data:
            context["contact"] = contact_result.data
            contact_email = contact_result.data.get("email")
        else:
            contact_email = None
        
        # Get previous meetings (most recent first)
        meetings_result = db.client.table("meetings").select("*").eq(
            "contact_id", contact_id
        ).is_(
            "deleted_at", "null"
        ).order(
            "date", desc=True
        ).limit(10).execute()
        
        if meetings_result.data:
            context["previous_meetings"] = meetings_result.data
            context["last_meeting"] = meetings_result.data[0] if meetings_result.data else None
        
        # Get open tasks related to this contact's meetings
        if context["previous_meetings"]:
            meeting_ids = [m["id"] for m in context["previous_meetings"]]
            tasks_result = db.client.table("tasks").select("*").in_(
                "origin_id", meeting_ids
            ).neq(
                "status", "Done"
            ).is_(
                "deleted_at", "null"
            ).execute()
            
            if tasks_result.data:
                context["open_tasks"] = tasks_result.data
        
        # Get recent emails with this contact
        context["recent_emails"] = get_emails_for_contact(db, contact_id, contact_email, limit=10)
        
        # Get previous calendar events with this contact
        context["previous_events"] = get_calendar_events_for_contact(db, contact_id, contact_email, limit=10)
        
        return context
        
    except Exception as e:
        logger.error(f"Error getting contact context for {contact_id}: {e}")
        return context


def generate_briefing_with_llm(
    llm,
    event: Dict,
    contact_context: Dict[str, Any]
) -> str:
    """
    Use Claude to generate a personalized meeting briefing.
    """
    contact = contact_context.get("contact") or {}
    previous_meetings = contact_context.get("previous_meetings", [])
    last_meeting = contact_context.get("last_meeting")
    open_tasks = contact_context.get("open_tasks", [])
    recent_emails = contact_context.get("recent_emails", [])
    previous_events = contact_context.get("previous_events", [])
    
    # Build context for the LLM
    contact_info = ""
    if contact:
        contact_info = f"""
CONTACT INFORMATION:
- Name: {contact.get('first_name', '')} {contact.get('last_name', '')}
- Company: {contact.get('company', 'Unknown')}
- Job Title: {contact.get('job_title', 'Unknown')}
- Notes: {contact.get('notes', 'None')}
"""
    
    meeting_history = ""
    if previous_meetings:
        meeting_history = "PREVIOUS MEETINGS (Voice Memos):\n"
        for i, m in enumerate(previous_meetings[:5], 1):
            date = m.get('date', 'Unknown date')
            title = m.get('title', 'Untitled')
            summary = m.get('summary', 'No summary')[:500]  # Truncate long summaries
            meeting_history += f"{i}. [{date}] {title}\n   Summary: {summary}\n\n"
    
    # Email history
    email_history = ""
    if recent_emails:
        email_history = "RECENT EMAIL EXCHANGES:\n"
        for i, e in enumerate(recent_emails[:5], 1):
            date = e.get('date', 'Unknown')[:10] if e.get('date') else 'Unknown'
            subject = e.get('subject', 'No subject')[:100]
            sender = e.get('sender', 'Unknown')
            snippet = e.get('snippet', e.get('body_preview', ''))[:200]
            direction = "FROM" if contact.get('email', '').lower() in sender.lower() else "TO"
            email_history += f"{i}. [{date}] {direction} them - {subject}\n   Preview: {snippet}...\n\n"
    
    # Calendar event history
    event_history = ""
    if previous_events:
        event_history = "PREVIOUS CALENDAR EVENTS:\n"
        for i, ev in enumerate(previous_events[:5], 1):
            start = ev.get('start_time', 'Unknown')[:10] if ev.get('start_time') else 'Unknown'
            summary = ev.get('summary', 'Untitled event')[:100]
            location = ev.get('location', '')
            loc_str = f" @ {location}" if location else ""
            event_history += f"{i}. [{start}] {summary}{loc_str}\n"
    
    open_items = ""
    if open_tasks:
        open_items = "OPEN TASKS/FOLLOW-UPS:\n"
        for task in open_tasks[:5]:
            open_items += f"- {task.get('title', 'Untitled task')}\n"
    
    prompt = f"""You are a helpful personal assistant preparing a meeting briefing.

UPCOMING MEETING:
- Title: {event.get('summary', event.get('title', 'Meeting'))}
- Time: {event.get('start_time', 'Unknown')}
- Attendees: {', '.join(event.get('attendees', []) or ['Unknown'])}

{contact_info}

{meeting_history}

{email_history}

{event_history}

{open_items}

Generate a brief, actionable meeting briefing. Include:
1. A quick reminder of your relationship with this person (if any history)
2. What you discussed in your last meeting or recent emails (if applicable)
3. Recent communication patterns (emails, past calendar events)
4. 2-3 suggested conversation topics or questions to ask
5. Any follow-ups you should mention

Keep it concise and practical. Use bullet points. No more than 250 words.
If there's no history with this person, focus on suggested ice-breakers based on any available info."""

    try:
        response = llm.client.messages.create(
            model=llm.model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Error generating briefing with LLM: {e}")
        return generate_fallback_briefing(event, contact_context)


def generate_fallback_briefing(event: Dict, contact_context: Dict) -> str:
    """Generate a simple briefing without LLM if it fails."""
    contact = contact_context.get("contact") or {}
    last_meeting = contact_context.get("last_meeting")
    recent_emails = contact_context.get("recent_emails", [])
    previous_events = contact_context.get("previous_events", [])
    
    lines = [f"📅 **Upcoming: {event.get('summary', event.get('title', 'Meeting'))}**"]
    
    if contact:
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        company = contact.get('company')
        if name:
            lines.append(f"👤 With: {name}" + (f" ({company})" if company else ""))
    
    if last_meeting:
        lines.append(f"\n📋 Last meeting: {last_meeting.get('date', 'Unknown')}")
        if last_meeting.get('summary'):
            lines.append(f"Summary: {last_meeting['summary'][:200]}...")
    
    if recent_emails:
        lines.append(f"\n📧 Recent emails: {len(recent_emails)} exchanges")
        latest = recent_emails[0]
        lines.append(f"Latest: {latest.get('subject', 'No subject')[:50]}")
    
    if previous_events:
        lines.append(f"\n📆 Past events: {len(previous_events)} calendar events together")
    
    open_tasks = contact_context.get("open_tasks", [])
    if open_tasks:
        lines.append("\n⚠️ Open follow-ups:")
        for task in open_tasks[:3]:
            lines.append(f"  • {task.get('title', 'Task')}")
    
    return "\n".join(lines)


async def generate_meeting_briefing(
    db,
    llm,
    event: Dict
) -> Optional[MeetingBriefing]:
    """
    Generate a complete meeting briefing for an event.
    
    Args:
        db: Database client
        llm: LLM client (ClaudeMultiAnalyzer)
        event: Calendar event dict
    
    Returns: MeetingBriefing object or None if briefing can't be generated
    """
    event_id = event.get("id")
    event_title = event.get("summary") or event.get("title", "Meeting")
    contact_id = event.get("contact_id")
    
    # Parse attendees
    attendees = []
    attendees_data = event.get("attendees")
    if attendees_data:
        if isinstance(attendees_data, list):
            for a in attendees_data:
                if isinstance(a, dict):
                    attendees.append(a.get("email", str(a)))
                else:
                    attendees.append(str(a))
        elif isinstance(attendees_data, str):
            attendees = [attendees_data]
    
    # Get contact context
    contact_context = {}
    contact_name = None
    contact_company = None
    
    if contact_id:
        contact_context = get_contact_context(db, contact_id)
        contact = contact_context.get("contact")
        if contact:
            contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            contact_company = contact.get("company")
    
    # Try to find contact from attendees if not linked
    if not contact_id and attendees:
        for attendee_email in attendees:
            try:
                contact_result = db.client.table("contacts").select("id, first_name, last_name, company").eq(
                    "email", attendee_email
                ).single().execute()
                
                if contact_result.data:
                    contact_id = contact_result.data["id"]
                    contact_name = f"{contact_result.data.get('first_name', '')} {contact_result.data.get('last_name', '')}".strip()
                    contact_company = contact_result.data.get("company")
                    contact_context = get_contact_context(db, contact_id)
                    break
            except:
                continue
    
    # Generate briefing text
    briefing_text = generate_briefing_with_llm(llm, event, contact_context)
    
    # Extract suggested topics and open items
    suggested_topics = []
    open_items = []
    
    open_tasks = contact_context.get("open_tasks", [])
    for task in open_tasks[:3]:
        open_items.append(task.get("title", "Follow-up item"))
    
    # Get last meeting info
    last_meeting = contact_context.get("last_meeting")
    last_meeting_date = last_meeting.get("date") if last_meeting else None
    last_meeting_summary = last_meeting.get("summary") if last_meeting else None
    
    return MeetingBriefing(
        event_id=event_id,
        event_title=event_title,
        event_start=event.get("start_time", ""),
        contact_id=contact_id,
        contact_name=contact_name,
        contact_company=contact_company,
        previous_meetings_count=len(contact_context.get("previous_meetings", [])),
        last_meeting_date=last_meeting_date,
        last_meeting_summary=last_meeting_summary[:300] if last_meeting_summary else None,
        suggested_topics=suggested_topics,
        open_items=open_items,
        briefing_text=briefing_text,
        attendees=attendees,
        recent_emails_count=len(contact_context.get("recent_emails", [])),
        previous_events_count=len(contact_context.get("previous_events", []))
    )


def format_briefing_for_telegram(briefing: MeetingBriefing) -> str:
    """Format a briefing for Telegram notification."""
    lines = [
        f"🔔 *Meeting in 15 minutes*",
        f"📅 *{briefing.event_title}*",
    ]
    
    if briefing.contact_name:
        company_part = f" ({briefing.contact_company})" if briefing.contact_company else ""
        lines.append(f"👤 With: {briefing.contact_name}{company_part}")
    
    if briefing.previous_meetings_count > 0:
        lines.append(f"📊 Previous meetings: {briefing.previous_meetings_count}")
        if briefing.last_meeting_date:
            lines.append(f"📆 Last met: {briefing.last_meeting_date}")
    
    lines.append("")
    lines.append(briefing.briefing_text)
    
    return "\n".join(lines)
