"""
Messaging Tools for Chat.

This module contains tools for Beeper messaging operations including
inbox management, sending messages, and chat operations.
"""

import os
import httpx
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from app.core.database import supabase
from .base import logger, _sanitize_ilike


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

MESSAGING_TOOLS = [
    {
        "name": "get_beeper_inbox",
        "description": """Get the Beeper inbox - chats that need your attention across WhatsApp, LinkedIn, Telegram, etc.

Uses inbox-zero workflow:
- 'needs_response': DMs where the other person sent the last message (awaiting your reply)
- 'other_active': DMs where you sent the last message (ball in their court)

Use this when user asks about:
- 'Who do I need to reply to?'
- 'Any unread messages?'
- 'What messages need my attention?'
- 'Show my WhatsApp/LinkedIn/Telegram messages'""",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_groups": {
                    "type": "boolean",
                    "description": "Include group chats (usually lower priority)",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Max chats per category",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_beeper_chat_messages",
        "description": """Get messages from a specific Beeper chat.

Use this to read the conversation history with a specific person.
First use get_beeper_inbox or search_beeper_messages to find the beeper_chat_id.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID (e.g., '!abc123:beeper.local')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to retrieve",
                    "default": 20
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "search_beeper_messages",
        "description": """Search across all Beeper message history.

Use this to find specific conversations or information mentioned in messages.
Supports full-text search across WhatsApp, LinkedIn, Telegram, etc.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "platform": {
                    "type": "string",
                    "enum": ["whatsapp", "linkedin", "telegram"],
                    "description": "Filter by platform (optional)"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Filter by contact name (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_beeper_contact_messages",
        "description": """Get all message history with a specific contact across all platforms.

Use when user asks:
- 'What did John send me?'
- 'Show messages with Sarah'
- 'When did I last talk to [name]?'

First searches contacts to find the contact_id, then gets all messages.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name of the contact"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max messages to return",
                    "default": 30
                }
            },
            "required": ["contact_name"]
        }
    },
    {
        "name": "archive_beeper_chat",
        "description": """Archive a Beeper chat (marks as 'done' for inbox-zero).

Use after user has responded to a chat or wants to dismiss it.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to archive"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "unarchive_beeper_chat",
        "description": "Unarchive a previously archived Beeper chat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to unarchive"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "send_beeper_message",
        "description": """Send a message via Beeper to WhatsApp, LinkedIn, Telegram, etc.

IMPORTANT: This will actually send the message! Always confirm with user first.
The two-step process:
1. Call with user_confirmed=false to preview the message
2. Call again with user_confirmed=true after user confirms""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to send to"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Or specify contact name (will look up chat)"
                },
                "message": {
                    "type": "string",
                    "description": "The message content to send"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Set false to preview, true to actually send"
                }
            },
            "required": ["message", "user_confirmed"]
        }
    },
    {
        "name": "mark_beeper_read",
        "description": "Mark messages in a Beeper chat as read.",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "get_beeper_status",
        "description": "Check Beeper bridge connection status and health.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_beeper_http_headers() -> Dict[str, str]:
    """Get HTTP headers for Beeper bridge API calls."""
    headers = {
        "Content-Type": "application/json",
    }
    # Bridge requires X-API-Key for authentication (fail-closed if not set)
    bridge_api_key = os.getenv("BEEPER_BRIDGE_API_KEY")
    if not bridge_api_key:
        logger.warning("BEEPER_BRIDGE_API_KEY not set - bridge calls will fail")
    headers["X-API-Key"] = bridge_api_key or ""
    return headers


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _get_beeper_inbox(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get the Beeper inbox with inbox-zero workflow."""
    try:
        include_groups = params.get("include_groups", False)
        limit = params.get("limit", 10)

        # Query chats that need response (not archived, not outgoing last message)
        needs_response_query = supabase.table("beeper_chats").select(
            "beeper_chat_id, platform, chat_type, chat_name, contact_id"
        ).eq("is_archived", False).eq("needs_response", True)

        if not include_groups:
            needs_response_query = needs_response_query.eq("chat_type", "dm")

        needs_response_result = needs_response_query.limit(limit).execute()

        # Query other active chats (not archived, outgoing last message)
        other_active_query = supabase.table("beeper_chats").select(
            "beeper_chat_id, platform, chat_type, chat_name, contact_id"
        ).eq("is_archived", False).eq("needs_response", False)

        if not include_groups:
            other_active_query = other_active_query.eq("chat_type", "dm")

        other_active_result = other_active_query.limit(limit).execute()

        # Format responses
        needs_response = []
        for chat in (needs_response_result.data or []):
            # Get last message
            last_msg = supabase.table("beeper_messages").select(
                "content, timestamp, is_outgoing"
            ).eq("beeper_chat_id", chat["beeper_chat_id"]
            ).order("timestamp", desc=True).limit(1).execute()

            last_message = last_msg.data[0] if last_msg.data else None

            needs_response.append({
                "chat_id": chat["beeper_chat_id"],
                "platform": chat.get("platform"),
                "name": chat.get("chat_name"),
                "last_message": last_message.get("content", "")[:100] if last_message else "",
                "timestamp": last_message.get("timestamp") if last_message else None
            })

        other_active = []
        for chat in (other_active_result.data or []):
            last_msg = supabase.table("beeper_messages").select(
                "content, timestamp, is_outgoing"
            ).eq("beeper_chat_id", chat["beeper_chat_id"]
            ).order("timestamp", desc=True).limit(1).execute()

            last_message = last_msg.data[0] if last_msg.data else None

            other_active.append({
                "chat_id": chat["beeper_chat_id"],
                "platform": chat.get("platform"),
                "name": chat.get("chat_name"),
                "last_message": last_message.get("content", "")[:100] if last_message else "",
                "timestamp": last_message.get("timestamp") if last_message else None
            })

        return {
            "needs_response": needs_response,
            "needs_response_count": len(needs_response),
            "other_active": other_active,
            "other_active_count": len(other_active)
        }
    except Exception as e:
        logger.error(f"Error getting Beeper inbox: {e}")
        return {"error": str(e)}


def _get_beeper_chat_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get messages from a specific Beeper chat."""
    try:
        beeper_chat_id = params.get("beeper_chat_id")
        limit = params.get("limit", 20)

        if not beeper_chat_id:
            return {"error": "beeper_chat_id is required"}

        # Get chat info
        chat_result = supabase.table("beeper_chats").select(
            "chat_name, platform, chat_type"
        ).eq("beeper_chat_id", beeper_chat_id).execute()

        chat_info = chat_result.data[0] if chat_result.data else {}

        # Get messages
        messages_result = supabase.table("beeper_messages").select(
            "content, is_outgoing, timestamp"
        ).eq("beeper_chat_id", beeper_chat_id
        ).order("timestamp", desc=True).limit(limit).execute()

        messages = []
        for msg in reversed(messages_result.data or []):
            messages.append({
                "content": msg.get("content"),
                "is_outgoing": msg.get("is_outgoing"),
                "timestamp": msg.get("timestamp"),
                "sender": "You" if msg.get("is_outgoing") else chat_info.get("chat_name", "Them")
            })

        return {
            "chat_id": beeper_chat_id,
            "chat_name": chat_info.get("chat_name"),
            "platform": chat_info.get("platform"),
            "messages": messages,
            "count": len(messages)
        }
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return {"error": str(e)}


def _search_beeper_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search across all Beeper message history."""
    try:
        query = params.get("query", "")
        platform = params.get("platform")
        contact_name = params.get("contact_name")
        limit = params.get("limit", 20)

        if not query:
            return {"error": "Search query is required"}

        # Build search query
        db_limit = limit * 2 if contact_name else limit
        search_query = supabase.table("beeper_messages").select(
            "beeper_chat_id, content, is_outgoing, timestamp"
        ).ilike("content", f"%{query}%").order("timestamp", desc=True)

        if platform:
            search_query = search_query.eq("platform", platform)

        search_query = search_query.limit(db_limit)

        result = search_query.execute()

        messages = []
        for msg in (result.data or []):
            # Get chat info
            chat_result = supabase.table("beeper_chats").select(
                "chat_name, platform"
            ).eq("beeper_chat_id", msg["beeper_chat_id"]).execute()

            chat_info = chat_result.data[0] if chat_result.data else {}

            # Filter by contact name if specified (requires join to contacts, so post-filter)
            if contact_name and contact_name.lower() not in (chat_info.get("chat_name") or "").lower():
                continue

            messages.append({
                "chat_id": msg["beeper_chat_id"],
                "chat_name": chat_info.get("chat_name"),
                "platform": chat_info.get("platform"),
                "content": msg.get("content"),
                "is_outgoing": msg.get("is_outgoing"),
                "timestamp": msg.get("timestamp")
            })

        return {
            "messages": messages,
            "count": len(messages),
            "query": query
        }
    except Exception as e:
        logger.error(f"Error searching messages: {e}")
        return {"error": str(e)}


def _get_beeper_contact_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get all message history with a specific contact."""
    try:
        contact_name = params.get("contact_name", "")
        limit = params.get("limit", 30)

        if not contact_name:
            return {"error": "contact_name is required"}

        # Find contact
        safe_contact_name = _sanitize_ilike(contact_name)
        contact_result = supabase.table("contacts").select("id").or_(
            f"first_name.ilike.%{safe_contact_name}%,last_name.ilike.%{safe_contact_name}%"
        ).is_("deleted_at", "null").limit(1).execute()

        if not contact_result.data:
            # Try to find by chat name directly
            chat_result = supabase.table("beeper_chats").select(
                "beeper_chat_id"
            ).ilike("chat_name", f"%{contact_name}%").limit(1).execute()

            if not chat_result.data:
                return {"error": f"Contact '{contact_name}' not found"}

            # Get messages from this chat
            beeper_chat_id = chat_result.data[0]["beeper_chat_id"]
            return _get_beeper_chat_messages({"beeper_chat_id": beeper_chat_id, "limit": limit})

        contact_id = contact_result.data[0]["id"]

        # Get all chats with this contact
        chats_result = supabase.table("beeper_chats").select(
            "beeper_chat_id, platform, chat_name"
        ).eq("contact_id", contact_id).execute()

        all_messages = []
        for chat in (chats_result.data or []):
            messages_result = supabase.table("beeper_messages").select(
                "content, is_outgoing, timestamp"
            ).eq("beeper_chat_id", chat["beeper_chat_id"]
            ).order("timestamp", desc=True).limit(max(limit // len(chats_result.data), 1)).execute()

            for msg in (messages_result.data or []):
                all_messages.append({
                    "platform": chat.get("platform"),
                    "chat_name": chat.get("chat_name"),
                    "content": msg.get("content"),
                    "is_outgoing": msg.get("is_outgoing"),
                    "timestamp": msg.get("timestamp")
                })

        # Sort by timestamp
        all_messages.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        return {
            "contact_name": contact_name,
            "messages": all_messages[:limit],
            "count": len(all_messages[:limit])
        }
    except Exception as e:
        logger.error(f"Error getting contact messages: {e}")
        return {"error": str(e)}


def _archive_beeper_chat(params: Dict[str, Any]) -> Dict[str, Any]:
    """Archive a Beeper chat."""
    try:
        beeper_chat_id = params.get("beeper_chat_id")
        if not beeper_chat_id:
            return {"error": "beeper_chat_id is required"}

        supabase.table("beeper_chats").update({
            "is_archived": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("beeper_chat_id", beeper_chat_id).execute()

        return {
            "success": True,
            "chat_id": beeper_chat_id,
            "message": "Chat archived (marked as done)"
        }
    except Exception as e:
        logger.error(f"Error archiving chat: {e}")
        return {"error": str(e)}


def _unarchive_beeper_chat(params: Dict[str, Any]) -> Dict[str, Any]:
    """Unarchive a Beeper chat."""
    try:
        beeper_chat_id = params.get("beeper_chat_id")
        if not beeper_chat_id:
            return {"error": "beeper_chat_id is required"}

        supabase.table("beeper_chats").update({
            "is_archived": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("beeper_chat_id", beeper_chat_id).execute()

        return {
            "success": True,
            "chat_id": beeper_chat_id,
            "message": "Chat unarchived"
        }
    except Exception as e:
        logger.error(f"Error unarchiving chat: {e}")
        return {"error": str(e)}


def _send_beeper_message(params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message via Beeper."""
    import urllib.parse

    beeper_chat_id = params.get("beeper_chat_id")
    contact_name = params.get("contact_name")
    message = params.get("message", "").strip()
    user_confirmed = params.get("user_confirmed", False)
    last_user_message = params.get("_last_user_message", "")

    if not message:
        return {"error": "message is required"}

    # Find chat ID if contact name provided
    if not beeper_chat_id and contact_name:
        chat_result = supabase.table("beeper_chats").select(
            "beeper_chat_id, platform, chat_name"
        ).ilike("chat_name", f"%{contact_name}%").eq("chat_type", "dm").limit(1).execute()

        if chat_result.data:
            beeper_chat_id = chat_result.data[0]["beeper_chat_id"]
        else:
            return {"error": f"No chat found with contact '{contact_name}'"}

    if not beeper_chat_id:
        return {"error": "Either beeper_chat_id or contact_name is required"}

    # Get chat info
    chat_result = supabase.table("beeper_chats").select(
        "chat_name, platform"
    ).eq("beeper_chat_id", beeper_chat_id).execute()

    chat_info = chat_result.data[0] if chat_result.data else {}

    # Preview mode
    if not user_confirmed:
        return {
            "status": "preview",
            "chat_id": beeper_chat_id,
            "platform": chat_info.get("platform"),
            "recipient": chat_info.get("chat_name"),
            "message_preview": message,
            "instructions": "Ask user to confirm with 'yes send it' or 'send'"
        }

    # Verify user actually confirmed in their message
    confirmation_phrases = ["yes", "send", "confirm", "go ahead", "do it", "proceed"]
    if not any(phrase in last_user_message.lower() for phrase in confirmation_phrases):
        logger.warning(f"Send attempted without confirmation. User message: '{last_user_message}'")
        return {
            "status": "needs_confirmation",
            "message": "Please explicitly confirm you want to send this message (say 'yes' or 'send it')"
        }

    # Actually send the message via the bridge
    beeper_bridge_url = os.getenv("BEEPER_BRIDGE_URL", "http://localhost:8377")
    encoded_chat_id = urllib.parse.quote(beeper_chat_id, safe='')

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{beeper_bridge_url}/chats/{encoded_chat_id}/send",
                headers=_get_beeper_http_headers(),
                json={
                    "text": message
                }
            )

            if response.status_code == 200:
                logger.info(f"Sent Beeper message to {chat_info.get('chat_name')} on {chat_info.get('platform')}")
                return {
                    "success": True,
                    "chat_id": beeper_chat_id,
                    "platform": chat_info.get("platform"),
                    "recipient": chat_info.get("chat_name"),
                    "message": f"Message sent to {chat_info.get('chat_name')} via {chat_info.get('platform')}"
                }
            else:
                return {"error": f"Failed to send message: {response.text[:200]}"}

    except httpx.TimeoutException:
        return {"error": "Beeper bridge timeout - please try again"}
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {"error": str(e)}


def _mark_beeper_read(params: Dict[str, Any]) -> Dict[str, Any]:
    """Mark messages in a Beeper chat as read."""
    import urllib.parse

    try:
        beeper_chat_id = params.get("beeper_chat_id")
        if not beeper_chat_id:
            return {"error": "beeper_chat_id is required"}

        beeper_bridge_url = os.getenv("BEEPER_BRIDGE_URL", "http://localhost:8377")
        encoded_chat_id = urllib.parse.quote(beeper_chat_id, safe='')

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{beeper_bridge_url}/chats/{encoded_chat_id}/read",
                    headers=_get_beeper_http_headers(),
                )

                if response.status_code == 200:
                    return {
                        "success": True,
                        "chat_id": beeper_chat_id,
                        "message": "Marked as read"
                    }
                else:
                    return {"error": f"Failed to mark as read: {response.text[:200]}"}

        except httpx.TimeoutException:
            return {"error": "Beeper bridge timeout"}
    except Exception as e:
        logger.error(f"Error marking as read: {e}")
        return {"error": str(e)}


def _get_beeper_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Check Beeper bridge connection status."""
    beeper_bridge_url = os.getenv("BEEPER_BRIDGE_URL", "http://localhost:8377")
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{beeper_bridge_url}/health")

            if response.status_code == 200:
                result = response.json()
                return {
                    "status": "connected",
                    "bridge_url": beeper_bridge_url,
                    "health": result
                }
            else:
                return {
                    "status": "error",
                    "bridge_url": beeper_bridge_url,
                    "error": f"Health check failed: {response.status_code}"
                }

    except httpx.TimeoutException:
        return {
            "status": "unreachable",
            "bridge_url": beeper_bridge_url,
            "error": "Beeper bridge timeout"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
