"""
Beeper Service - Hybrid Database + Live Access
================================================
Provides access to Beeper chats and messages with two modes:

1. **Database Mode (Default)**: Fast, reliable, uses synced data from Supabase
2. **Live Mode**: Real-time data from beeper-bridge when explicitly needed

Use live mode only when:
- User explicitly asks for "latest" or "most recent" messages
- Database data might be stale (>15 min since sync)
- Need to verify real-time status

For most queries, database mode is faster and more reliable.
"""

import logging
import os
import httpx
from typing import Optional, List, Dict, Any
from app.core.database import supabase

logger = logging.getLogger("Jarvis.Intelligence.Beeper")

# Service URLs
SYNC_SERVICE_URL = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
BEEPER_BRIDGE_URL = os.getenv("BEEPER_BRIDGE_URL", "https://beeper.new-world-project.com")


class BeeperService:
    """Unified service for accessing Beeper data from database or live."""
    
    def __init__(self):
        self.db = supabase
        logger.info("Beeper service initialized (hybrid mode)")
    
    # =========================================================================
    # STATUS
    # =========================================================================
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get Beeper connectivity status.
        
        Checks:
        1. Database stats (synced chats/messages)
        2. Bridge connectivity (if reachable)
        
        Returns:
            Status dict with db_stats and bridge_status
        """
        result = {
            "status": "ok",
            "db_stats": {},
            "bridge_status": "unknown"
        }
        
        # Get database stats
        try:
            chats_count = self.db.table("beeper_chats") \
                .select("id", count="exact") \
                .execute()
            messages_count = self.db.table("beeper_messages") \
                .select("id", count="exact") \
                .execute()
            
            result["db_stats"] = {
                "chats": chats_count.count or 0,
                "messages": messages_count.count or 0
            }
        except Exception as e:
            logger.warning(f"Failed to get DB stats: {e}")
            result["db_stats"] = {"error": str(e)}
        
        # Check bridge connectivity
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{BEEPER_BRIDGE_URL}/health")
                if resp.status_code == 200:
                    bridge_data = resp.json()
                    result["bridge_status"] = "connected" if bridge_data.get("beeper_connected") else "disconnected"
                    result["platforms"] = list(bridge_data.get("accounts", {}).keys())
                else:
                    result["bridge_status"] = "error"
        except httpx.ConnectError:
            result["bridge_status"] = "offline"
        except httpx.TimeoutException:
            result["bridge_status"] = "timeout"
        except Exception as e:
            logger.warning(f"Failed to check bridge: {e}")
            result["bridge_status"] = "error"
        
        return result
    
    # =========================================================================
    # INBOX & CHATS
    # =========================================================================
    
    async def get_inbox(
        self,
        include_groups: bool = False,
        limit: int = 30,
        live: bool = False
    ) -> Dict[str, Any]:
        """
        Get inbox chats that need attention.
        
        Args:
            include_groups: Include group chats
            limit: Max chats per category
            live: Fetch from beeper-bridge instead of database
        
        Returns:
            Inbox organized by priority
        """
        if live:
            return await self._get_inbox_live(include_groups, limit)
        return self._get_inbox_db(include_groups, limit)
    
    def _get_inbox_db(self, include_groups: bool, limit: int) -> Dict[str, Any]:
        """Get inbox from database (fast)."""
        try:
            # Chats that need response (last message from them)
            needs_response = self.db.table("beeper_chats") \
                .select("*, contact:contacts(id, first_name, last_name, company)") \
                .eq("chat_type", "dm") \
                .eq("is_archived", False) \
                .eq("needs_response", True) \
                .order("last_message_at", desc=True) \
                .limit(limit) \
                .execute()
            
            # Other active DMs (last message from you)
            other_active = self.db.table("beeper_chats") \
                .select("*, contact:contacts(id, first_name, last_name, company)") \
                .eq("chat_type", "dm") \
                .eq("is_archived", False) \
                .eq("needs_response", False) \
                .order("last_message_at", desc=True) \
                .limit(limit) \
                .execute()
            
            result = {
                "needs_response": {
                    "count": len(needs_response.data),
                    "chats": self._format_chats(needs_response.data)
                },
                "other_active": {
                    "count": len(other_active.data),
                    "chats": self._format_chats(other_active.data)
                }
            }
            
            if include_groups:
                groups = self.db.table("beeper_chats") \
                    .select("*") \
                    .in_("chat_type", ["group", "channel"]) \
                    .eq("is_archived", False) \
                    .order("last_message_at", desc=True) \
                    .limit(limit) \
                    .execute()
                
                result["groups"] = {
                    "count": len(groups.data),
                    "chats": self._format_chats(groups.data)
                }
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get inbox from database: {e}")
            raise
    
    async def _get_inbox_live(self, include_groups: bool, limit: int) -> Dict[str, Any]:
        """Get inbox from beeper-bridge (real-time)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"limit": limit}
                if include_groups:
                    params["include_groups"] = "true"
                
                # Call sync service which will fetch live if needed
                response = await client.get(
                    f"{SYNC_SERVICE_URL}/beeper/inbox",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to get inbox live: {e}")
            raise
    
    async def get_chat_messages(
        self,
        beeper_chat_id: str,
        limit: int = 30,
        before: Optional[str] = None,
        live: bool = False
    ) -> Dict[str, Any]:
        """
        Get messages from a specific chat.
        
        Args:
            beeper_chat_id: Chat ID
            limit: Number of messages
            before: Get messages before this timestamp
            live: Fetch from beeper-bridge for real-time data
        
        Returns:
            Messages with chat context
        """
        if live:
            return await self._get_messages_live(beeper_chat_id, limit, before)
        return self._get_messages_db(beeper_chat_id, limit, before)
    
    def _get_messages_db(
        self,
        beeper_chat_id: str,
        limit: int,
        before: Optional[str]
    ) -> Dict[str, Any]:
        """Get messages from database."""
        try:
            query = self.db.table("beeper_messages") \
                .select("*, chat:beeper_chats(platform, chat_name, contact_id)") \
                .eq("beeper_chat_id", beeper_chat_id) \
                .order("timestamp", desc=True) \
                .limit(limit)
            
            if before:
                query = query.lt("timestamp", before)
            
            result = query.execute()
            
            # Get chat info
            chat_info = self.db.table("beeper_chats") \
                .select("*, contact:contacts(id, first_name, last_name, company)") \
                .eq("beeper_chat_id", beeper_chat_id) \
                .single() \
                .execute()
            
            return {
                "chat": chat_info.data,
                "messages": result.data,
                "count": len(result.data)
            }
        
        except Exception as e:
            logger.error(f"Failed to get messages from database: {e}")
            raise
    
    async def _get_messages_live(
        self,
        beeper_chat_id: str,
        limit: int,
        before: Optional[str]
    ) -> Dict[str, Any]:
        """Get messages from beeper-bridge (real-time)."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"limit": limit}
                if before:
                    params["before"] = before
                
                # URL encode the chat ID
                import urllib.parse
                encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
                
                response = await client.get(
                    f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/messages",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to get messages live: {e}")
            raise
    
    # =========================================================================
    # SENDING MESSAGES
    # =========================================================================
    
    async def send_message(
        self,
        beeper_chat_id: str,
        content: str,
        reply_to_event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message to a Beeper chat.
        
        Args:
            beeper_chat_id: Chat ID to send to
            content: Message text
            reply_to_event_id: Optional message ID to reply to
        
        Returns:
            Send status and details
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # URL encode the chat ID
                import urllib.parse
                encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
                
                payload = {"text": content}
                if reply_to_event_id:
                    payload["reply_to"] = reply_to_event_id
                
                response = await client.post(
                    f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/messages",
                    json=payload
                )
                response.raise_for_status()
                
                logger.info(f"Sent message to chat {beeper_chat_id[:20]}...")
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            raise
    
    async def mark_as_read(self, beeper_chat_id: str) -> Dict[str, Any]:
        """Mark all messages in a chat as read."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                import urllib.parse
                encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
                
                response = await client.post(
                    f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/read"
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            raise
    
    async def archive_chat(self, beeper_chat_id: str) -> Dict[str, Any]:
        """Archive a chat (inbox-zero workflow)."""
        try:
            # Update in database
            self.db.table("beeper_chats") \
                .update({"is_archived": True, "archived_at": "now()"}) \
                .eq("beeper_chat_id", beeper_chat_id) \
                .execute()
            
            # Also tell beeper-bridge (optional, for UI sync)
            async with httpx.AsyncClient(timeout=30.0) as client:
                import urllib.parse
                encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
                
                await client.post(
                    f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/archive"
                )
            
            return {"status": "archived", "beeper_chat_id": beeper_chat_id}
        
        except Exception as e:
            logger.error(f"Failed to archive chat: {e}")
            raise
    
    # =========================================================================
    # SEARCH
    # =========================================================================
    
    async def search_messages(
        self,
        query: str,
        platform: Optional[str] = None,
        contact_id: Optional[str] = None,
        limit: int = 30,
        live: bool = False
    ) -> Dict[str, Any]:
        """
        Search across message history.
        
        Args:
            query: Search query
            platform: Filter by platform
            contact_id: Filter by contact
            limit: Max results
            live: Search live data (usually not needed)
        
        Returns:
            Matching messages with context
        """
        if live:
            return await self._search_messages_live(query, platform, limit)
        return self._search_messages_db(query, platform, contact_id, limit)
    
    def _search_messages_db(
        self,
        query: str,
        platform: Optional[str],
        contact_id: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Search messages in database using full-text search."""
        try:
            # Use PostgreSQL full-text search
            search_query = self.db.table("beeper_messages") \
                .select("*, chat:beeper_chats(platform, chat_name, contact_id, contact:contacts(first_name, last_name))") \
                .text_search("content", query) \
                .order("timestamp", desc=True) \
                .limit(limit)
            
            if platform:
                search_query = search_query.eq("platform", platform)
            if contact_id:
                search_query = search_query.eq("contact_id", contact_id)
            
            result = search_query.execute()
            
            return {
                "query": query,
                "count": len(result.data),
                "messages": result.data
            }
        
        except Exception as e:
            logger.error(f"Failed to search messages in database: {e}")
            raise
    
    async def _search_messages_live(
        self,
        query: str,
        platform: Optional[str],
        limit: int
    ) -> Dict[str, Any]:
        """Search messages via beeper-bridge."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"q": query, "limit": limit}
                if platform:
                    params["platform"] = platform
                
                response = await client.get(
                    f"{BEEPER_BRIDGE_URL}/messages/search",
                    params=params
                )
                response.raise_for_status()
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to search messages live: {e}")
            raise
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _format_chats(self, chats: List[Dict]) -> List[Dict]:
        """Format chat data for API response."""
        formatted = []
        for chat in chats:
            contact = chat.get("contact", {}) if isinstance(chat.get("contact"), dict) else None
            
            formatted_chat = {
                "beeper_chat_id": chat["beeper_chat_id"],
                "platform": chat["platform"],
                "chat_type": chat["chat_type"],
                "chat_name": chat.get("chat_name"),
                "last_message_at": chat.get("last_message_at"),
                "last_message_preview": chat.get("last_message_preview"),
                "last_message_is_outgoing": chat.get("last_message_is_outgoing"),
                "unread_count": chat.get("unread_count", 0),
                "needs_response": chat.get("needs_response", False)
            }
            
            if contact:
                formatted_chat["contact"] = {
                    "id": contact.get("id"),
                    "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                    "company": contact.get("company")
                }
            
            formatted.append(formatted_chat)
        
        return formatted
