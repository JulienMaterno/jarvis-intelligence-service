import json
import logging
import os
import re
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Set

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import the new enhanced analysis module
from app.features.journaling.evening_analysis import (
    analyze_day_for_journal,
    JournalAnalysisRequest,
    JournalAnalysisResponse,
    ActivityData,
)

router = APIRouter(tags=["Journaling"])
logger = logging.getLogger("Jarvis.Intelligence.API.Journaling")

MODEL_ID = os.getenv("CLAUDE_JOURNAL_MODEL", "claude-sonnet-4-5-20250929")
MAX_LIST_ITEMS = 10


# =============================================================================
# LEGACY MODELS (for backwards compatibility)
# =============================================================================

class LegacyActivityData(BaseModel):
    """Legacy activity data model for backwards compatibility."""
    meetings: List[dict] = Field(default_factory=list)
    calendar_events: List[dict] = Field(default_factory=list)
    emails: List[dict] = Field(default_factory=list)
    tasks_completed: List[dict] = Field(default_factory=list)
    tasks_created: List[dict] = Field(default_factory=list)
    reflections: List[dict] = Field(default_factory=list)
    journals: List[dict] = Field(default_factory=list)
    screen_time: Optional[dict] = None
    reading: Optional[dict] = None
    highlights: List[dict] = Field(default_factory=list)


class JournalPromptRequest(BaseModel):
    """Request for evening journal prompt - supports both legacy and new format."""
    activity_data: LegacyActivityData
    user_name: Optional[str] = None
    timezone: str = "UTC"


class JournalPromptResponse(BaseModel):
    """Response with evening journal prompt."""
    status: str
    highlights: List[str] = Field(default_factory=list)
    reflection_prompts: List[str] = Field(default_factory=list)  # Legacy name
    reflection_questions: List[str] = Field(default_factory=list)  # New name
    observations: List[str] = Field(default_factory=list)
    people_summary: str = ""
    message: str = ""
    journal_content: str = ""


# =============================================================================
# NEW ENHANCED ENDPOINT
# =============================================================================

@router.post("/journal/evening-analysis", response_model=JournalAnalysisResponse)
async def generate_evening_analysis(request: JournalAnalysisRequest) -> JournalAnalysisResponse:
    """
    NEW ENHANCED ENDPOINT: Generate comprehensive evening journal analysis.
    
    This endpoint analyzes all daily activities and generates:
    - Key highlights from the day
    - Thoughtful reflection questions based on specific events
    - Observations and patterns noticed
    - Auto-generated journal content
    - Formatted Telegram message
    """
    try:
        return analyze_day_for_journal(request)
    except Exception as exc:
        logger.exception("Failed to generate evening analysis")
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# LEGACY ENDPOINT (maintained for backwards compatibility)
# =============================================================================


def _limit_items(items: Sequence[str], limit: int = MAX_LIST_ITEMS) -> List[str]:
    return [item for item in items if item][:limit]


def _format_people_summary(names: Iterable[str]) -> str:
    deduped = sorted({name.strip() for name in names if name and name.strip()})
    return ", ".join(deduped[:MAX_LIST_ITEMS]) if deduped else "No direct contacts captured"


def _collect_activity_context(request: JournalPromptRequest) -> tuple[str, Set[str]]:
    context_parts: list[str] = []
    people_mentioned: Set[str] = set()
    activity_data = request.activity_data

    if activity_data.meetings:
        meeting_summaries: list[str] = []
        for meeting in activity_data.meetings:
            title = meeting.get("title") or "Untitled meeting"
            summary = meeting.get("summary", "")
            trimmed = summary[:200] if summary else ""
            meeting_summaries.append(f"- {title}: {trimmed}".rstrip())
            for name in meeting.get("people_mentioned", []) or []:
                if isinstance(name, str):
                    people_mentioned.add(name)
        context_parts.append(
            f"MEETINGS ({len(activity_data.meetings)}):\n" + "\n".join(meeting_summaries)
        )

    if activity_data.calendar_events:
        event_summaries: list[str] = []
        for event in activity_data.calendar_events:
            title = event.get("summary") or event.get("title") or "Calendar event"
            event_summaries.append(f"- {title}")
            for attendee in event.get("attendees", []) or []:
                display = attendee.get("displayName") if isinstance(attendee, dict) else None
                if display:
                    people_mentioned.add(display)
        context_parts.append(
            f"CALENDAR EVENTS ({len(activity_data.calendar_events)}):\n" + "\n".join(event_summaries)
        )

    if activity_data.emails:
        skip_keywords = {"unsubscribe", "newsletter", "automated", "noreply", "no-reply", "github", "notification"}
        email_summaries: list[str] = []
        for email in activity_data.emails:
            subject = email.get("subject", "")
            if any(keyword in subject.lower() for keyword in skip_keywords):
                continue
            sender = email.get("sender") or email.get("from") or "unknown sender"
            email_summaries.append(f"- {subject} (from: {sender})")
            if email.get("contact_name"):
                people_mentioned.add(email["contact_name"])
        if email_summaries:
            context_parts.append(
                f"EMAILS ({len(email_summaries)} meaningful):\n" + "\n".join(email_summaries[:MAX_LIST_ITEMS])
            )

    if activity_data.tasks_completed:
        completed = [task.get("title", "Task") for task in activity_data.tasks_completed]
        if completed:
            context_parts.append(
                f"TASKS COMPLETED ({len(completed)}):\n- " + "\n- ".join(_limit_items(completed))
            )

    if activity_data.tasks_created:
        created = [task.get("title", "Task") for task in activity_data.tasks_created]
        if created:
            context_parts.append(
                f"NEW TASKS ({len(created)}):\n- " + "\n- ".join(_limit_items(created))
            )

    if activity_data.reflections:
        reflections = [item.get("title", "Reflection") for item in activity_data.reflections]
        if reflections:
            context_parts.append(
                f"REFLECTIONS RECORDED ({len(reflections)}):\n- " + "\n- ".join(_limit_items(reflections))
            )

    if activity_data.journals:
        highlights: list[str] = []
        for journal in activity_data.journals:
            highlights.extend(journal.get("highlights", [])[:MAX_LIST_ITEMS])
        if highlights:
            context_parts.append("JOURNAL HIGHLIGHTS:\n- " + "\n- ".join(_limit_items(highlights)))

    # Screen time from ActivityWatch
    if activity_data.screen_time:
        st = activity_data.screen_time
        screen_lines: list[str] = []
        
        if st.get("total_active_hours"):
            screen_lines.append(f"Total active screen time: {st['total_active_hours']}h")
        if st.get("productive_hours"):
            screen_lines.append(f"Productive time: {st['productive_hours']}h")
        if st.get("distracting_hours"):
            screen_lines.append(f"Distracting time: {st['distracting_hours']}h")
        
        top_apps = st.get("top_apps", [])
        if top_apps:
            app_names = [app.get("app", app) if isinstance(app, dict) else str(app) for app in top_apps[:5]]
            screen_lines.append(f"Top apps: {', '.join(app_names)}")
        
        top_sites = st.get("top_sites", [])
        if top_sites:
            site_names = [site.get("site", site) if isinstance(site, dict) else str(site) for site in top_sites[:5]]
            screen_lines.append(f"Top websites: {', '.join(site_names)}")
        
        if screen_lines:
            context_parts.append("SCREEN TIME (ActivityWatch):\n" + "\n".join(screen_lines))

    # Reading data - books and highlights
    if activity_data.reading:
        reading = activity_data.reading
        reading_lines: list[str] = []
        
        # Currently reading books
        currently_reading = reading.get("currently_reading", [])
        if currently_reading:
            reading_lines.append("Currently reading:")
            for book in currently_reading[:3]:
                title = book.get("title", "Unknown")
                author = book.get("author", "")
                progress = book.get("progress_percent", 0)
                author_str = f" by {author}" if author else ""
                reading_lines.append(f"  - {title}{author_str} ({progress}% complete)")
        
        # Today's highlights
        highlights = reading.get("todays_highlights", [])
        if highlights:
            reading_lines.append(f"\nToday's book highlights ({len(highlights)}):")
            for h in highlights[:5]:
                content = h.get("content", "")[:100]
                book = h.get("book_title", "")
                if content:
                    reading_lines.append(f"  - \"{content}...\" ({book})")
                    if h.get("note"):
                        reading_lines.append(f"    Note: {h['note'][:80]}")
        
        # Recently finished
        finished = reading.get("recently_finished", [])
        if finished:
            reading_lines.append(f"\nRecently finished:")
            for book in finished[:3]:
                title = book.get("title", "Unknown")
                rating = book.get("rating")
                rating_str = f" ({'⭐' * rating})" if rating else ""
                reading_lines.append(f"  - {title}{rating_str}")
        
        if reading_lines:
            context_parts.append("READING:\n" + "\n".join(reading_lines))

    context = "\n\n".join(context_parts) if context_parts else "No significant activities recorded today."
    return context, people_mentioned


def _call_claude(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = response.content[0].text

    try:
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(response_text)
    except json.JSONDecodeError:
        logger.warning("Unable to parse Claude response; returning fallback JSON")
        return {
            "highlights": ["Reflect on your day's activities"],
            "meetings": [],
            "reflection_prompts": ["What stood out to you today?"],
        }


def _build_prompt(context: str, people_summary: str, user_name: Optional[str]) -> str:
    salutation = f"You are a thoughtful personal assistant helping {user_name} reflect on their day." if user_name else "You are a thoughtful personal assistant helping someone reflect on their day."
    return f"""{salutation}

TODAY'S ACTIVITIES:
{context}

PEOPLE INTERACTED WITH: {people_summary or 'No direct contacts captured'}

Based on this day's activities, generate a JSON response with the following fields:

1. "highlights": A list of 3-5 bullet points of the most relevant or interesting things done today (tasks, emails, reflections, etc.). Do not include meetings here unless they were the primary work output. Avoid redundancy.
2. "meetings": A list of the meetings that occurred today. If none, return an empty list.
3. "reflection_prompts": 2-3 personalized questions based on specific events or conversations today.

Respond ONLY in valid JSON format:
{{
    "highlights": ["string", "string"],
    "meetings": ["string", "string"],
    "reflection_prompts": ["string", "string"]
}}
"""


def _build_message(
    highlights: List[str],
    meetings: List[str],
    prompts: List[str],
    people_summary: str,
    screen_time: Optional[dict] = None,
    reading: Optional[dict] = None
) -> str:
    now = datetime.utcnow()
    lines: list[str] = []

    lines.append("**Evening Journal**")
    lines.append(f"_{now.strftime('%A, %B %d')}_")
    lines.append("")

    if highlights:
        lines.append("**Today's highlights:**")
        lines.extend(f"- {item}" for item in highlights)
        lines.append("")

    if meetings:
        lines.append("**Meetings:**")
        lines.extend(f"- {item}" for item in meetings)
        lines.append("")

    # Include reading progress if available
    if reading:
        currently_reading = reading.get("currently_reading", [])
        todays_highlights = reading.get("todays_highlights", [])
        
        if currently_reading or todays_highlights:
            lines.append("**📚 Reading:**")
            
            if currently_reading:
                for book in currently_reading[:2]:
                    title = book.get("title", "Unknown")
                    progress = book.get("progress_percent", 0)
                    lines.append(f"- {title}: {progress}% complete")
            
            if todays_highlights:
                lines.append(f"- {len(todays_highlights)} new highlight(s) today")
            
            lines.append("")

    # Include screen time summary if available
    if screen_time:
        lines.append("**Screen Time:**")
        if screen_time.get("total_active_hours"):
            lines.append(f"- Active: {screen_time['total_active_hours']}h")
        if screen_time.get("productive_hours"):
            lines.append(f"- Productive: {screen_time['productive_hours']}h")
        if screen_time.get("distracting_hours"):
            lines.append(f"- Distracting: {screen_time['distracting_hours']}h")
        top_apps = screen_time.get("top_apps", [])
        if top_apps:
            app_names = [app.get("app", app) if isinstance(app, dict) else str(app) for app in top_apps[:3]]
            lines.append(f"- Top apps: {', '.join(app_names)}")
        lines.append("")

    if prompts:
        lines.append("**Things to reflect on:**")
        lines.extend(f"- {item}" for item in prompts)
        lines.append("")

    lines.append(f"People you interacted with: {people_summary}")
    lines.append("Reply with a voice note or text to journal.")

    return "\n".join(lines).strip()


@router.post("/journal/evening-prompt", response_model=JournalPromptResponse)
async def generate_evening_journal_prompt(request: JournalPromptRequest) -> JournalPromptResponse:
    """Generate an evening journal prompt grounded in the day's activity history."""
    try:
        context, people_mentioned = _collect_activity_context(request)
        people_summary = _format_people_summary(people_mentioned)
        prompt = _build_prompt(context, people_summary, request.user_name)
        analysis = _call_claude(prompt)

        highlights = _limit_items(analysis.get("highlights", []), limit=5)
        meetings = _limit_items(analysis.get("meetings", []), limit=MAX_LIST_ITEMS)
        reflection_prompts = _limit_items(analysis.get("reflection_prompts", []), limit=3)

        # Get screen time and reading data for message template
        screen_time = None
        if request.activity_data.screen_time:
            screen_time = request.activity_data.screen_time
        
        reading = None
        if request.activity_data.reading:
            reading = request.activity_data.reading

        message = _build_message(highlights, meetings, reflection_prompts, people_summary, screen_time, reading)

        return JournalPromptResponse(
            status="success",
            highlights=highlights,
            reflection_prompts=reflection_prompts,
            people_summary=people_summary,
            message=message,
        )

    except Exception as exc:
        logger.exception("Failed to build evening journal prompt")
        raise HTTPException(status_code=500, detail=str(exc))
