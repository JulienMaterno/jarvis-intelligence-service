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
    beeper_messages_count: int = 0
    messaging_platforms: List[str] = None
    linkedin_url: Optional[str] = None


def is_all_day_event(event: Dict) -> bool:
    """
    Check if event is an all-day event by detecting midnight UTC time.
    
    All-day events from Google Calendar have 'date' instead of 'dateTime',
    which gets stored as T00:00:00+00:00 in our database.
    """
    start_time = event.get("start_time", "")
    return "T00:00:00" in start_time


def is_real_meeting(event: Dict) -> bool:
    """
    Determine if event is a real meeting worth briefing for.
    
    A real meeting either:
    1. Has at least one attendee besides yourself (email without 'self': True)
    2. OR title contains meeting indicators: "&", "<>", " x ", " X ", "|"
    
    Filters out:
    - Solo calendar blocks (focus time, work blocks)
    - Birthday reminders
    - Personal appointments without other people
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


def get_upcoming_events_for_briefing(
    db,
    minutes_ahead: int = 30,
    minutes_buffer: int = 5,
    include_all_day: bool = False
) -> List[Dict]:
    """
    Get calendar events starting within the specified time window.
    
    Args:
        db: Database client
        minutes_ahead: Look for events starting within this many minutes
        minutes_buffer: Don't include events that already started (buffer)
        include_all_day: If False (default), filters out all-day events
    
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
        
        events = result.data or []
        
        # Filter out all-day events unless explicitly requested
        if not include_all_day:
            events = [e for e in events if not is_all_day_event(e)]
        
        # Filter to only real meetings (with other people or meeting indicators)
        events = [e for e in events if is_real_meeting(e)]
        
        return events
    except Exception as e:
        logger.error(f"Error fetching upcoming events: {e}")
        return []


def normalize_name(name: str) -> str:
    """Normalize a name for fuzzy matching."""
    if not name:
        return ""
    # Lowercase, strip, remove common suffixes/prefixes
    name = name.lower().strip()
    # Remove common patterns like "and Aaron Pütting" from calendar titles
    for pattern in [" and aaron", " & aaron", " x aaron", " | aaron", "aaron and ", "aaron & ", "aaron x ", "aaron | "]:
        name = name.replace(pattern, "")
    return name.strip()


def names_match(name1: str, name2: str) -> bool:
    """
    Check if two names match (fuzzy).
    Handles cases like:
    - "Nick Hazell" vs "Nick Hazell" (exact)
    - "Nick" vs "Nick Hazell" (partial - first name)
    - "Minh Cao" vs "Minh" (partial)
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False

    # Exact match
    if n1 == n2:
        return True

    # One contains the other (for partial names)
    if n1 in n2 or n2 in n1:
        return True

    # First name match (first word)
    n1_first = n1.split()[0] if n1.split() else ""
    n2_first = n2.split()[0] if n2.split() else ""
    if n1_first and n2_first and n1_first == n2_first:
        # Also check last name if available
        n1_parts = n1.split()
        n2_parts = n2.split()
        if len(n1_parts) > 1 and len(n2_parts) > 1:
            # Both have last names - check if they match too
            return n1_parts[-1] == n2_parts[-1]
        # Only first name available on one side - accept the match
        return True

    return False


def find_beeper_chat_by_name(db, name: str) -> Optional[Dict]:
    """
    Find a Beeper chat by fuzzy name matching.

    Searches chat_name and remote_user_name in beeper_chats.
    Returns the best matching chat (most recent activity).

    Args:
        db: Database client
        name: Person's name to search for

    Returns: Best matching beeper_chat record or None
    """
    if not name:
        return None

    normalized = normalize_name(name)
    if not normalized:
        return None

    try:
        # Get recent chats that might match
        # We search for chats where chat_name or remote_user_name contains parts of the name
        # Using ilike for case-insensitive partial match
        first_name = normalized.split()[0] if normalized.split() else normalized

        result = db.client.table("beeper_chats").select(
            "id, beeper_chat_id, platform, chat_name, remote_user_name, last_message_at, needs_response"
        ).or_(
            f"chat_name.ilike.%{first_name}%,remote_user_name.ilike.%{first_name}%"
        ).order(
            "last_message_at", desc=True
        ).limit(20).execute()

        if not result.data:
            return None

        # Find the best match using fuzzy matching
        for chat in result.data:
            chat_name = chat.get("chat_name", "")
            remote_name = chat.get("remote_user_name", "")

            if names_match(name, chat_name) or names_match(name, remote_name):
                logger.info(f"Found Beeper chat for '{name}': {chat_name} ({chat.get('platform')})")
                return chat

        return None
    except Exception as e:
        logger.error(f"Error finding Beeper chat for name '{name}': {e}")
        return None


def lookup_contact_with_linkedin_by_name(db, name: str) -> Optional[Dict]:
    """
    Look up a contact with LinkedIn data by searching by name.
    Used for "first meeting" cases where we might have LinkedIn data
    even without a saved contact link on the calendar event.

    Args:
        db: Database client
        name: Person's name to search

    Returns:
        Contact dict with linkedin_data if found, None otherwise
    """
    if not name:
        return None

    normalized = normalize_name(name)
    if not normalized:
        return None

    parts = normalized.split()
    first_name = parts[0]
    last_name = parts[-1] if len(parts) > 1 else None

    try:
        # Search contacts - prioritize those with linkedin_data
        if last_name and first_name != last_name:
            # Try exact first + last name match
            result = db.client.table("contacts").select(
                "id, first_name, last_name, company, job_title, linkedin_url, linkedin_data"
            ).ilike(
                "first_name", first_name
            ).ilike(
                "last_name", last_name
            ).is_(
                "deleted_at", "null"
            ).limit(1).execute()

            if result.data:
                return result.data[0]

        # Fallback: first name only (if unique)
        result = db.client.table("contacts").select(
            "id, first_name, last_name, company, job_title, linkedin_url, linkedin_data"
        ).ilike(
            "first_name", first_name
        ).is_(
            "deleted_at", "null"
        ).limit(5).execute()

        if result.data:
            # Find best match
            for contact in result.data:
                contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                if names_match(name, contact_name):
                    return contact

            # If only one result, return it
            if len(result.data) == 1:
                return result.data[0]

        return None
    except Exception as e:
        logger.error(f"Error looking up contact by name '{name}': {e}")
        return None


def format_linkedin_summary(linkedin_data: Dict, company: str = None, job_title: str = None) -> str:
    """
    Format LinkedIn profile data into a concise summary for briefings.
    Used for "first meeting" cases where we have LinkedIn data but no prior history.

    Args:
        linkedin_data: The linkedin_data JSONB from contacts table
        company: Company from contact record (fallback)
        job_title: Job title from contact record (fallback)

    Returns:
        Formatted string summary, or empty string if no useful data
    """
    parts = []

    # Current role - prefer linkedin_data, fall back to contact fields
    li_company = None
    if linkedin_data and isinstance(linkedin_data, dict):
        li_company = linkedin_data.get('current_company_name')

    if li_company:
        parts.append(f"at {li_company}")
    elif company:
        parts.append(f"at {company}")

    # Location
    if linkedin_data and isinstance(linkedin_data, dict):
        location = linkedin_data.get('location') or linkedin_data.get('city')
        if location:
            parts.append(f"in {location}")

    # Education (brief)
    if linkedin_data and isinstance(linkedin_data, dict):
        education = linkedin_data.get('educations_details')
        if education:
            # Truncate long education strings
            edu_short = education[:60] + "..." if len(education) > 60 else education
            parts.append(f"({edu_short})")

    # Recent activity - most valuable for conversation starters
    if linkedin_data and isinstance(linkedin_data, dict):
        activity = linkedin_data.get('activity', [])
        if activity and len(activity) > 0:
            recent = activity[0]
            title = recent.get('title', '')
            if title:
                # Truncate and clean
                title_short = title[:70] + "..." if len(title) > 70 else title
                parts.append(f"Recent: \"{title_short}\"")

    return " | ".join(parts) if parts else ""


def get_beeper_messages_by_chat_id(db, beeper_chat_id: str, limit: int = 20) -> List[Dict]:
    """
    Get Beeper messages by chat ID (not contact ID).

    Args:
        db: Database client
        beeper_chat_id: The Beeper chat identifier
        limit: Maximum messages to return

    Returns: List of messages
    """
    try:
        result = db.client.table("beeper_messages").select(
            "content, platform, is_outgoing, timestamp, sender_name, message_type"
        ).eq(
            "beeper_chat_id", beeper_chat_id
        ).order(
            "timestamp", desc=True
        ).limit(limit).execute()

        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching Beeper messages for chat {beeper_chat_id}: {e}")
        return []


def get_beeper_messages_for_contact(db, contact_id: str, limit: int = 20) -> List[Dict]:
    """
    Get recent Beeper messages (WhatsApp, LinkedIn, etc.) with a contact.

    Args:
        db: Database client
        contact_id: Contact UUID
        limit: Maximum number of messages to return

    Returns: List of recent Beeper messages with platform info
    """
    try:
        # Get messages linked to this contact
        result = db.client.table("beeper_messages").select(
            "content, platform, is_outgoing, timestamp, sender_name, message_type"
        ).eq(
            "contact_id", contact_id
        ).order(
            "timestamp", desc=True
        ).limit(limit).execute()

        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching Beeper messages for contact {contact_id}: {e}")
        return []


def get_beeper_chats_for_contact(db, contact_id: str) -> List[Dict]:
    """
    Get Beeper chat info for a contact (shows which platforms they're on).

    Args:
        db: Database client
        contact_id: Contact UUID

    Returns: List of Beeper chats with this contact
    """
    try:
        result = db.client.table("beeper_chats").select(
            "platform, chat_name, last_message_at, last_message_preview, last_message_is_outgoing, needs_response"
        ).eq(
            "contact_id", contact_id
        ).order(
            "last_message_at", desc=True
        ).execute()

        return result.data or []
    except Exception as e:
        logger.error(f"Error fetching Beeper chats for contact {contact_id}: {e}")
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
        Dict with contact info, previous meetings, emails, calendar events, Beeper messages, and open items
    """
    context = {
        "contact": None,
        "previous_meetings": [],
        "last_meeting": None,
        "open_tasks": [],
        "notes": [],
        "recent_emails": [],
        "previous_events": [],
        "beeper_messages": [],
        "beeper_chats": []
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
        
        # Get recent Beeper messages (WhatsApp, LinkedIn, etc.)
        context["beeper_messages"] = get_beeper_messages_for_contact(db, contact_id, limit=20)
        context["beeper_chats"] = get_beeper_chats_for_contact(db, contact_id)
        
        return context
        
    except Exception as e:
        logger.error(f"Error getting contact context for {contact_id}: {e}")
        return context


def generate_briefing_with_llm(
    llm,
    event: Dict,
    contact_context: Dict[str, Any],
    memory_context: str = ""
) -> str:
    """
    Use Claude to generate a personalized meeting briefing.
    
    Args:
        llm: LLM client
        event: Calendar event dict
        contact_context: Dict with contact info, meetings, emails, etc.
        memory_context: Optional AI memory context string
    """
    contact = contact_context.get("contact") or {}
    previous_meetings = contact_context.get("previous_meetings", [])
    last_meeting = contact_context.get("last_meeting")
    open_tasks = contact_context.get("open_tasks", [])
    recent_emails = contact_context.get("recent_emails", [])
    previous_events = contact_context.get("previous_events", [])
    beeper_messages = contact_context.get("beeper_messages", [])
    beeper_chats = contact_context.get("beeper_chats", [])
    
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
        # Add LinkedIn profile data if available
        linkedin_data = contact.get('linkedin_data')
        if linkedin_data and isinstance(linkedin_data, dict):
            contact_info += "\nLINKEDIN PROFILE:\n"
            if linkedin_data.get('current_company_name'):
                contact_info += f"- Current Company: {linkedin_data.get('current_company_name')}\n"
            if linkedin_data.get('location'):
                contact_info += f"- Location: {linkedin_data.get('location')}\n"
            if linkedin_data.get('educations_details'):
                contact_info += f"- Education: {linkedin_data.get('educations_details')}\n"
            # Add recent activity (shows what they're interested in)
            activity = linkedin_data.get('activity', [])
            if activity:
                contact_info += "- Recent LinkedIn activity:\n"
                for act in activity[:3]:
                    title = act.get('title', '')[:100]
                    if title:
                        contact_info += f"  • {title}\n"
    
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
    
    # Beeper messages (WhatsApp, LinkedIn, etc.)
    messaging_history = ""
    if beeper_messages:
        messaging_history = "RECENT MESSAGES (WhatsApp/LinkedIn/etc.):\n"
        for i, msg in enumerate(beeper_messages[:10], 1):
            ts = msg.get('timestamp', 'Unknown')[:16] if msg.get('timestamp') else 'Unknown'
            platform = msg.get('platform', 'unknown').upper()
            direction = "YOU" if msg.get('is_outgoing') else "THEM"
            content = msg.get('content', '[media]')[:200] if msg.get('content') else '[media/voice]'
            messaging_history += f"{i}. [{ts}] [{platform}] {direction}: {content}\n"
    
    # Add which platforms they're on
    if beeper_chats:
        platforms = list(set(chat.get('platform', '').lower() for chat in beeper_chats if chat.get('platform')))
        if platforms:
            messaging_history += f"\nActive on: {', '.join(platforms)}\n"
        # Check if any chat needs response
        pending = [chat for chat in beeper_chats if chat.get('needs_response')]
        if pending:
            messaging_history += f"⚠️ Pending response on: {', '.join(p.get('platform', '') for p in pending)}\n"
    
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
    
    # Format attendees - they're dicts with email/displayName
    attendees = event.get('attendees', []) or []
    if attendees:
        attendee_names = []
        for a in attendees:
            if isinstance(a, dict):
                name = a.get('displayName') or a.get('email', 'Unknown')
                attendee_names.append(name)
            else:
                attendee_names.append(str(a))
        attendees_str = ', '.join(attendee_names) if attendee_names else 'Unknown'
    else:
        attendees_str = 'Unknown'
    
    # Check if we have any meaningful history
    has_history = bool(previous_meetings or recent_emails or beeper_messages or previous_events or open_tasks or memory_context.strip())

    # Check for LinkedIn contact (for first meeting scenarios)
    linkedin_contact = contact_context.get("linkedin_contact")
    has_linkedin = bool(linkedin_contact and linkedin_contact.get("linkedin_data"))

    if not has_history:
        # No history - check if we have LinkedIn data for first meeting context
        if has_linkedin:
            linkedin_summary = format_linkedin_summary(
                linkedin_contact.get("linkedin_data"),
                linkedin_contact.get("company"),
                linkedin_contact.get("job_title")
            )
            if linkedin_summary:
                return f"First meeting. {linkedin_summary}"
        # No history and no LinkedIn - signal to use simple message
        return None

    prompt = f"""Generate a meeting briefing focusing on what was discussed LAST TIME so I know where to continue.

{contact_info}

{meeting_history}

{email_history}

{messaging_history}

{event_history}

{open_items}

FOCUS ON:
1. What we discussed in the LAST meeting/conversation (most important!)
2. Any recent messages or emails with substantive content
3. Open items or follow-ups from previous discussions
4. Key topics to potentially continue

STRICT RULES:
1. ONLY state facts explicitly written in the data above
2. If emails are just scheduling (confirming times, calendar invites), ignore them
3. NEVER invent names, topics, projects, or connections not in the data
4. Prioritize the most RECENT substantive interaction
5. Maximum 120 words
6. If nothing substantive found, write "First substantive conversation."

Output format:
- Start with what we discussed last time
- Then any relevant recent context
- Keep it actionable and concise"""

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
    event: Dict,
    memory_service=None
) -> Optional[MeetingBriefing]:
    """
    Generate a complete meeting briefing for an event.
    
    Args:
        db: Database client
        llm: LLM client (ClaudeMultiAnalyzer)
        event: Calendar event dict
        memory_service: Optional MemoryService for AI memories
    
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
            except Exception:
                continue  # Contact not found or DB error

    # Extract name from event title or attendees for Beeper lookup
    # This helps find chat history even without a saved contact
    person_name_for_beeper = None
    if not contact_id:
        # Try to extract name from calendar title (e.g., "Nick Hazell and Aaron Pütting")
        title = event_title or ""
        # Remove common patterns to extract the other person's name
        # Include variations with Pütting/Putting surname
        patterns_to_remove = [
            " and Aaron Pütting", " and Aaron Putting", " and Aaron",
            " & Aaron Pütting", " & Aaron Putting", " & Aaron",
            " x Aaron Pütting", " x Aaron Putting", " x Aaron",
            " | Aaron Pütting", " | Aaron Putting", " | Aaron",
            "Aaron Pütting and ", "Aaron Putting and ", "Aaron and ",
            "Aaron Pütting & ", "Aaron Putting & ", "Aaron & ",
            "Aaron Pütting x ", "Aaron Putting x ", "Aaron x ",
            "Aaron Pütting | ", "Aaron Putting | ", "Aaron | ",
        ]
        for pattern in patterns_to_remove:
            if pattern.lower() in title.lower():
                person_name_for_beeper = title.lower().replace(pattern.lower(), "").strip()
                # Capitalize first letter of each word
                person_name_for_beeper = " ".join(w.capitalize() for w in person_name_for_beeper.split())
                break

        # If no name from title, try attendee displayName
        if not person_name_for_beeper:
            attendees_data = event.get("attendees") or []
            for att in attendees_data:
                if isinstance(att, dict) and not att.get("self"):
                    display_name = att.get("displayName")
                    if display_name:
                        person_name_for_beeper = display_name
                        break

        # Set contact_name for display even without a contact record
        if person_name_for_beeper and not contact_name:
            contact_name = person_name_for_beeper

    # If no contact found, try to find Beeper chat by name
    beeper_chat_match = None
    if not contact_id and person_name_for_beeper:
        beeper_chat_match = find_beeper_chat_by_name(db, person_name_for_beeper)
        if beeper_chat_match:
            logger.info(f"Found Beeper chat for '{person_name_for_beeper}' without contact record")
            # Get messages from this chat
            beeper_chat_id = beeper_chat_match.get("beeper_chat_id")
            if beeper_chat_id:
                contact_context["beeper_messages"] = get_beeper_messages_by_chat_id(db, beeper_chat_id, limit=20)
                contact_context["beeper_chats"] = [beeper_chat_match]

    # If no contact found, also try to find emails by attendee email directly
    if not contact_id and attendees:
        for attendee_email in attendees:
            # Skip own email
            if "aaron" in attendee_email.lower() or "putting" in attendee_email.lower():
                continue
            try:
                email_result = db.client.table("emails").select(
                    "id, subject, sender, recipient, date, snippet, body_text"
                ).or_(
                    f"sender.ilike.%{attendee_email}%,recipient.ilike.%{attendee_email}%"
                ).order(
                    "date", desc=True
                ).limit(10).execute()

                if email_result.data:
                    contact_context["recent_emails"] = email_result.data
                    logger.info(f"Found {len(email_result.data)} emails for attendee {attendee_email}")
                    break
            except Exception as e:
                logger.warning(f"Error fetching emails for attendee {attendee_email}: {e}")

    # If still no contact found, try to find a contact with LinkedIn data by name
    # This helps provide context for "first meeting" scenarios
    linkedin_contact = None
    if not contact_id and person_name_for_beeper:
        linkedin_contact = lookup_contact_with_linkedin_by_name(db, person_name_for_beeper)
        if linkedin_contact:
            logger.info(f"Found contact with LinkedIn data for '{person_name_for_beeper}': {linkedin_contact.get('first_name')} {linkedin_contact.get('last_name')}")
            # Store in contact_context for use in briefing generation
            contact_context["linkedin_contact"] = linkedin_contact

    # Memory context disabled for now - it was returning unrelated memories
    # and causing the LLM to hallucinate connections
    memory_context = ""

    # Generate briefing text
    briefing_text = generate_briefing_with_llm(llm, event, contact_context, memory_context)

    # If None, there's no history and no LinkedIn - skip this briefing
    if briefing_text is None:
        logger.info(f"Skipping briefing for '{event_title}' - no prior interactions or LinkedIn data")
        return None
    
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
    
    # Get Beeper/messaging info
    beeper_messages = contact_context.get("beeper_messages", [])
    beeper_chats = contact_context.get("beeper_chats", [])
    messaging_platforms = list(set(chat.get('platform', '') for chat in beeper_chats if chat.get('platform')))

    # Get LinkedIn URL from contact (or linkedin_contact for first meetings)
    contact_data = contact_context.get("contact") or {}
    linkedin_url = contact_data.get("linkedin_url")

    # If no LinkedIn URL from main contact, try linkedin_contact (found by name)
    if not linkedin_url:
        linkedin_contact = contact_context.get("linkedin_contact")
        if linkedin_contact:
            linkedin_url = linkedin_contact.get("linkedin_url")

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
        previous_events_count=len(contact_context.get("previous_events", [])),
        beeper_messages_count=len(beeper_messages),
        messaging_platforms=messaging_platforms or None,
        linkedin_url=linkedin_url
    )


def format_briefing_for_telegram(briefing: MeetingBriefing) -> str:
    """Format a briefing for Telegram notification."""
    lines = [
        f"📅 *{briefing.event_title}*",
    ]

    if briefing.contact_name:
        company_part = f" ({briefing.contact_company})" if briefing.contact_company else ""
        lines.append(f"👤 {briefing.contact_name}{company_part}")

    # Add LinkedIn link if available
    if briefing.linkedin_url:
        lines.append(f"🔗 [LinkedIn]({briefing.linkedin_url})")

    lines.append("")
    lines.append(briefing.briefing_text)

    return "\n".join(lines)
