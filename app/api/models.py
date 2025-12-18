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
