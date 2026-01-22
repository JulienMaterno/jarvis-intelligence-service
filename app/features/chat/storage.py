"""
Chat Message Storage Service

Stores every chat message in Supabase for:
1. Complete audit trail
2. Letta processing queue
3. Historical analysis
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from app.api.dependencies import get_database
from app.core.logging_utils import sanitize_log_message

logger = logging.getLogger("Jarvis.Intelligence.ChatStorage")


class ChatMessageStorage:
    """
    Manages raw storage of all chat messages.
    
    Every message is stored here, regardless of whether
    Mem0 or Letta process it.
    """
    
    def __init__(self):
        self._current_session_id: Optional[str] = None
        self._session_start: Optional[datetime] = None
        
    def _get_or_create_session(self) -> str:
        """
        Get current session ID or create new one.
        
        Sessions auto-expire after 4 hours of inactivity.
        """
        now = datetime.now(timezone.utc)
        
        # Check if we need a new session
        if self._current_session_id is None or self._session_start is None:
            self._current_session_id = str(uuid.uuid4())
            self._session_start = now
        elif (now - self._session_start) > timedelta(hours=4):
            # Session expired, create new one
            self._current_session_id = str(uuid.uuid4())
            self._session_start = now
            
        return self._current_session_id
    
    async def store_message(
        self,
        role: str,
        content: str,
        source: str = "telegram",
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        tools_used: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Store a single message.
        
        Args:
            role: 'user', 'assistant', or 'system'
            content: Message content
            source: 'telegram', 'web', 'api', 'voice'
            metadata: Additional context (attachments, model, etc.)
            user_id: Telegram user ID (for multi-user support)
            tools_used: List of tools used (for assistant messages)
            
        Returns:
            Message ID if successful
        """
        try:
            db = get_database()
            session_id = self._get_or_create_session()
            
            record = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "source": source,
                "metadata": metadata or {},
                "letta_processed": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Add optional fields
            if user_id is not None:
                record["user_id"] = user_id
            if tools_used:
                record["tools_used"] = tools_used
            
            result = db.client.table("chat_messages").insert(record).execute()
            
            if result.data:
                msg_id = result.data[0].get("id")
                # Sanitize content before logging to avoid PII leakage
                safe_content = sanitize_log_message(content[:50])
                logger.debug(f"Stored {role} message: {safe_content}...")
                return msg_id
            return None
            
        except Exception as e:
            logger.error(f"Failed to store chat message: {e}")
            return None
    
    async def store_exchange(
        self,
        user_message: str,
        assistant_response: str,
        source: str = "telegram",
        user_metadata: Optional[Dict] = None,
        assistant_metadata: Optional[Dict] = None,
        user_id: Optional[int] = None,
        tools_used: Optional[List[str]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Store a complete user-assistant exchange.
        
        Returns tuple of (user_msg_id, assistant_msg_id)
        """
        user_msg_id = await self.store_message(
            role="user",
            content=user_message,
            source=source,
            metadata=user_metadata,
            user_id=user_id
        )
        
        assistant_msg_id = await self.store_message(
            role="assistant",
            content=assistant_response,
            source=source,
            metadata=assistant_metadata,
            user_id=user_id,
            tools_used=tools_used
        )
        
        return user_msg_id, assistant_msg_id
    
    async def get_messages_for_date(
        self,
        date: datetime,
        include_processed: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all messages for a specific date.
        
        Used by daily Letta consolidation job.
        """
        try:
            db = get_database()
            
            start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            
            query = db.client.table("chat_messages")\
                .select("*")\
                .gte("created_at", start.isoformat())\
                .lt("created_at", end.isoformat())\
                .order("created_at", desc=False)
            
            if not include_processed:
                query = query.eq("letta_processed", False)
                
            result = query.execute()
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to get messages for date: {e}")
            return []
    
    async def get_recent_messages(
        self,
        limit: int = 50,
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent messages, optionally filtered by session."""
        try:
            db = get_database()
            
            query = db.client.table("chat_messages")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit)
            
            if session_id:
                query = query.eq("session_id", session_id)
                
            result = query.execute()
            return list(reversed(result.data or []))  # Chronological order
            
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []
    
    async def get_recent_proactive_outreach(
        self,
        minutes: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent proactive outreach message within the time window.
        
        This is used to provide context when the user replies to a 
        proactive message from Jarvis.
        
        Args:
            minutes: How far back to look for proactive messages
            
        Returns:
            Most recent proactive outreach message with metadata, or None
        """
        try:
            db = get_database()
            
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            
            result = db.client.table("chat_messages")\
                .select("*")\
                .eq("source", "proactive_outreach")\
                .gte("created_at", cutoff.isoformat())\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get recent proactive outreach: {e}")
            return None
    
    async def mark_letta_processed(
        self,
        message_ids: List[str]
    ) -> int:
        """
        Mark messages as processed by Letta.
        
        Returns count of updated records.
        """
        try:
            db = get_database()
            
            result = db.client.table("chat_messages")\
                .update({
                    "letta_processed": True,
                    "letta_processed_at": datetime.now(timezone.utc).isoformat()
                })\
                .in_("id", message_ids)\
                .execute()
            
            count = len(result.data or [])
            logger.info(f"Marked {count} messages as Letta-processed")
            return count
            
        except Exception as e:
            logger.error(f"Failed to mark messages as processed: {e}")
            return 0
    
    async def get_unprocessed_count(self) -> int:
        """Get count of messages not yet processed by Letta."""
        try:
            db = get_database()
            
            result = db.client.table("chat_messages")\
                .select("id", count="exact")\
                .eq("letta_processed", False)\
                .execute()
            
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Failed to get unprocessed count: {e}")
            return 0
    
    async def get_unprocessed_for_letta(
        self,
        limit: int = 100,
        min_content_length: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get messages that haven't been processed by Letta yet.
        
        Args:
            limit: Maximum messages to return
            min_content_length: Skip very short messages
            
        Returns:
            List of message dicts with id, role, content, created_at
        """
        try:
            db = get_database()
            
            result = db.client.table("chat_messages")\
                .select("id,role,content,created_at,user_id")\
                .eq("letta_processed", False)\
                .order("created_at", desc=False)\
                .limit(limit)\
                .execute()
            
            # Filter by content length in Python (more flexible than SQL)
            messages = [
                m for m in (result.data or [])
                if len(m.get("content", "")) >= min_content_length
            ]
            
            logger.debug(f"Found {len(messages)} unprocessed messages for Letta")
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get unprocessed messages: {e}")
            return []
    
    async def search_messages(
        self,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search messages by content.
        
        Uses PostgreSQL full-text search if available.
        """
        try:
            db = get_database()
            
            # Simple ILIKE search (works without FTS setup)
            result = db.client.table("chat_messages")\
                .select("*")\
                .ilike("content", f"%{query}%")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return []
    
    async def get_usage_stats(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get usage statistics with cost breakdown.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict with message counts, token usage, costs
        """
        try:
            db = get_database()
            
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            # Get all assistant messages with metadata (costs are stored there)
            result = db.client.table("chat_messages")\
                .select("role,metadata,created_at")\
                .gte("created_at", cutoff)\
                .execute()
            
            messages = result.data or []
            
            # Calculate stats
            total_messages = len(messages)
            user_messages = sum(1 for m in messages if m.get("role") == "user")
            assistant_messages = sum(1 for m in messages if m.get("role") == "assistant")
            
            # Extract cost data from metadata
            total_cost = 0.0
            total_input_tokens = 0
            total_output_tokens = 0
            messages_with_cost = 0
            
            daily_costs = {}  # date -> cost
            
            for m in messages:
                if m.get("role") == "assistant":
                    meta = m.get("metadata") or {}
                    if "cost_usd" in meta:
                        cost = meta.get("cost_usd", 0)
                        total_cost += cost
                        total_input_tokens += meta.get("input_tokens", 0)
                        total_output_tokens += meta.get("output_tokens", 0)
                        messages_with_cost += 1
                        
                        # Track daily costs
                        date = m.get("created_at", "")[:10]
                        daily_costs[date] = daily_costs.get(date, 0) + cost
            
            # Calculate averages
            avg_cost_per_message = total_cost / messages_with_cost if messages_with_cost > 0 else 0
            
            # Estimate monthly at current rate
            days_with_data = len(daily_costs)
            avg_daily_cost = total_cost / days_with_data if days_with_data > 0 else 0
            estimated_monthly = avg_daily_cost * 30
            
            return {
                "period_days": days,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "messages_with_cost_tracking": messages_with_cost,
                "tokens": {
                    "total_input": total_input_tokens,
                    "total_output": total_output_tokens,
                },
                "costs": {
                    "total_usd": round(total_cost, 4),
                    "avg_per_message_usd": round(avg_cost_per_message, 6),
                    "avg_daily_usd": round(avg_daily_cost, 4),
                    "estimated_monthly_usd": round(estimated_monthly, 2),
                },
                "daily_breakdown": dict(sorted(daily_costs.items())[-7:])  # Last 7 days
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage stats: {e}")
            return {"error": str(e)}


# Singleton instance
_storage: Optional[ChatMessageStorage] = None


def get_chat_storage() -> ChatMessageStorage:
    """Get or create the chat storage singleton."""
    global _storage
    if _storage is None:
        _storage = ChatMessageStorage()
    return _storage
