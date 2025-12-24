"""Briefing feature module."""

from app.features.briefing.meeting_briefing import (
    MeetingBriefing,
    get_upcoming_events_for_briefing,
    get_contact_context,
    generate_meeting_briefing,
    format_briefing_for_telegram,
)

__all__ = [
    "MeetingBriefing",
    "get_upcoming_events_for_briefing",
    "get_contact_context",
    "generate_meeting_briefing",
    "format_briefing_for_telegram",
]
