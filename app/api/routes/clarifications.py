"""
Clarification API routes.

Handles:
- Listing pending clarifications
- Submitting answers to clarifications
- Skipping clarifications
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

import logging

from app.services.database import get_database
from app.features.clarification.service import (
    get_pending_clarifications,
    resolve_clarification,
)
from app.features.memory.service import get_memory_service

logger = logging.getLogger("Jarvis.Intelligence.Clarification")

router = APIRouter(tags=["Clarification"])


class ClarificationAnswer(BaseModel):
    answer: str
    skip: bool = False


class ClarificationResponse(BaseModel):
    id: str
    item: str
    question: str
    context: Optional[dict] = None
    record_type: Optional[str] = None
    created_at: str


@router.get("/pending/{user_id}")
async def list_pending_clarifications(user_id: int) -> List[ClarificationResponse]:
    """
    Get all pending clarifications for a user.
    
    Returns list of clarifications waiting for answers.
    """
    db = get_database()
    clarifications = await get_pending_clarifications(user_id, db)
    
    return [
        ClarificationResponse(
            id=c["id"],
            item=c["item"],
            question=c["question"],
            context=c.get("context"),
            record_type=c.get("record_type"),
            created_at=c["created_at"]
        )
        for c in clarifications
    ]


@router.post("/answer/{clarification_id}")
async def submit_clarification_answer(
    clarification_id: str,
    body: ClarificationAnswer
):
    """
    Submit an answer to a pending clarification.
    
    The answer will:
    1. Update the original record (meeting, reflection, etc.)
    2. Be stored as a memory for future reference
    3. Mark the clarification as resolved
    """
    db = get_database()
    memory_service = get_memory_service()
    
    if body.skip:
        # Mark as skipped
        try:
            db.client.table("pending_clarifications").update({
                "status": "skipped"
            }).eq("id", clarification_id).execute()
            return {"status": "skipped", "clarification_id": clarification_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # Resolve the clarification
    success = await resolve_clarification(
        clarification_id=clarification_id,
        answer=body.answer,
        db=db,
        memory_service=memory_service
    )
    
    if success:
        return {
            "status": "resolved",
            "clarification_id": clarification_id,
            "answer": body.answer
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to resolve clarification")


@router.delete("/clear/{user_id}")
async def clear_pending_clarifications(user_id: int):
    """
    Clear all pending clarifications for a user.
    
    Marks them as expired. Use sparingly.
    """
    db = get_database()
    
    try:
        result = db.client.table("pending_clarifications").update({
            "status": "expired"
        }).eq("user_id", user_id).eq("status", "pending").execute()
        
        cleared = len(result.data) if result.data else 0
        return {"status": "cleared", "count": cleared}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
