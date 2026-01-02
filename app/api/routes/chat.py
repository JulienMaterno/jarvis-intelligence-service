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
    return {"status": "ok", "model": "claude-haiku-4-5-20250929"}
