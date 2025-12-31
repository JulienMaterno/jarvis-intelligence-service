"""
Beeper Messaging Routes
=======================
AI tools for reading and sending messages via Beeper.

These tools allow Claude to:
- List chats and unread messages
- Search message history
- Send messages (with user confirmation)
- Link chats to contacts

**Data Sources:**
- **Database (Default)**: Fast, reliable, synced every 15 minutes
- **Live Mode**: Real-time data from beeper-bridge when explicitly needed

Use `live=true` parameter only when:
- User explicitly asks for "latest" or "most recent" messages
- Need to verify real-time status
- Database data might be stale

Sending messages always goes through beeper-bridge in real-time.
"""

import logging
import os
import httpx
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.services.beeper import BeeperService

router = APIRouter(tags=["Beeper"])
logger = logging.getLogger("Jarvis.Intelligence.API.Beeper")

# Initialize the hybrid beeper service
beeper = BeeperService()

# The sync service handles sync operations
SYNC_SERVICE_URL = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")


# ============================================
# Models
# ============================================

class ChatInfo(BaseModel):
    """Information about a Beeper chat."""
    beeper_chat_id: str
    platform: str
    chat_name: Optional[str]
    contact_id: Optional[str]
    contact_name: Optional[str]
    contact_company: Optional[str]
    unread_count: int
    last_message_at: Optional[str]
    last_message_preview: Optional[str]


class MessageInfo(BaseModel):
    """Information about a Beeper message."""
    beeper_event_id: str
    beeper_chat_id: str
    platform: str
    sender_name: Optional[str]
    is_outgoing: bool
    content: Optional[str]
    timestamp: Optional[str]


class SendMessageRequest(BaseModel):
    """Request to send a message."""
    content: str
    reply_to_event_id: Optional[str] = None
    user_confirmed: bool = False  # MUST be True to actually send


class SendMessageResponse(BaseModel):
    """Response after sending a message."""
    status: str
    message: str
    platform: Optional[str] = None
    chat_name: Optional[str] = None
    message_preview: Optional[str] = None
    requires_confirmation: bool = False


class LinkChatRequest(BaseModel):
    """Request to link a chat to a contact."""
    contact_id: str


# ============================================
# Endpoints for Claude - Core Messaging
# ============================================

@router.get("/beeper/status")
async def get_beeper_status():
    """
    Check Beeper connectivity status.
    
    Returns:
        Connection status, available platforms, and account info.
    """
    try:
        result = await beeper.get_status()
        return result
    except Exception as e:
        logger.error(f"Failed to get Beeper status: {e}")
        return {"status": "unknown", "error": str(e)}


@router.get("/beeper/inbox")
async def get_inbox(
    include_groups: bool = False,
    limit: int = Query(30, ge=1, le=100),
    live: bool = Query(False, description="Fetch real-time data from Beeper (slower)")
):
    """
    Get the Beeper inbox - chats that need your attention.
    
    This is the PRIMARY view for managing messages. Uses inbox-zero workflow:
    - "needs_response" = DMs where the last message was from the other person (not you)
    - "other_active" = DMs where you sent the last message (ball is in their court)
    - Groups are lower priority and shown separately if requested
    
    💡 Tip: Use this first when the user asks about unread messages or what needs attention.
    
    **Data Source:**
    - Default: Database (fast, synced every 15 min)
    - `live=true`: Real-time from Beeper (slower, use only when explicitly needed)
    
    Args:
        include_groups: Also show group chats (usually lower priority)
        limit: Max chats per category
        live: Fetch real-time data instead of database
    
    Returns:
        Inbox organized by priority
    """
    return await beeper.get_inbox(include_groups, limit, live)


@router.get("/beeper/chats")
async def list_chats(
    platform: Optional[str] = None,
    unread_only: bool = False,
    unlinked_only: bool = False,
    limit: int = Query(20, ge=1, le=100),
    live: bool = Query(False, description="Fetch from live bridge instead of database")
):
    """
    List Beeper chats across all connected platforms.
    
    Use this to see recent conversations, check for unread messages,
    or find a specific chat to interact with.
    
    Args:
        platform: Filter by platform (whatsapp, telegram, linkedin, etc.)
        unread_only: Only show chats with unread messages
        unlinked_only: Only show chats not linked to a contact
        limit: Maximum chats to return
        live: Use live=true only when user needs real-time data
    
    Returns:
        List of chats with contact info where available.
    """
    # For filtered queries (platform, unread, unlinked), use database exclusively
    # Live mode doesn't support these filters efficiently
    if platform or unread_only or unlinked_only:
        # Database has these indexes, live bridge doesn't
        from app.core.database import supabase
        query = supabase.table("beeper_chats").select("*, contact:contacts(*)").order("updated_at", desc=True)
        
        if platform:
            query = query.eq("platform", platform)
        if unread_only:
            query = query.gt("unread_count", 0)
        if unlinked_only:
            query = query.is_("contact_id", "null")
        
        result = query.limit(limit).execute()
        return {"chats": result.data, "total": len(result.data)}
    
    # No filters - use standard inbox call
    return await beeper.get_inbox(include_groups=True, limit=limit, live=live)


@router.get("/beeper/unread")
async def get_unread_messages(limit: int = Query(50, ge=1, le=200)):
    """
    Get all unread messages across all platforms.
    
    This is useful for checking what messages need attention.
    Returns messages grouped by chat with contact info.
    
    Returns:
        Total unread count, number of chats, and recent messages per chat.
    """
    result = await beeper.get_unread_messages(limit)
    return result


@router.get("/beeper/chats/{beeper_chat_id}/messages")
async def get_chat_messages(
    beeper_chat_id: str,
    limit: int = Query(30, ge=1, le=100),
    before: Optional[str] = None,
    live: bool = Query(False, description="Fetch real-time messages from Beeper")
):
    """
    Get messages from a specific chat.
    
    Use this to read the conversation history with a specific person.
    
    **Data Source:**
    - Default: Database (fast, includes all synced messages)
    - `live=true`: Real-time from Beeper (use when user asks for "latest" messages)
    
    Args:
        beeper_chat_id: The chat ID (URL encoded if needed)
        limit: Number of messages to retrieve
        before: Get messages before this timestamp (for pagination)
        live: Fetch real-time data from Beeper
    
    Returns:
        List of messages, newest first.
    """
    return await beeper.get_chat_messages(beeper_chat_id, limit, before, live)


@router.get("/beeper/messages/search")
async def search_messages(
    q: str = Query(..., min_length=1, description="Search query"),
    platform: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = Query(30, ge=1, le=100),
    live: bool = Query(False, description="Search live messages instead of database")
):
    """
    Search across all message history.
    
    Use this to find specific conversations or information mentioned in messages.
    
    **Data Source:**
    - Default: Database (fast full-text search)
    - `live=true`: Search live Beeper data (rarely needed)
    
    Args:
        q: Search query (uses full-text search)
        platform: Filter by platform
        contact_id: Filter by contact (if chat is linked)
        limit: Maximum results
        live: Search live data
    
    Returns:
        Matching messages with chat context.
    """
    return await beeper.search_messages(q, platform, contact_id, limit, live)


@router.post("/beeper/chats/{beeper_chat_id}/send")
async def send_message(beeper_chat_id: str, request: SendMessageRequest) -> SendMessageResponse:
    """
    Send a message via Beeper.
    
    ⚠️ IMPORTANT: This will send a REAL message to a REAL person.
    
    The `user_confirmed` field MUST be set to `true` after showing the user
    the message and recipient and getting their explicit approval.
    
    Workflow:
    1. First call: Set user_confirmed=false to preview the message
    2. Show user: "Send '{content}' to {recipient}?"
    3. If user approves: Call again with user_confirmed=true
    
    Args:
        beeper_chat_id: The chat to send to
        content: The message text
        reply_to_event_id: Optional - reply to a specific message
        user_confirmed: MUST be true to actually send
    
    Returns:
        If user_confirmed=false: Confirmation prompt
        If user_confirmed=true: Send result
    """
    if not request.user_confirmed:
        # Get chat info for confirmation from database
        try:
            from app.core.database import supabase
            chat = supabase.table("beeper_chats") \
                .select("platform, chat_name, contact:contacts(first_name, last_name, company)") \
                .eq("beeper_chat_id", beeper_chat_id) \
                .single() \
                .execute()
            
            chat_data = chat.data
            contact = chat_data.get("contact", {}) if chat_data.get("contact") else None
            
            chat_name = chat_data.get("chat_name", "Unknown")
            if contact:
                name_parts = [contact.get("first_name"), contact.get("last_name")]
                chat_name = " ".join(filter(None, name_parts)) or chat_name
            
            platform = chat_data.get("platform", "unknown")
            
            return SendMessageResponse(
                status="confirmation_required",
                message=f"Ready to send message to {chat_name} on {platform}",
                platform=platform,
                chat_name=chat_name,
                message_preview=request.content[:100] + ("..." if len(request.content) > 100 else ""),
                requires_confirmation=True
            )
        except Exception as e:
            logger.error(f"Error getting chat info: {e}")
            return SendMessageResponse(
                status="confirmation_required",
                message=f"Ready to send message to chat {beeper_chat_id}",
                message_preview=request.content[:100],
                requires_confirmation=True
            )
    
    # User has confirmed - actually send via beeper service
    logger.info(f"Sending confirmed message to {beeper_chat_id}")
    
    result = await beeper.send_message(
        beeper_chat_id,
        request.content,
        request.reply_to_event_id
    )
    
    return SendMessageResponse(
        status="sent",
        message=f"Message sent successfully",
        message_preview=result.get("message_preview"),
        requires_confirmation=False
    )


@router.patch("/beeper/chats/{beeper_chat_id}/link-contact")
async def link_chat_to_contact(beeper_chat_id: str, request: LinkChatRequest):
    """
    Link a Beeper chat to a CRM contact.
    
    Use this when automatic linking failed or you want to correct a link.
    
    Args:
        beeper_chat_id: The chat to link
        contact_id: The contact to link to
    """
    result = await beeper.link_chat_to_contact(beeper_chat_id, request.contact_id)
    return result


@router.post("/beeper/sync")
async def trigger_sync(full: bool = False):
    """
    Trigger a Beeper sync from the bridge.
    
    This fetches new messages from all platforms and stores them in the database.
    
    Args:
        full: If True, resync all messages (up to 30 days). Otherwise incremental.
    
    Returns:
        Sync statistics.
    """
    result = await beeper.trigger_sync(full)
    return result


# ============================================
# Inbox-Zero Workflow Actions
# ============================================

@router.post("/beeper/chats/{beeper_chat_id}/archive")
async def archive_chat(beeper_chat_id: str):
    """
    Archive a chat (marks it as "handled" in inbox-zero workflow).
    
    Use this after responding to someone or when no response is needed.
    The chat will no longer appear in the "needs_response" list.
    
    💡 Think of archiving like "done" in a task list - you've handled it.
    """
    result = await beeper.archive_chat(beeper_chat_id)
    return result


@router.post("/beeper/chats/{beeper_chat_id}/unarchive")
async def unarchive_chat(beeper_chat_id: str):
    """
    Unarchive a chat (brings it back to active inbox).
    
    Use this if you need to follow up on an archived conversation.
    """
    result = await beeper.unarchive_chat(beeper_chat_id)
    return result


@router.post("/beeper/chats/{beeper_chat_id}/mark-read")
async def mark_read(beeper_chat_id: str):
    """
    Mark all messages in a chat as read.
    """
    result = await beeper.mark_as_read(beeper_chat_id)
    return result


@router.get("/beeper/groups")
async def list_groups(
    limit: int = Query(20, ge=1, le=50),
    live: bool = Query(False, description="Fetch from live bridge instead of database")
):
    """
    List group chats (lower priority than DMs).
    
    Groups are generally less urgent in the inbox-zero model.
    Use this when the user specifically asks about groups.
    
    Args:
        limit: Max groups to return
        live: Use live=true only when user needs real-time data
    """
    result = await beeper.get_inbox(include_groups=True, limit=limit, live=live)
    # Filter to only groups
    groups = [c for c in result.get("chats", []) if c.get("is_group", False)]
    return {"groups": groups, "total": len(groups)}
