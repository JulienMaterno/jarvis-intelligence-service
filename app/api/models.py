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
