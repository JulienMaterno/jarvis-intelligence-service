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
    """All activity data from the last 24 hours."""
    meetings: List[Dict] = Field(default_factory=list)
    calendar_events: List[Dict] = Field(default_factory=list)
    emails: List[Dict] = Field(default_factory=list)
    tasks_completed: List[Dict] = Field(default_factory=list)
    tasks_created: List[Dict] = Field(default_factory=list)
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
    """Response from evening journal analysis."""
    status: str
    highlights: List[str] = Field(default_factory=list)
    meetings: List[str] = Field(default_factory=list)
    reflection_questions: List[str] = Field(default_factory=list)
    observations: List[str] = Field(default_factory=list)
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
    
    # Tasks Created
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
        
        recently_finished = data.reading.get("recently_finished", [])
        if recently_finished:
            for book in recently_finished[:2]:
                title = book.get("title", "Unknown")
                rating = book.get("rating")
                line = f"- Finished: {title}"
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
    """Build the prompt for Claude to analyze the day and generate journal content."""
    
    name_ref = user_name or "the user"
    
    # Add previous journals context if available
    previous_context = ""
    if previous_journals:
        prev_lines = []
        for j in previous_journals[:3]:  # Last 3 days
            date = j.get("date", "Unknown")
            content = j.get("content") or ""  # Handle None content
            content = content[:500] if content else ""
            if content:
                prev_lines.append(f"--- {date} ---\n{content}\n")
        
        if prev_lines:
            previous_context = f"""

RECENT JOURNAL ENTRIES (for context and continuity):
{chr(10).join(prev_lines)}

Use this context to:
- Reference ongoing themes or projects
- Note progress on things mentioned before
- Connect today's events to recent patterns
"""
    
    return f"""You are a thoughtful, observant personal AI assistant helping {name_ref} reflect on their day. You have access to everything that happened in the last 24 hours.

Your role is to:
1. Identify the most meaningful moments and accomplishments
2. Notice patterns, themes, or interesting observations
3. Ask deep, thoughtful questions that encourage genuine reflection
4. Help create a valuable journal summary

TODAY'S ACTIVITIES (Last 24 hours):
{context}
{previous_context}

Based on this comprehensive view of the day, generate a JSON response with:

1. "highlights" - List of 3-5 most significant moments or accomplishments. Be specific about what happened. Don't be generic.

2. "meetings" - List of meeting summaries if any occurred. Include who was involved and key topics.

3. "observations" - 2-3 things you noticed about the day (patterns, themes, contrasts). Be insightful and specific.

4. "reflection_questions" - 3-4 THOUGHTFUL questions based on SPECIFIC things that happened. These should:
   - Reference actual events, tasks, or interactions from the data
   - Encourage deeper thinking about decisions, feelings, or outcomes
   - Help the user gain insight into their day
   - Be personal and relevant to what they actually did
   
   GOOD examples:
   - "You had 3 meetings today with different clients. Which conversation felt most productive and why?"
   - "You highlighted a passage about leadership in your book. How does that apply to the project you're working on?"
   - "I noticed you completed 5 tasks but also created 8 new ones. Do you feel like you're gaining ground or falling behind?"
   
   BAD examples (too generic):
   - "What are you grateful for today?"
   - "How do you feel about your day?"
   - "What did you learn today?"

5. "journal_content" - A 2-3 paragraph DESCRIPTION of {name_ref}'s day. IMPORTANT RULES:
   - Write in THIRD PERSON, describing what {name_ref} did (NOT first person "I did...")
   - Example: "{name_ref} started the day with..." or "Today, {name_ref} focused on..."
   - Be specific about events, accomplishments, and notable moments
   - Include any observations about patterns or themes
   - This is an observer's summary, not a personal diary entry
   - Keep a warm but objective tone

Respond ONLY in valid JSON format:
{{
    "highlights": ["string"],
    "meetings": ["string"],
    "observations": ["string"],
    "reflection_questions": ["string"],
    "journal_content": "string"
}}
"""


# =============================================================================
# AI INTERACTION
# =============================================================================

def call_claude_for_analysis(prompt: str) -> Dict[str, Any]:
    """Call Claude to analyze the day's activities."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    
    try:
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=2000,
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
            "meetings": [],
            "observations": ["Today was recorded but needs your interpretation"],
            "reflection_questions": ["What stood out to you most about today?"],
            "journal_content": "Today was a day of various activities. Take some time to reflect on what mattered most."
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
    """Format the analysis into a Telegram message."""
    now = datetime.now(timezone.utc)
    lines = []
    
    # Header
    lines.append("📓 **Evening Journal**")
    lines.append(f"_{now.strftime('%A, %B %d, %Y')}_")
    lines.append("")
    
    # Quick Stats
    if activity_summary:
        stats = []
        if activity_summary.get("meetings_count", 0):
            stats.append(f"🤝 {activity_summary['meetings_count']} meetings")
        if activity_summary.get("tasks_completed_count", 0):
            stats.append(f"✅ {activity_summary['tasks_completed_count']} completed")
        if activity_summary.get("tasks_created_count", 0):
            stats.append(f"📝 {activity_summary['tasks_created_count']} new tasks")
        if activity_summary.get("highlights_count", 0):
            stats.append(f"📚 {activity_summary['highlights_count']} highlights")
        
        if stats:
            lines.append("**Your Day:** " + " • ".join(stats))
            lines.append("")
    
    # AI Highlights
    ai_highlights = analysis.get("highlights", [])
    if ai_highlights:
        lines.append("**✨ Key Moments:**")
        for h in ai_highlights[:5]:
            lines.append(f"• {h}")
        lines.append("")
    
    # Meetings
    meetings = analysis.get("meetings", [])
    if meetings:
        lines.append("**🤝 Meetings:**")
        for m in meetings[:4]:
            lines.append(f"• {m}")
        lines.append("")
    
    # Observations
    observations = analysis.get("observations", [])
    if observations:
        lines.append("**👁 I Noticed:**")
        for o in observations[:3]:
            lines.append(f"• {o}")
        lines.append("")
    
    # Reading Section
    if reading:
        currently_reading = reading.get("currently_reading", [])
        recently_finished = reading.get("recently_finished", [])
        
        if currently_reading or recently_finished:
            lines.append("**📚 Reading:**")
            for book in currently_reading[:2]:
                lines.append(f"• {book.get('title', 'Book')}: {book.get('progress_percent', 0)}%")
            for book in recently_finished[:1]:
                lines.append(f"• Finished: {book.get('title', 'Book')}")
            lines.append("")
    
    # Book Highlights
    if highlights:
        lines.append("**💡 Today's Highlights:**")
        for h in highlights[:2]:
            content = h.get("content", "")[:100]
            book = h.get("book_title", "")
            if content:
                lines.append(f'_"{content}..."_')
                if book:
                    lines.append(f"  — {book}")
        lines.append("")
    
    # Reflection Questions - THE KEY PART
    questions = analysis.get("reflection_questions", [])
    if questions:
        lines.append("**🤔 Questions for You:**")
        for q in questions[:4]:
            lines.append(f"• {q}")
        lines.append("")
    
    # Call to action
    lines.append("---")
    lines.append("_Reply with voice or text to add your thoughts._")
    
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
