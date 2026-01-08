"""
Chat API Routes.

Provides conversational AI endpoint for Telegram and other clients.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.features.chat import ChatRequest, ChatResponse, get_chat_service
from app.core.database import supabase

logger = logging.getLogger("Jarvis.API.Chat")
router = APIRouter(tags=["Chat"])


class LocationUpdate(BaseModel):
    """Location update from user device (Telegram or iOS Shortcut)."""
    latitude: float
    longitude: float
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None


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


@router.post("/location")
async def update_location(location: LocationUpdate):
    """
    Update user's location (from Telegram live location or iOS Shortcut).
    
    The timezone can be auto-detected from coordinates using timezonefinder,
    or provided explicitly.
    """
    try:
        from datetime import datetime, timezone as tz
        
        # Try to detect timezone from coordinates
        detected_tz = location.timezone
        if not detected_tz:
            try:
                from timezonefinder import TimezoneFinder
                tf = TimezoneFinder()
                detected_tz = tf.timezone_at(lat=location.latitude, lng=location.longitude)
            except ImportError:
                logger.warning("timezonefinder not installed, using provided timezone or UTC")
                detected_tz = "UTC"
            except Exception as e:
                logger.warning(f"Timezone detection failed: {e}")
                detected_tz = "UTC"
        
        now = datetime.now(tz.utc).isoformat()
        
        # Upsert location data to sync_state
        updates = [
            {"key": "user_location", "value": f"{location.latitude},{location.longitude}", "updated_at": now},
            {"key": "user_timezone", "value": detected_tz or "UTC", "updated_at": now},
        ]
        
        if location.city:
            updates.append({"key": "user_city", "value": location.city, "updated_at": now})
        if location.country:
            updates.append({"key": "user_country", "value": location.country, "updated_at": now})
        
        for update in updates:
            supabase.table("sync_state").upsert(update, on_conflict="key").execute()
        
        logger.info(f"Location updated: {location.city or 'Unknown'}, TZ: {detected_tz}")
        
        return {
            "status": "updated",
            "latitude": location.latitude,
            "longitude": location.longitude,
            "timezone": detected_tz,
            "city": location.city,
            "country": location.country
        }
        
    except Exception as e:
        logger.exception("Location update error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/location")
async def get_location():
    """Get current stored location."""
    try:
        result = supabase.table("sync_state").select("key, value, updated_at").in_(
            "key", ["user_location", "user_timezone", "user_city", "user_country"]
        ).execute()
        
        location_data = {}
        for row in (result.data or []):
            location_data[row["key"]] = row["value"]
            if row["key"] == "user_location":
                location_data["updated_at"] = row["updated_at"]
        
        if not location_data:
            return {"status": "not_set", "message": "Share your location via Telegram or iOS Shortcut"}
        
        coords = location_data.get("user_location", "").split(",")
        return {
            "status": "ok",
            "latitude": float(coords[0]) if len(coords) > 0 else None,
            "longitude": float(coords[1]) if len(coords) > 1 else None,
            "timezone": location_data.get("user_timezone"),
            "city": location_data.get("user_city"),
            "country": location_data.get("user_country"),
            "updated_at": location_data.get("updated_at")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/health")
async def chat_health():
    """Check if chat service is healthy."""
    from app.features.letta import get_letta_service
    
    letta = get_letta_service()
    letta_status = await letta.health_check()
    
    return {
        "status": "ok",
        "model": "claude-haiku-4-5-20251001",
        "letta": letta_status
    }


# =============================================================================
# LETTA BATCH PROCESSING ENDPOINTS
# =============================================================================

@router.post("/chat/letta/consolidate")
async def consolidate_letta_messages(
    mode: str = "lightweight",
    limit: int = 100
):
    """
    Process unprocessed chat messages and send to Letta.
    
    Called by Cloud Scheduler:
    - Hourly: mode="lightweight" (just archival, ~$0.001/msg)
    - Daily: mode="full" (agent processing, ~$0.05/msg)
    
    Modes:
    - "lightweight": Insert to archival memory only (cheap)
    - "full": Full agent processing with memory block updates (expensive)
    
    This endpoint is idempotent - messages are marked as processed.
    """
    try:
        from app.features.letta import get_letta_service
        
        letta = get_letta_service()
        
        # Check if Letta is healthy first
        health = await letta.health_check()
        if health.get("status") != "healthy":
            return {
                "status": "skipped",
                "reason": "Letta unavailable",
                "letta_status": health
            }
        
        # Process unprocessed messages
        result = await letta.process_unprocessed_messages(mode=mode)
        
        return {
            "status": "success",
            "mode": mode,
            **result
        }
        
    except Exception as e:
        logger.exception("Letta consolidation error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/letta/daily-summary")
async def letta_daily_summary():
    """
    Generate and send a daily summary to Letta for memory block updates.
    
    Called by Cloud Scheduler once per day (evening).
    
    This:
    1. Aggregates today's conversations
    2. Extracts key topics, decisions, action items
    3. Sends to Letta agent for memory block updates
    
    Cost: ~$0.05-0.10 (one agent call)
    """
    try:
        from datetime import datetime, timedelta
        from app.features.letta import get_letta_service
        from app.features.chat.storage import get_chat_storage
        
        letta = get_letta_service()
        storage = get_chat_storage()
        
        # Check Letta health
        health = await letta.health_check()
        if health.get("status") != "healthy":
            return {
                "status": "skipped",
                "reason": "Letta unavailable",
                "letta_status": health
            }
        
        # Get today's messages
        today = datetime.now()
        messages = await storage.get_messages_for_date(today, include_processed=True)
        
        if not messages:
            return {
                "status": "skipped",
                "reason": "No messages today"
            }
        
        # Build summary using Claude (cheap with Haiku)
        from app.services.llm import ClaudeMultiAnalyzer
        llm = ClaudeMultiAnalyzer()
        
        conversation_text = "\n".join([
            f"{m['role'].upper()}: {m['content'][:500]}"
            for m in messages[:50]  # Limit to last 50 messages
        ])
        
        summary_prompt = f"""Analyze this day's conversations and extract:

1. KEY TOPICS (max 5): Main subjects discussed
2. DECISIONS (max 3): Any decisions Aaron made
3. ACTION ITEMS (max 5): Tasks or commitments

Return JSON:
{{
  "summary": "One paragraph summary of the day",
  "topics": ["topic1", "topic2"],
  "decisions": ["decision1"],
  "action_items": ["item1", "item2"]
}}

CONVERSATIONS:
{conversation_text[:8000]}"""

        response = llm.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": summary_prompt}]
        )
        
        import json
        result_text = response.content[0].text.strip()
        
        # Parse JSON
        try:
            if "{" in result_text:
                json_start = result_text.find("{")
                json_end = result_text.rfind("}") + 1
                summary_data = json.loads(result_text[json_start:json_end])
            else:
                summary_data = {"summary": result_text, "topics": [], "decisions": [], "action_items": []}
        except json.JSONDecodeError:
            summary_data = {"summary": result_text[:500], "topics": [], "decisions": [], "action_items": []}
        
        # Send to Letta for memory block updates
        result = await letta.consolidate_day(
            date=today,
            summary=summary_data.get("summary", "No summary"),
            key_topics=summary_data.get("topics", []),
            decisions=summary_data.get("decisions", []),
            action_items=summary_data.get("action_items", [])
        )
        
        return {
            "status": "success",
            "messages_analyzed": len(messages),
            "summary": summary_data,
            "letta_updated": result is not None
        }
        
    except Exception as e:
        logger.exception("Daily summary error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/letta/status")
async def letta_status():
    """
    Get current Letta status including memory blocks and unprocessed count.
    """
    try:
        from app.features.letta import get_letta_service
        from app.features.chat.storage import get_chat_storage
        
        letta = get_letta_service()
        storage = get_chat_storage()
        
        # Get health
        health = await letta.health_check()
        
        # Get memory blocks
        blocks = {}
        if health.get("status") == "healthy":
            blocks = await letta.get_memory_blocks()
        
        # Get unprocessed count
        unprocessed = await storage.get_unprocessed_count()
        
        return {
            "letta_health": health,
            "memory_blocks": blocks,
            "unprocessed_messages": unprocessed,
            "agent_id": letta.agent_id or "not configured"
        }
        
    except Exception as e:
        logger.exception("Letta status error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/usage")
async def chat_usage(days: int = 30):
    """
    Get chat usage statistics with cost breakdown.
    
    Returns:
        - Total messages in period
        - Token usage (input/output)
        - Costs (total, average, estimated monthly)
        - Daily breakdown for last 7 days
    """
    try:
        from app.features.chat.storage import get_chat_storage
        
        storage = get_chat_storage()
        stats = await storage.get_usage_stats(days=days)
        
        return {
            "status": "success",
            **stats
        }
        
    except Exception as e:
        logger.exception("Usage stats error")
        raise HTTPException(status_code=500, detail=str(e))
