"""
Chat API Routes.

Provides conversational AI endpoint for Telegram and other clients.
"""

import logging
from fastapi import APIRouter, HTTPException

from app.features.chat import ChatRequest, ChatResponse, get_chat_service

logger = logging.getLogger("Jarvis.API.Chat")
router = APIRouter(tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a conversational message with tool use.
    
    This endpoint allows natural language interaction with the knowledge database.
    Claude will automatically use tools to:
    - Query data (meetings, contacts, tasks, etc.)
    - Create records (tasks, reflections)
    - Search and retrieve information
    
    Example requests:
    - "When did I last meet John?"
    - "Create a task to follow up with Sarah"
    - "What meetings do I have this week?"
    - "Add to my project-jarvis reflection: implemented chat feature"
    """
    try:
        service = get_chat_service()
        response = await service.process_message(request)
        
        logger.info(f"Chat processed. Tools used: {response.tools_used}")
        return response
        
    except Exception as e:
        logger.exception("Chat endpoint error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/health")
async def chat_health():
    """Check if chat service is healthy."""
    return {"status": "ok", "model": "claude-sonnet-4-5-20250929"}
