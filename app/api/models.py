from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class TranscriptRequest(BaseModel):
    transcript: str
    filename: str
    recording_date: Optional[str] = None
    audio_duration_seconds: Optional[float] = None
    language: Optional[str] = None

class TranscriptProcessRequest(BaseModel):
    transcript_id: str
    
class AnalysisResponse(BaseModel):
    status: str
    analysis: Dict[str, Any]
    db_records: Dict[str, Any]

class LinkContactRequest(BaseModel):
    contact_id: str

class CreateContactRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    company: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    link_to_meeting_id: Optional[str] = None  # Optionally link to a meeting after creation

# =========================================================================
# EMAIL MODELS
# =========================================================================

class CreateEmailRequest(BaseModel):
    subject: str
    from_email: str
    to_emails: List[str]
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_name: Optional[str] = None
    cc_emails: Optional[List[str]] = None
    direction: str = "inbound"  # 'inbound' or 'outbound'
    sent_at: Optional[str] = None
    received_at: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    meeting_id: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    has_attachments: Optional[bool] = False
    attachment_names: Optional[List[str]] = None
    source_provider: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

class EmailResponse(BaseModel):
    status: str
    email_id: str
    email_url: str
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None

class LinkEmailRequest(BaseModel):
    meeting_id: Optional[str] = None
    contact_id: Optional[str] = None

# =========================================================================
# CALENDAR EVENT MODELS
# =========================================================================

class CreateCalendarEventRequest(BaseModel):
    title: str
    start_time: str  # ISO timestamp
    end_time: str    # ISO timestamp
    description: Optional[str] = None
    location: Optional[str] = None
    organizer_email: Optional[str] = None
    organizer_name: Optional[str] = None
    attendees: Optional[List[Dict[str, Any]]] = None
    all_day: Optional[bool] = False
    status: Optional[str] = "confirmed"
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    meeting_id: Optional[str] = None
    email_id: Optional[str] = None
    event_type: Optional[str] = None
    tags: Optional[List[str]] = None
    meeting_url: Optional[str] = None
    is_recurring: Optional[bool] = False
    recurrence_rule: Optional[str] = None
    source_provider: Optional[str] = None
    source_event_id: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

class CalendarEventResponse(BaseModel):
    status: str
    event_id: str
    event_url: str
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None

class LinkCalendarEventRequest(BaseModel):
    meeting_id: Optional[str] = None
    contact_id: Optional[str] = None

# =========================================================================
# INTERACTION MODELS
# =========================================================================

class ContactInteractionsResponse(BaseModel):
    status: str
    contact_id: str
    contact_name: str
    total_interactions: int
    interactions: List[Dict[str, Any]]
    summary: Dict[str, Any]  # Contains counts by type

class ContactSummaryResponse(BaseModel):
    status: str
    contact: Dict[str, Any]
    interaction_counts: Dict[str, int]
    recent_interactions: List[Dict[str, Any]]
    upcoming_events: List[Dict[str, Any]]

# =========================================================================
# DAILY JOURNAL ANALYSIS MODELS
# =========================================================================

class DailyActivityData(BaseModel):
    """Raw activity data collected for the day."""

    meetings: List[Dict[str, Any]] = Field(default_factory=list)
    calendar_events: List[Dict[str, Any]] = Field(default_factory=list)
    emails: List[Dict[str, Any]] = Field(default_factory=list)
    tasks_completed: List[Dict[str, Any]] = Field(default_factory=list)
    tasks_created: List[Dict[str, Any]] = Field(default_factory=list)
    reflections: List[Dict[str, Any]] = Field(default_factory=list)
    journals: List[Dict[str, Any]] = Field(default_factory=list)

class JournalPromptRequest(BaseModel):
    """Request for AI-generated evening journal prompt."""
    activity_data: DailyActivityData
    user_name: Optional[str] = None
    timezone: Optional[str] = "UTC"

class JournalPromptResponse(BaseModel):
    """AI-generated evening journal prompt."""

    status: str
    highlights: List[str]
    reflection_prompts: List[str]
    people_summary: Optional[str] = Field(
        default=None,
        description="Summary of the people referenced in today's activity stream.",
    )
    message: str
