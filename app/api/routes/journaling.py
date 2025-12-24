"""
Journaling API Routes

Provides endpoints for generating evening journal prompts and analysis.

The new `/journal/evening-analysis` endpoint is the primary implementation.
The legacy `/journal/evening-prompt` endpoint wraps the new implementation for backwards compatibility.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import the enhanced analysis module (single source of truth)
from app.features.journaling.evening_analysis import (
    analyze_day_for_journal,
    JournalAnalysisRequest,
    JournalAnalysisResponse,
    ActivityData,
)

router = APIRouter(tags=["Journaling"])
logger = logging.getLogger("Jarvis.Intelligence.API.Journaling")


# =============================================================================
# LEGACY RESPONSE MODEL (for backwards compatibility)
# =============================================================================

class JournalPromptResponse(BaseModel):
    """Legacy response format with evening journal prompt."""
    status: str
    highlights: List[str] = Field(default_factory=list)
    reflection_prompts: List[str] = Field(default_factory=list)  # Legacy name
    reflection_questions: List[str] = Field(default_factory=list)  # New name
    observations: List[str] = Field(default_factory=list)
    people_summary: str = ""
    message: str = ""
    journal_content: str = ""


# =============================================================================
# PRIMARY ENDPOINT
# =============================================================================

@router.post("/journal/evening-analysis", response_model=JournalAnalysisResponse)
async def generate_evening_analysis(request: JournalAnalysisRequest) -> JournalAnalysisResponse:
    """
    Generate comprehensive evening journal analysis.
    
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
# LEGACY ENDPOINT (backwards compatibility - delegates to new implementation)
# =============================================================================

class LegacyActivityData(BaseModel):
    """Legacy activity data model - maps to new ActivityData format."""
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


class LegacyJournalPromptRequest(BaseModel):
    """Legacy request format - will be converted to JournalAnalysisRequest."""
    activity_data: LegacyActivityData
    user_name: Optional[str] = None
    timezone: str = "UTC"


def _convert_to_new_request(legacy_request: LegacyJournalPromptRequest) -> JournalAnalysisRequest:
    """Convert legacy request format to new format."""
    legacy_data = legacy_request.activity_data
    
    # Convert LegacyActivityData to ActivityData
    new_activity_data = ActivityData(
        meetings=legacy_data.meetings,
        calendar_events=legacy_data.calendar_events,
        emails=legacy_data.emails,
        tasks_completed=legacy_data.tasks_completed,
        tasks_created=legacy_data.tasks_created,
        reflections=legacy_data.reflections,
        highlights=legacy_data.highlights,
        reading=legacy_data.reading,
        screen_time=legacy_data.screen_time,
    )
    
    return JournalAnalysisRequest(
        activity_data=new_activity_data,
        user_name=legacy_request.user_name,
        timezone=legacy_request.timezone,
    )


def _convert_to_legacy_response(new_response: JournalAnalysisResponse) -> JournalPromptResponse:
    """Convert new response format to legacy format."""
    return JournalPromptResponse(
        status=new_response.status,
        highlights=new_response.highlights,
        reflection_prompts=new_response.reflection_questions,  # Legacy name
        reflection_questions=new_response.reflection_questions,
        observations=new_response.observations,
        people_summary="",  # Legacy field - not used in new implementation
        message=new_response.message,
        journal_content=new_response.journal_content,
    )


@router.post("/journal/evening-prompt", response_model=JournalPromptResponse)
async def generate_evening_journal_prompt(request: LegacyJournalPromptRequest) -> JournalPromptResponse:
    """
    [LEGACY] Generate an evening journal prompt.
    
    This endpoint is maintained for backwards compatibility.
    It internally converts the request and delegates to the new implementation.
    
    Consider migrating to `/journal/evening-analysis` for the full feature set.
    """
    try:
        # Convert to new format and delegate
        new_request = _convert_to_new_request(request)
        new_response = analyze_day_for_journal(new_request)
        
        # Convert back to legacy format
        return _convert_to_legacy_response(new_response)
        
    except Exception as exc:
        logger.exception("Failed to build evening journal prompt")
        raise HTTPException(status_code=500, detail=str(exc))
