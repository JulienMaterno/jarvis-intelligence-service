"""
Follow-Up Draft Generation Routes

Generates short, contextual follow-up email drafts using Claude.
Called by the sync service when follow-up timers expire.
"""

import logging

from anthropic import AsyncAnthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(tags=["Follow-Up"])
logger = logging.getLogger("Jarvis.Intelligence.API.FollowUp")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class FollowUpDraftRequest(BaseModel):
    """Request to generate a follow-up email draft."""
    subject: str = Field(description="Original email subject")
    original_body: str = Field(default="", description="Original email body (truncated)")
    recipient_name: str = Field(description="Recipient name or email")
    days_since: int = Field(default=7, description="Days since original email")
    follow_up_count: int = Field(default=0, description="Number of follow-ups already sent")


class FollowUpDraftResponse(BaseModel):
    """Generated follow-up draft."""
    draft_body: str
    model_used: str


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/follow-up/generate-draft", response_model=FollowUpDraftResponse)
async def generate_follow_up_draft(request: FollowUpDraftRequest):
    """
    Generate a short, contextual follow-up email draft.

    Uses Claude Haiku for fast, cost-effective generation.
    The draft is 2-4 sentences, direct but friendly.
    """
    try:
        # Use Haiku for simple draft generation (fast + cheap)
        model = "claude-haiku-4-5-20251001"
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build the prompt based on follow-up count
        if request.follow_up_count == 0:
            tone_instruction = "This is the first follow-up. Be friendly and casual."
        elif request.follow_up_count == 1:
            tone_instruction = "This is the second follow-up. Be slightly more direct but still polite."
        else:
            tone_instruction = (
                f"This is follow-up #{request.follow_up_count + 1}. "
                "Be direct and concise. Consider mentioning this is a final check-in."
            )

        prompt = f"""Write a brief follow-up email body for Aaron.

Original email context:
- To: {request.recipient_name}
- Subject: {request.subject}
- Sent: {request.days_since} days ago
- Body excerpt: {request.original_body[:1500] if request.original_body else '(not available)'}

{tone_instruction}

Rules:
- Write ONLY the email body text (no subject line, no "Hi" greeting for follow-up #2+)
- 2-4 sentences maximum
- Reference the specific topic from the original email
- Professional but casual tone
- Do not be apologetic or overly formal
- Do not include a signature"""

        response = await client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        draft_body = response.content[0].text.strip()

        logger.info(
            f"Generated follow-up draft for '{request.subject}' "
            f"(#{request.follow_up_count + 1}, {len(draft_body)} chars)"
        )

        return FollowUpDraftResponse(
            draft_body=draft_body,
            model_used=model,
        )

    except Exception as e:
        logger.error(f"Failed to generate follow-up draft: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Draft generation failed: {str(e)}"
        )
