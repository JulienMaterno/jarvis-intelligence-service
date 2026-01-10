"""
Memory Consolidation Service

Comprehensive memory extraction from ALL data sources.
Runs periodically to ensure no knowledge is lost.

DATA SOURCES:
=============
1. chat_messages     - Telegram conversations (Letta + Mem0)
2. beeper_messages   - WhatsApp/LinkedIn/Slack (Mem0)
3. transcripts       - Voice memos (Mem0)
4. meetings          - Meeting summaries (Mem0)
5. journals          - Daily journals (Mem0)
6. reflections       - Topic reflections (Mem0)
7. calendar_events   - Calendar context (Mem0)
8. contacts          - CRM data (Mem0)

ARCHITECTURE:
=============
- Mem0: Extracts semantic memories (facts, relationships, preferences)
- Letta: Stores episodic memory (conversation history)
- Both systems are fed from multiple sources

SCHEDULING:
===========
- Lightweight (hourly): Chat messages → Letta archival
- Comprehensive (2x daily): All sources → Mem0 extraction
- Daily summary: Letta memory block updates
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import asyncio

logger = logging.getLogger("Jarvis.Memory.Consolidation")


class MemoryConsolidationService:
    """
    Unified memory extraction from all data sources.
    
    This service ensures:
    1. No data slips through the cracks
    2. Both Mem0 and Letta are kept in sync
    3. Cost-effective batch processing
    """
    
    def __init__(self):
        self._mem0 = None
        self._letta = None
        self._db = None
    
    def _ensure_services(self):
        """Lazy initialization of services."""
        if self._mem0 is None:
            from app.features.memory import get_memory_service
            self._mem0 = get_memory_service()
        if self._letta is None:
            from app.features.letta import get_letta_service
            self._letta = get_letta_service()
        if self._db is None:
            from app.core.database import supabase
            self._db = supabase
    
    # =========================================================================
    # MAIN CONSOLIDATION ENTRY POINTS
    # =========================================================================
    
    async def consolidate_all(
        self,
        hours_back: int = 24,
        include_letta: bool = True,
        include_mem0: bool = True
    ) -> Dict[str, Any]:
        """
        Run comprehensive memory consolidation across all sources.
        
        Call this 2x daily (morning + evening) for complete coverage.
        
        Args:
            hours_back: How far back to look for new data
            include_letta: Whether to process chat_messages → Letta
            include_mem0: Whether to extract Mem0 memories from all sources
        
        Returns:
            Summary of what was processed
        """
        self._ensure_services()
        
        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "hours_back": hours_back,
            "sources": {}
        }
        
        # 1. Letta: Process chat messages to archival
        if include_letta:
            try:
                letta_result = await self._letta.process_unprocessed_messages(mode="lightweight")
                results["sources"]["letta_chat"] = letta_result
            except Exception as e:
                logger.error(f"Letta consolidation failed: {e}")
                results["sources"]["letta_chat"] = {"error": str(e)}
        
        # 2. Mem0: Extract from all sources
        if include_mem0:
            mem0_results = {}
            
            # Chat messages (that might have been missed by real-time extraction)
            try:
                chat_count = await self._extract_from_chat_messages(hours_back)
                mem0_results["chat_messages"] = {"extracted": chat_count}
            except Exception as e:
                mem0_results["chat_messages"] = {"error": str(e)}
            
            # Beeper messages
            try:
                beeper_count = await self._extract_from_beeper(hours_back)
                mem0_results["beeper_messages"] = {"extracted": beeper_count}
            except Exception as e:
                mem0_results["beeper_messages"] = {"error": str(e)}
            
            # Transcripts (voice memos)
            try:
                transcript_count = await self._extract_from_transcripts(hours_back)
                mem0_results["transcripts"] = {"extracted": transcript_count}
            except Exception as e:
                mem0_results["transcripts"] = {"error": str(e)}
            
            # Meetings
            try:
                meeting_count = await self._extract_from_meetings(hours_back)
                mem0_results["meetings"] = {"extracted": meeting_count}
            except Exception as e:
                mem0_results["meetings"] = {"error": str(e)}
            
            # Journals
            try:
                journal_count = await self._extract_from_journals(hours_back)
                mem0_results["journals"] = {"extracted": journal_count}
            except Exception as e:
                mem0_results["journals"] = {"error": str(e)}
            
            results["sources"]["mem0"] = mem0_results
        
        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        # Log summary
        total = sum(
            r.get("extracted", 0) 
            for r in results.get("sources", {}).get("mem0", {}).values()
            if isinstance(r, dict)
        )
        logger.info(f"Memory consolidation complete: {total} Mem0 memories extracted")
        
        return results
    
    async def consolidate_lightweight(self) -> Dict[str, Any]:
        """
        Lightweight hourly consolidation.
        
        Only processes chat_messages → Letta archival.
        Fast and cheap (~$0.001/message).
        """
        self._ensure_services()
        
        try:
            result = await self._letta.process_unprocessed_messages(mode="lightweight")
            return {
                "status": "success",
                "mode": "lightweight",
                **result
            }
        except Exception as e:
            logger.error(f"Lightweight consolidation failed: {e}")
            return {"status": "error", "error": str(e)}
    
    # =========================================================================
    # SOURCE-SPECIFIC EXTRACTION
    # =========================================================================
    
    async def _extract_from_chat_messages(self, hours_back: int = 24) -> int:
        """
        Extract Mem0 memories from chat_messages that weren't processed in real-time.
        
        This catches messages where:
        - Real-time extraction failed
        - Message didn't match keyword heuristics but contains valuable info
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Get user messages (assistant messages don't contain user facts)
        result = self._db.table("chat_messages").select(
            "id, content, created_at"
        ).eq("role", "user").gte(
            "created_at", since.isoformat()
        ).order("created_at", desc=True).limit(100).execute()
        
        messages = result.data or []
        if not messages:
            return 0
        
        # Batch into conversations (group by 10-minute windows)
        batches = self._batch_messages_by_time(messages, window_minutes=10)
        
        count = 0
        for batch in batches:
            text = "\n".join([f"User: {m['content']}" for m in batch])
            if len(text) > 50:  # Skip very short batches
                extracted = await self._mem0.extract_from_text(
                    text=text,
                    source="chat_batch",
                )
                count += extracted
        
        return count
    
    async def _extract_from_beeper(self, hours_back: int = 24) -> int:
        """
        Extract memories from Beeper messages (WhatsApp, LinkedIn, Slack).
        
        BATCHED: All conversations from all chats are combined into a single
        Claude call to minimize API costs. The model extracts memories from
        the combined context.
        
        This is RICH data - people share lots of info in casual messages.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Get recent messages with chat context
        result = self._db.table("beeper_messages").select(
            "id, content, is_outgoing, timestamp, beeper_chat_id"
        ).gte(
            "timestamp", since.isoformat()
        ).order("timestamp", desc=True).limit(500).execute()
        
        messages = result.data or []
        if not messages:
            return 0
        
        # Group by chat for context
        chats = {}
        for msg in messages:
            chat_id = msg.get("beeper_chat_id", "unknown")
            if chat_id not in chats:
                chats[chat_id] = []
            chats[chat_id].append(msg)
        
        # Also get chat names for context
        chat_names = {}
        try:
            chat_result = self._db.table("beeper_chats").select(
                "beeper_chat_id, chat_name, platform"
            ).in_("beeper_chat_id", list(chats.keys())).execute()
            for chat in (chat_result.data or []):
                chat_names[chat["beeper_chat_id"]] = {
                    "name": chat.get("chat_name", "Unknown"),
                    "platform": chat.get("platform", "unknown")
                }
        except Exception as e:
            logger.warning(f"Could not fetch chat names: {e}")
        
        # BATCHED: Build ALL conversations into one text block
        all_conversations = []
        for chat_id, chat_msgs in chats.items():
            chat_info = chat_names.get(chat_id, {"name": "Unknown", "platform": "unknown"})
            contact_name = chat_info["name"]
            platform = chat_info["platform"]
            
            conversation_lines = []
            for m in sorted(chat_msgs, key=lambda x: x.get("timestamp", "")):
                # IMPORTANT: Clearly label who said what
                # Aaron's messages are outgoing, contact's messages are incoming
                if m.get("is_outgoing"):
                    speaker = "Aaron"  # This is the USER speaking
                else:
                    speaker = f"{contact_name} (not Aaron)"  # Clearly mark as OTHER person
                content = m.get("content", "")
                if content and len(content.strip()) > 0:
                    conversation_lines.append(f"{speaker}: {content}")
            
            if len(conversation_lines) >= 2:  # Skip single-message "conversations"
                all_conversations.append(
                    f"=== {platform.upper()} conversation with {contact_name} ===\n"
                    f"⚠️ Remember: Only Aaron's statements are facts about Aaron!\n" + 
                    "\n".join(conversation_lines)
                )
        
        if not all_conversations:
            return 0
        
        # SINGLE Claude call for all conversations
        combined_text = "\n\n".join(all_conversations)
        
        # Truncate if extremely long (shouldn't happen with 500 msg limit)
        if len(combined_text) > 50000:
            combined_text = combined_text[:50000] + "\n\n[... truncated ...]"
        
        logger.info(f"Batched {len(all_conversations)} conversations ({len(messages)} messages) for memory extraction")
        
        extracted = await self._mem0.extract_from_text(
            text=combined_text,
            source="beeper_batch",
        )
        
        return extracted
    
    async def _extract_from_transcripts(self, hours_back: int = 24) -> int:
        """
        Extract memories from voice memo transcripts.
        
        Transcripts are already analyzed during processing, but this catches
        any that were missed or re-extracts with improved prompts.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        result = self._db.table("transcripts").select(
            "id, full_text, source_file, created_at"
        ).gte("created_at", since.isoformat()).limit(20).execute()
        
        transcripts = result.data or []
        if not transcripts:
            return 0
        
        count = 0
        for t in transcripts:
            text = t.get("full_text", "")
            source = t.get("source_file", "transcript")
            
            if text and len(text) > 100:
                # Use the more comprehensive transcript extraction
                extracted = await self._mem0.seed_from_raw_transcript(
                    transcript_text=text,
                    source_file=source
                )
                count += extracted
        
        return count
    
    async def _extract_from_meetings(self, hours_back: int = 24) -> int:
        """
        Extract memories from meeting records.
        
        Meetings have structured data (summary, topics, action items)
        that can yield high-quality memories.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Use only columns that definitely exist in the database
        # Avoid action_items as it may not exist in all deployments
        try:
            result = self._db.table("meetings").select(
                "id, title, summary, topics_discussed, people_mentioned, contact_name, date"
            ).gte("created_at", since.isoformat()).limit(20).execute()
        except Exception as e:
            logger.warning(f"Could not query meetings: {e}")
            return 0
        
        meetings = result.data or []
        if not meetings:
            return 0
        
        count = 0
        for m in meetings:
            # Build a text summary of the meeting
            parts = []
            if m.get("title"):
                parts.append(f"Meeting: {m['title']}")
            if m.get("contact_name"):
                parts.append(f"With: {m['contact_name']}")
            if m.get("date"):
                parts.append(f"Date: {m['date']}")
            if m.get("summary"):
                parts.append(f"Summary: {m['summary']}")
            if m.get("topics_discussed"):
                topics = m["topics_discussed"]
                if isinstance(topics, list):
                    parts.append(f"Topics: {', '.join(str(t) for t in topics)}")
            if m.get("people_mentioned"):
                parts.append(f"People mentioned: {', '.join(m['people_mentioned'])}")
            
            text = "\n".join(parts)
            
            if len(text) > 50:
                extracted = await self._mem0.extract_from_text(
                    text=text,
                    source="meeting",
                    source_id=m.get("id")
                )
                count += extracted
        
        return count
    
    async def _extract_from_journals(self, hours_back: int = 24) -> int:
        """
        Extract memories from journal entries.
        
        Journals contain introspective content about:
        - Current state (mood, energy)
        - Achievements (wins)
        - Struggles (challenges)
        - Plans (tomorrow_focus)
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Use only columns that definitely exist in the database
        # Note: wins, challenges, energy may not exist in all deployments
        try:
            result = self._db.table("journals").select(
                "id, date, title, content, mood, tomorrow_focus, gratitude"
            ).gte("created_at", since.isoformat()).limit(10).execute()
        except Exception as e:
            logger.warning(f"Could not query journals: {e}")
            return 0
        
        journals = result.data or []
        if not journals:
            return 0
        
        count = 0
        for j in journals:
            # Build comprehensive text from journal
            parts = []
            if j.get("date"):
                parts.append(f"Journal entry for {j['date']}")
            if j.get("mood"):
                parts.append(f"Mood: {j['mood']}")
            if j.get("content"):
                parts.append(f"Content: {j['content'][:500]}")  # Truncate long content
            if j.get("tomorrow_focus"):
                focus = j["tomorrow_focus"] if isinstance(j["tomorrow_focus"], list) else [j["tomorrow_focus"]]
                parts.append(f"Tomorrow's focus: {', '.join(str(f) for f in focus)}")
            if j.get("gratitude"):
                gratitude = j["gratitude"] if isinstance(j["gratitude"], list) else [j["gratitude"]]
                parts.append(f"Gratitude: {', '.join(str(g) for g in gratitude)}")
            
            text = "\n".join(parts)
            
            if len(text) > 50:
                extracted = await self._mem0.extract_from_text(
                    text=text,
                    source="journal",
                    source_id=j.get("id")
                )
                count += extracted
        
        return count
    
    # =========================================================================
    # UTILITIES
    # =========================================================================
    
    def _batch_messages_by_time(
        self,
        messages: List[Dict],
        window_minutes: int = 10
    ) -> List[List[Dict]]:
        """
        Group messages into batches by time proximity.
        
        Messages within `window_minutes` of each other are grouped together.
        """
        if not messages:
            return []
        
        # Sort by created_at
        sorted_msgs = sorted(messages, key=lambda m: m.get("created_at", ""))
        
        batches = []
        current_batch = [sorted_msgs[0]]
        
        for msg in sorted_msgs[1:]:
            try:
                prev_time = datetime.fromisoformat(current_batch[-1].get("created_at", "").replace("Z", "+00:00"))
                curr_time = datetime.fromisoformat(msg.get("created_at", "").replace("Z", "+00:00"))
                
                if (curr_time - prev_time).total_seconds() <= window_minutes * 60:
                    current_batch.append(msg)
                else:
                    batches.append(current_batch)
                    current_batch = [msg]
            except Exception:
                current_batch.append(msg)
        
        if current_batch:
            batches.append(current_batch)
        
        return batches


# Singleton
_consolidation_service: Optional[MemoryConsolidationService] = None

def get_consolidation_service() -> MemoryConsolidationService:
    """Get singleton instance of consolidation service."""
    global _consolidation_service
    if _consolidation_service is None:
        _consolidation_service = MemoryConsolidationService()
    return _consolidation_service
