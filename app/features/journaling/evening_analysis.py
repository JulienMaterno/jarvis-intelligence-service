"""
==============================================================================
ENHANCED EVENING JOURNAL ANALYSIS
==============================================================================

This module generates AI-powered evening journal prompts that:

1. Analyze all daily activity comprehensively
2. Generate insightful, personalized summaries
3. Ask thoughtful reflection questions based on specific observations
4. Include book highlights and reading progress
5. Create journal content that can be stored

The AI acts as a thoughtful personal assistant who has observed your entire
day and helps you reflect on what happened.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger("Jarvis.Intelligence.EveningJournal")

MODEL_ID = os.getenv("CLAUDE_JOURNAL_MODEL", "claude-sonnet-4-5-20250929")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ActivityData(BaseModel):
    """All activity data from TODAY (user's timezone)."""
    meetings: List[Dict] = Field(default_factory=list)
    calendar_events: List[Dict] = Field(default_factory=list)
    emails: List[Dict] = Field(default_factory=list)
    tasks_completed: List[Dict] = Field(default_factory=list)
    tasks_created: List[Dict] = Field(default_factory=list)
    tasks_due_today: List[Dict] = Field(default_factory=list)  # Tasks scheduled for today (may have been set earlier)
    reflections: List[Dict] = Field(default_factory=list)
    highlights: List[Dict] = Field(default_factory=list)  # Book highlights
    reading: Optional[Dict] = None  # Reading progress
    screen_time: Optional[Dict] = None
    contacts_added: List[Dict] = Field(default_factory=list)
    summary: Optional[Dict] = None


class JournalAnalysisRequest(BaseModel):
    """Request for evening journal analysis."""
    activity_data: ActivityData
    user_name: Optional[str] = None
    timezone: str = "UTC"
    previous_journals: Optional[List[Dict]] = None  # Last few journal entries for context


class JournalAnalysisResponse(BaseModel):
    """Response from evening journal analysis.
    
    Note: 'meetings' and 'observations' fields are kept for backwards compatibility
    but the new prompt no longer generates them (they're merged into highlights/questions).
    """
    status: str
    highlights: List[str] = Field(default_factory=list)
    meetings: List[str] = Field(default_factory=list)  # Deprecated - kept for compatibility
    reflection_questions: List[str] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)  # Deprecated - merged into questions
    journal_content: str = ""
    message: str = ""


# =============================================================================
# CONTEXT BUILDING
# =============================================================================

def build_activity_context(data: ActivityData) -> str:
    """Build a comprehensive context string from all activity data."""
    sections = []
    
    # Meetings
    if data.meetings:
        meeting_lines = []
        for m in data.meetings[:10]:
            title = m.get("title", "Untitled")
            summary = m.get("summary", "")[:200]
            contact = m.get("contact_name", "")
            people = m.get("people_mentioned", [])
            
            line = f"- {title}"
            if contact:
                line += f" (with {contact})"
            if summary:
                line += f": {summary}"
            meeting_lines.append(line)
            
            if people:
                meeting_lines.append(f"  People mentioned: {', '.join(people[:5])}")
        
        sections.append(f"MEETINGS ({len(data.meetings)}):\n" + "\n".join(meeting_lines))
    
    # Tasks Completed
    if data.tasks_completed:
        task_lines = [f"- {t.get('title', 'Task')}" for t in data.tasks_completed[:10]]
        sections.append(f"TASKS COMPLETED ({len(data.tasks_completed)}):\n" + "\n".join(task_lines))
    
    # Tasks Created Today
    if data.tasks_created:
        task_lines = []
        for t in data.tasks_created[:10]:
            title = t.get("title", "Task")
            priority = t.get("priority", "")
            due = t.get("due_date", "")
            line = f"- {title}"
            if priority:
                line += f" [{priority}]"
            if due:
                line += f" (due: {due})"
            task_lines.append(line)
        sections.append(f"NEW TASKS CREATED ({len(data.tasks_created)}):\n" + "\n".join(task_lines))
    
    # Tasks Due Today (may have been scheduled earlier - important for follow-up)
    if data.tasks_due_today:
        task_lines = []
        for t in data.tasks_due_today[:10]:
            title = t.get("title", "Task")
            status = t.get("status", "")
            priority = t.get("priority", "")
            line = f"- {title}"
            if status:
                line += f" [{status}]"
            if priority:
                line += f" ({priority})"
            task_lines.append(line)
        sections.append(f"TASKS DUE TODAY ({len(data.tasks_due_today)}):\n" + "\n".join(task_lines))
    
    # Reflections
    if data.reflections:
        reflection_lines = []
        for r in data.reflections[:5]:
            title = r.get("title", "Reflection")
            content = r.get("content", "")[:150]
            mood = r.get("mood", "")
            
            line = f"- {title}"
            if mood:
                line += f" (mood: {mood})"
            if content:
                line += f"\n  Content: {content}..."
            reflection_lines.append(line)
        sections.append(f"REFLECTIONS RECORDED ({len(data.reflections)}):\n" + "\n".join(reflection_lines))
    
    # Calendar Events
    if data.calendar_events:
        event_lines = []
        for e in data.calendar_events[:10]:
            summary = e.get("summary") or e.get("title", "Event")
            location = e.get("location", "")
            attendees = e.get("attendees", [])
            
            line = f"- {summary}"
            if location:
                line += f" @ {location}"
            if attendees:
                names = [a.get("displayName", a.get("email", "")) for a in attendees[:3] if isinstance(a, dict)]
                if names:
                    line += f" (with: {', '.join(names)})"
            event_lines.append(line)
        sections.append(f"CALENDAR EVENTS ({len(data.calendar_events)}):\n" + "\n".join(event_lines))
    
    # Emails (filtered for meaningful ones)
    if data.emails:
        email_lines = []
        for e in data.emails[:10]:
            subject = e.get("subject", "No subject")
            sender = e.get("sender", "Unknown")
            email_lines.append(f"- {subject} (from: {sender})")
        sections.append(f"MEANINGFUL EMAILS ({len(data.emails)}):\n" + "\n".join(email_lines))
    
    # Book Highlights - NEW!
    if data.highlights:
        highlight_lines = []
        for h in data.highlights[:8]:
            content = h.get("content", "")[:150]
            book = h.get("book_title", "")
            note = h.get("note", "")
            
            if content:
                line = f'- "{content}..."'
                if book:
                    line += f" (from: {book})"
                highlight_lines.append(line)
                if note:
                    highlight_lines.append(f"  Your note: {note[:100]}")
        
        if highlight_lines:
            sections.append(f"BOOK HIGHLIGHTS ({len(data.highlights)}):\n" + "\n".join(highlight_lines))
    
    # Reading Progress - NEW!
    if data.reading:
        reading_lines = []
        
        currently_reading = data.reading.get("currently_reading", [])
        if currently_reading:
            for book in currently_reading[:3]:
                title = book.get("title", "Unknown")
                progress = book.get("progress_percent", 0)
                author = book.get("author", "")
                line = f"- Currently reading: {title}"
                if author:
                    line += f" by {author}"
                line += f" ({progress}% complete)"
                reading_lines.append(line)
        
        # Only books finished TODAY (not last 7 days)
        finished_today = data.reading.get("finished_today", [])
        if finished_today:
            for book in finished_today[:2]:
                title = book.get("title", "Unknown")
                rating = book.get("rating")
                line = f"- Finished today: {title}"
                if rating:
                    line += f" (rated {rating}/5)"
                reading_lines.append(line)
        
        started_today = data.reading.get("started_today", [])
        if started_today:
            for book in started_today[:2]:
                title = book.get("title", "Unknown")
                reading_lines.append(f"- Started new book: {title}")
        
        if reading_lines:
            sections.append("READING ACTIVITY:\n" + "\n".join(reading_lines))
    
    # Screen Time
    if data.screen_time:
        st = data.screen_time
        screen_lines = []
        
        if st.get("total_active_hours"):
            screen_lines.append(f"- Total active time: {st['total_active_hours']}h")
        if st.get("productive_hours"):
            screen_lines.append(f"- Productive time: {st['productive_hours']}h")
        if st.get("distracting_hours"):
            screen_lines.append(f"- Distracting time: {st['distracting_hours']}h")
        
        top_apps = st.get("top_apps", [])
        if top_apps:
            app_names = [a.get("app", str(a)) if isinstance(a, dict) else str(a) for a in top_apps[:5]]
            screen_lines.append(f"- Top apps: {', '.join(app_names)}")
        
        if screen_lines:
            sections.append("SCREEN TIME:\n" + "\n".join(screen_lines))
    
    # Contacts Added
    if data.contacts_added:
        contact_lines = []
        for c in data.contacts_added[:5]:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            company = c.get("company", "")
            line = f"- {name}"
            if company:
                line += f" ({company})"
            contact_lines.append(line)
        sections.append(f"NEW CONTACTS ({len(data.contacts_added)}):\n" + "\n".join(contact_lines))
    
    # Combine all sections
    if sections:
        return "\n\n".join(sections)
    else:
        return "No significant activities recorded today."


# =============================================================================
# PROMPT ENGINEERING
# =============================================================================

def build_analysis_prompt(context: str, user_name: Optional[str] = None, previous_journals: Optional[List[Dict]] = None) -> str:
    """Build a concise prompt for Claude to analyze the day and generate journal content."""
    
    name_ref = user_name or "the user"
    
    # Add previous journals context if available (minimal, just for deduplication)
    previous_context = ""
    if previous_journals:
        prev_lines = []
        for j in previous_journals[:2]:  # Only last 2 days for deduplication
            date = j.get("date", "Unknown")
            content = j.get("content") or ""
            # Only include a brief summary to help avoid mentioning same things
            if content:
                prev_lines.append(f"[{date}]: {content[:200]}...")
        
        if prev_lines:
            previous_context = f"""
--- PREVIOUS DAYS (for deduplication only - DO NOT mention these events) ---
{chr(10).join(prev_lines)}
--- END PREVIOUS CONTEXT ---
"""
    
    return f"""You are {name_ref}'s thoughtful personal assistant generating a brief evening journal.

CRITICAL RULES:
1. ONLY include events from TODAY'S ACTIVITIES below
2. Be CONCISE - less is more. Quiet days = short journals
3. NO redundancy - each fact should appear exactly ONCE
4. DO NOT list things separately if they're the same event (e.g., meeting + calendar event)
5. Integrate insights about reading, screen time, etc. naturally - don't list them as separate sections

TODAY'S ACTIVITIES:
{context}
{previous_context}

Generate JSON with these fields. Keep it SHORT and NON-REDUNDANT:

{{
    "highlights": [
        // 2-4 KEY moments only. Quality over quantity.
        // Skip if day was quiet. Empty array is fine.
        // Each item: one sentence, specific, no overlap with other items
    ],
    "reflection_questions": [
        // 2-3 thoughtful questions that combine observations WITH curiosity
        // Reference specific events from today
        // MERGE insights into questions (don't have separate "observations")
        // Example: "You spent 5h in deep work today but only completed 1 task - what made it feel productive or draining?"
    ],
    "journal_content": "Brief 1-2 paragraph description in third person. Focus only on what's meaningful. For quiet days, a single sentence is fine."
}}

BREVITY GUIDE:
- Quiet day (0-2 meetings, few tasks): 2-3 highlights max, 2 questions, 1-2 sentences in journal_content
- Normal day (3-5 meetings, multiple tasks): 3-4 highlights, 2-3 questions, short paragraph
- Busy day (5+ meetings): 4-5 highlights max, 3 questions, 2 paragraphs

Respond with valid JSON only."""


# =============================================================================
# AI INTERACTION
# =============================================================================

def call_claude_for_analysis(prompt: str) -> Dict[str, Any]:
    """Call Claude to analyze the day's activities."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    try:
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=1500,  # Reduced for conciseness
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text
        
        # Parse JSON from response
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            return json.loads(json_match.group())
        
        return json.loads(response_text)
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Claude response: {e}")
        return {
            "highlights": ["Take a moment to reflect on your day"],
            "reflection_questions": ["What stood out to you most about today?"],
            "journal_content": "A day of quiet activities. Take some time to reflect."
        }
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


# =============================================================================
# MESSAGE FORMATTING
# =============================================================================

def format_telegram_message(
    analysis: Dict,
    activity_summary: Dict,
    reading: Optional[Dict] = None,
    highlights: Optional[List[Dict]] = None
) -> str:
    """Format the analysis into a CONCISE Telegram message.
    
    Design principles:
    - No redundancy (don't list meetings AND key moments about same event)
    - Reading/highlights integrated into flow, not separate sections
    - Observations merged into questions
    - Quiet days = shorter messages
    """
    now = datetime.now(timezone.utc)
    lines = []
    
    # Header with date
    lines.append("📓 **Evening Journal**")
    lines.append(f"_{now.strftime('%A, %B %d, %Y')}_")
    lines.append("")
    
    # Quick Stats (one line summary)
    if activity_summary:
        stats = []
        meetings = activity_summary.get("meetings_count", 0)
        completed = activity_summary.get("tasks_completed_count", 0)
        created = activity_summary.get("tasks_created_count", 0)
        book_highlights = activity_summary.get("highlights_count", 0)
        
        if meetings:
            stats.append(f"🤝 {meetings} meeting{'s' if meetings > 1 else ''}")
        if completed:
            stats.append(f"✅ {completed} done")
        if created:
            stats.append(f"📝 {created} new tasks")
        if book_highlights:
            stats.append(f"📚 {book_highlights} highlights")
        
        # Include reading progress inline
        if reading:
            currently_reading = reading.get("currently_reading", [])
            for book in currently_reading[:1]:  # Just one book
                progress = book.get('progress_percent', 0)
                if progress > 0:
                    stats.append(f"📖 {book.get('title', 'Reading')}: {progress}%")
        
        if stats:
            lines.append("**Your Day:** " + " • ".join(stats))
            lines.append("")
    
    # Key Moments (AI-generated highlights - the main content)
    ai_highlights = analysis.get("highlights", [])
    if ai_highlights:
        lines.append("**✨ Key Moments:**")
        for h in ai_highlights[:4]:  # Max 4
            lines.append(f"• {h}")
        lines.append("")
    
    # Skip separate meetings/observations/book sections - they're now merged into highlights/questions
    
    # Reflection Questions (with observations baked in)
    questions = analysis.get("reflection_questions", [])
    if questions:
        lines.append("**🤔 Reflect:**")
        for q in questions[:3]:  # Max 3 questions
            lines.append(f"• {q}")
        lines.append("")
    
    # Call to action
    lines.append("---")
    lines.append("_Reply with voice or text to capture your thoughts._")
    
    return "\n".join(lines)


# =============================================================================
# MAIN ANALYSIS FUNCTION
# =============================================================================

def analyze_day_for_journal(request: JournalAnalysisRequest) -> JournalAnalysisResponse:
    """
    Main function to analyze the day and generate journal content.
    
    This is called by the sync service to generate the evening journal.
    """
    try:
        # Build context from all activities
        context = build_activity_context(request.activity_data)
        
        # Build prompt with previous journals context and call Claude
        prompt = build_analysis_prompt(
            context, 
            request.user_name,
            previous_journals=request.previous_journals
        )
        analysis = call_claude_for_analysis(prompt)
        
        # Get summary for stats
        summary = request.activity_data.summary or {}
        
        # Format Telegram message
        message = format_telegram_message(
            analysis=analysis,
            activity_summary=summary,
            reading=request.activity_data.reading,
            highlights=request.activity_data.highlights[:5] if request.activity_data.highlights else None
        )
        
        return JournalAnalysisResponse(
            status="success",
            highlights=analysis.get("highlights", []),
            meetings=analysis.get("meetings", []),
            reflection_questions=analysis.get("reflection_questions", []),
            observations=analysis.get("observations", []),
            journal_content=analysis.get("journal_content", ""),
            message=message
        )
        
    except Exception as e:
        logger.exception("Failed to analyze day for journal")
        raise
