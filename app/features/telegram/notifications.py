"""
Telegram notification service.
Sends messages to the user via the Telegram bot.
"""

import logging
import httpx
from typing import Optional, List, Dict, Any

from app.shared.constants import TELEGRAM_BOT_URL, TELEGRAM_CHAT_ID

logger = logging.getLogger("Jarvis.Intelligence.Telegram")


async def send_telegram_message(
    text: str,
    chat_id: int = None,
    parse_mode: str = "Markdown"
) -> bool:
    """
    Send a message to the user via Telegram bot.
    
    Args:
        text: Message text (supports Markdown)
        chat_id: Telegram chat ID (defaults to configured TELEGRAM_CHAT_ID)
        parse_mode: 'Markdown' or 'HTML'
    
    Returns:
        True if sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_URL:
        logger.warning("TELEGRAM_BOT_URL not configured, skipping notification")
        return False
    
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    if not target_chat_id:
        logger.warning("No chat_id provided and TELEGRAM_CHAT_ID not configured")
        return False
    
    url = f"{TELEGRAM_BOT_URL.rstrip('/')}/send_message"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json={
                "chat_id": target_chat_id,
                "text": text,
                "parse_mode": parse_mode
            })
            
            if response.status_code == 200:
                logger.info(f"Telegram message sent to {target_chat_id}")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


def build_processing_result_message(
    category: str,
    db_records: Dict[str, Any],
    analysis: Dict[str, Any],
    transcript_preview: str = None
) -> str:
    """
    Build a user-friendly message summarizing what was processed.
    Includes options for feedback/corrections.
    
    Args:
        category: Primary category (meeting, journal, reflection, etc.)
        db_records: Dict with created record IDs
        analysis: The LLM analysis result
        transcript_preview: Optional first ~100 chars of transcript
    
    Returns:
        Formatted message string
    """
    lines = []
    
    # Header based on category
    emoji_map = {
        "meeting": "📅",
        "journal": "📓",
        "reflection": "💭",
        "task_planning": "✅",
        "other": "📝"
    }
    emoji = emoji_map.get(category, "📝")
    lines.append(f"{emoji} *Voice memo processed!*")
    lines.append("")
    
    # What was created
    created_items = []
    
    if db_records.get("journal_ids"):
        journals = analysis.get("journals", [])
        for j in journals:
            date = j.get("date", "today")
            mood = j.get("mood", "")
            mood_str = f" (Mood: {mood})" if mood else ""
            created_items.append(f"📓 Journal for {date}{mood_str}")
    
    if db_records.get("meeting_ids"):
        meetings = analysis.get("meetings", [])
        for m in meetings:
            title = m.get("title", "Untitled")
            person = m.get("person_name", "")
            person_str = f" with {person}" if person else ""
            created_items.append(f"📅 Meeting: {title}{person_str}")
    
    if db_records.get("reflection_ids"):
        reflections = analysis.get("reflections", [])
        appended = db_records.get("reflection_appended", False)
        for r in reflections:
            title = r.get("title", "Untitled")
            if appended:
                created_items.append(f"💭 Appended to: {title}")
            else:
                created_items.append(f"💭 Reflection: {title}")
    
    if db_records.get("task_ids"):
        task_count = len(db_records["task_ids"])
        created_items.append(f"✅ {task_count} task(s) created")
    
    if created_items:
        lines.append("*Created:*")
        for item in created_items:
            lines.append(f"  {item}")
        lines.append("")
    
    # Contact linking feedback - only show linked contacts, skip unlinked
    contact_matches = db_records.get("contact_matches", [])
    linked_contacts = [m for m in contact_matches if m.get("matched")]
    if linked_contacts:
        lines.append("*Contacts:*")
        for match in linked_contacts:
            name = match.get("searched_name", "Unknown")
            linked = match.get("linked_contact", {})
            linked_name = linked.get("name", name)
            company = linked.get("company", "")
            company_str = f" ({company})" if company else ""
            lines.append(f"  👤 Linked: {linked_name}{company_str}")
        lines.append("")
    
    # Footer with feedback options
    lines.append("_Reply to provide feedback or corrections._")
    
    return "\n".join(lines)


def build_meeting_feedback_message(
    meeting_id: str,
    meeting_data: Dict[str, Any],
    contact_match: Dict[str, Any] = None
) -> str:
    """
    Build a meeting-specific feedback message with correction options.
    
    This message asks the user to confirm or correct:
    - Meeting title and summary
    - Contact association
    - Topics discussed
    - Follow-up items
    
    Args:
        meeting_id: UUID of the created meeting
        meeting_data: The meeting analysis data
        contact_match: Optional contact matching info
    
    Returns:
        Formatted message with feedback options
    """
    lines = []
    
    title = meeting_data.get("title", "Untitled Meeting")
    person = meeting_data.get("person_name", "")
    summary = meeting_data.get("summary", "")[:200]
    date = meeting_data.get("date", "today")
    topics = meeting_data.get("topics_discussed", [])
    
    lines.append(f"📅 *Meeting Created*")
    lines.append("")
    lines.append(f"*{title}*")
    if person:
        lines.append(f"With: {person}")
    lines.append(f"Date: {date}")
    lines.append("")
    
    if summary:
        lines.append(f"_{summary}_")
        lines.append("")
    
    if topics:
        lines.append("*Topics discussed:*")
        for t in topics[:5]:
            if isinstance(t, dict):
                topic_name = t.get("topic", "")
                lines.append(f"  • {topic_name}")
            else:
                lines.append(f"  • {t}")
        lines.append("")
    
    # Contact linking status
    if contact_match:
        if contact_match.get("matched"):
            linked = contact_match.get("linked_contact", {})
            linked_name = linked.get("name", person)
            company = linked.get("company", "")
            company_str = f" ({company})" if company else ""
            lines.append(f"👤 Linked to: {linked_name}{company_str}")
        else:
            searched_name = contact_match.get("searched_name", person)
            suggestions = contact_match.get("suggestions", [])
            
            lines.append(f"❓ *Contact not found:* {searched_name}")
            if suggestions:
                lines.append("Reply with a number to link:")
                for i, s in enumerate(suggestions[:5], 1):
                    name = s.get("name", "Unknown")
                    company = s.get("company", "")
                    company_str = f" ({company})" if company else ""
                    lines.append(f"  {i}. {name}{company_str}")
                lines.append("  0. Skip")
                lines.append("  Or type the correct name")
            else:
                lines.append("Type the correct name or '0' to skip")
        lines.append("")
    
    # Feedback prompt
    lines.append("*Is this correct?*")
    lines.append("• Reply 'yes' or ✓ if correct")
    lines.append("• Reply with corrections if not")
    lines.append(f"• Meeting ID: `{meeting_id[:8]}...`")
    
    return "\n".join(lines)


async def send_meeting_feedback(
    meeting_id: str,
    meeting_data: Dict[str, Any],
    contact_match: Dict[str, Any] = None,
    chat_id: int = None
) -> bool:
    """
    Send a meeting feedback message to Telegram.
    Called whenever a meeting is created.
    
    Args:
        meeting_id: UUID of the created meeting
        meeting_data: The meeting analysis data  
        contact_match: Optional contact matching info
        chat_id: Target chat ID (defaults to TELEGRAM_CHAT_ID)
    
    Returns:
        True if sent successfully
    """
    message = build_meeting_feedback_message(meeting_id, meeting_data, contact_match)
    return await send_telegram_message(message, chat_id=chat_id)


def build_journal_day_summary_message(
    journal_data: Dict[str, Any],
    reflection_prompts: List[str] = None
) -> str:
    """
    Build an evening journal prompt message with day overview.
    
    Args:
        journal_data: Journal entry data
        reflection_prompts: AI-generated reflection questions
    
    Returns:
        Formatted message for Telegram
    """
    lines = []
    
    date = journal_data.get("date", "today")
    lines.append(f"📓 *Evening Journal - {date}*")
    lines.append("")
    
    # Summary
    summary = journal_data.get("summary", "")
    if summary:
        lines.append(f"_{summary}_")
        lines.append("")
    
    # Key events
    key_events = journal_data.get("key_events", [])
    if key_events:
        lines.append("*Today's highlights:*")
        for event in key_events[:5]:
            lines.append(f"  • {event}")
        lines.append("")
    
    # Accomplishments
    accomplishments = journal_data.get("accomplishments", [])
    if accomplishments:
        lines.append("*Accomplishments:*")
        for acc in accomplishments[:5]:
            lines.append(f"  ✓ {acc}")
        lines.append("")
    
    # Challenges
    challenges = journal_data.get("challenges", [])
    if challenges:
        lines.append("*Challenges:*")
        for ch in challenges[:3]:
            lines.append(f"  ⚡ {ch}")
        lines.append("")
    
    # Tomorrow focus
    tomorrow = journal_data.get("tomorrow_focus", [])
    if tomorrow:
        lines.append("*Tomorrow's focus:*")
        for t in tomorrow[:5]:
            lines.append(f"  → {t}")
        lines.append("")
    
    # Reflection prompts
    if reflection_prompts:
        lines.append("*Reflect on:*")
        for prompt in reflection_prompts[:3]:
            lines.append(f"  💭 {prompt}")
        lines.append("")
    
    lines.append("_Reply with a voice note to journal more._")
    
    return "\n".join(lines)
