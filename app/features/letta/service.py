"""
Letta Integration Service

Provides episodic memory through Letta's self-editing memory system.
Works alongside Mem0 (semantic memory) for comprehensive context.

ARCHITECTURE:
=============
Mem0 (Semantic Memory) - "What do I know?"
  - Permanent facts and preferences
  - Relationship information
  - Profile data
  - Low-cost extraction (Haiku)

Letta (Episodic Memory) - "What happened recently?"
  - Conversation history and search
  - Topic tracking over sessions
  - Decision and action item tracking
  - Self-editing memory blocks
  - Higher-cost but more contextual (Sonnet)

COST OPTIMIZATION:
==================
- Raw messages stored in Supabase (cheap, always available)
- Letta is called BATCH (not per-message) to reduce API costs
- Two modes:
  1. LIGHTWEIGHT: Just store to archival (no agent reasoning)
  2. FULL: Agent processes and updates memory blocks

Consolidation runs:
- Hourly: Lightweight archival storage
- Daily: Full memory block update (evening/morning)
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import httpx

logger = logging.getLogger("Jarvis.Intelligence.Letta")


class LettaService:
    """
    Integration with Letta for episodic memory.
    
    Uses Letta's:
    - Memory blocks (always in context)
    - Archival memory (searchable storage)
    - Conversation search (full-text + semantic)
    
    COST-EFFECTIVE DESIGN:
    - Batch processing instead of per-message
    - Lightweight archival writes (no agent reasoning)
    - Full consolidation only daily
    """
    
    _instance: Optional["LettaService"] = None
    _initialized: bool = False
    
    def __init__(self):
        """Initialize Letta service."""
        self.base_url = os.getenv("LETTA_URL", "http://localhost:8283")
        self.password = os.getenv("LETTA_PASSWORD", "")
        self.agent_id = os.getenv("LETTA_AGENT_ID", "")
        self._client: Optional[httpx.AsyncClient] = None
        
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for Letta API calls."""
        headers = {"Content-Type": "application/json"}
        if self.password:
            headers["Authorization"] = f"Bearer {self.password}"
        return headers
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._get_headers(),
                timeout=120.0  # Increased for batch operations
            )
        return self._client
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Letta server is reachable."""
        try:
            client = await self._ensure_client()
            response = await client.get("/v1/health")
            if response.status_code == 200:
                return {"status": "healthy", "letta_url": self.base_url, "agent_id": self.agent_id}
            return {"status": "unhealthy", "error": response.text}
        except Exception as e:
            logger.warning(f"Letta health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}
    
    # =========================================================================
    # LIGHTWEIGHT OPERATIONS (Low Cost)
    # =========================================================================
    
    async def insert_to_archival(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Insert text directly to Letta's archival memory.
        
        This is a LIGHTWEIGHT operation - no agent reasoning, just storage.
        Use for batch inserting conversation history.
        
        Cost: ~$0.001 per insert (embedding only, no LLM)
        """
        if not self.agent_id:
            logger.warning("No Letta agent_id configured")
            return False
            
        try:
            client = await self._ensure_client()
            
            payload = {"text": text}
            if metadata:
                # Letta archival supports metadata for filtering
                payload["metadata"] = metadata
            
            response = await client.post(
                f"/v1/agents/{self.agent_id}/archival-memory",
                json=payload
            )
            
            if response.status_code in (200, 201):
                logger.debug(f"Archival insert success: {text[:50]}...")
                return True
            else:
                logger.warning(f"Archival insert failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.warning(f"Error inserting to archival: {e}")
            return False
    
    async def batch_insert_archival(
        self,
        entries: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Batch insert multiple entries to archival memory.
        
        Each entry should have: {"text": "...", "metadata": {...}}
        
        Returns: {"success": count, "failed": count}
        """
        success = 0
        failed = 0
        
        for entry in entries:
            text = entry.get("text", "")
            metadata = entry.get("metadata")
            
            if text:
                result = await self.insert_to_archival(text, metadata)
                if result:
                    success += 1
                else:
                    failed += 1
        
        logger.info(f"Batch archival insert: {success} success, {failed} failed")
        return {"success": success, "failed": failed}
    
    async def search_archival(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search Letta's archival memory for relevant past conversations.
        
        Cost: ~$0.001 per search (embedding only)
        """
        if not self.agent_id:
            return []
            
        try:
            client = await self._ensure_client()
            response = await client.post(
                f"/v1/agents/{self.agent_id}/archival-memory/search",
                json={"query": query, "limit": limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("passages", [])  # Letta returns 'passages' not 'results'
            return []
            
        except Exception as e:
            logger.warning(f"Error searching Letta archival: {e}")
            return []
    
    # =========================================================================
    # FULL AGENT OPERATIONS (Higher Cost - Use Sparingly)
    # =========================================================================
    
    async def send_message(
        self,
        user_message: str,
        assistant_response: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message exchange to Letta for FULL agent processing.
        
        The agent will:
        - Process the message
        - Decide what to remember
        - Update memory blocks (recent_topics, decisions, action_items)
        - Potentially insert to archival
        
        ⚠️ EXPENSIVE: Uses Claude Sonnet for reasoning
        Cost: ~$0.05-0.10 per call
        
        Use for:
        - Daily consolidation summaries
        - Important decisions/events
        - NOT for every chat message
        """
        if not self.agent_id:
            logger.warning("No Letta agent_id configured, skipping message")
            return None
            
        try:
            client = await self._ensure_client()
            
            # Build messages to send
            messages = [{"role": "user", "content": user_message}]
            if assistant_response:
                messages.append({"role": "assistant", "content": assistant_response})
            
            response = await client.post(
                f"/v1/agents/{self.agent_id}/messages",
                json={"messages": messages}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Letta agent processed message")
                return data
            else:
                logger.warning(f"Letta message failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.warning(f"Error sending to Letta: {e}")
            return None
    
    async def consolidate_day(
        self,
        date: datetime,
        summary: str,
        key_topics: List[str],
        decisions: List[str],
        action_items: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Send a daily consolidation to Letta for memory block updates.
        
        This is the PRIMARY way to update Letta's memory blocks.
        Should be called once per day (evening or morning).
        
        Args:
            date: The date being consolidated
            summary: Brief summary of the day's conversations
            key_topics: Topics discussed
            decisions: Decisions made
            action_items: Action items/commitments
        
        Cost: ~$0.05-0.10 (one agent call per day)
        """
        date_str = date.strftime("%Y-%m-%d")
        
        # Build a consolidation message for the agent
        consolidation_message = f"""DAILY CONSOLIDATION for {date_str}

SUMMARY:
{summary}

KEY TOPICS DISCUSSED:
{chr(10).join(f'- {t}' for t in key_topics) if key_topics else '- No specific topics'}

DECISIONS MADE:
{chr(10).join(f'- {d}' for d in decisions) if decisions else '- No decisions recorded'}

ACTION ITEMS/COMMITMENTS:
{chr(10).join(f'- {a}' for a in action_items) if action_items else '- No action items'}

Please update your memory blocks with this information:
1. Update 'recent_topics' with the topics discussed
2. Update 'decisions' with any decisions made
3. Update 'action_items' with commitments
4. Archive detailed information if relevant"""

        return await self.send_message(consolidation_message)
    
    # =========================================================================
    # MEMORY BLOCK OPERATIONS
    # =========================================================================
    
    async def get_memory_blocks(self) -> Dict[str, str]:
        """
        Get current memory block values.
        
        Returns dict like {'human': '...', 'recent_topics': '...', 'decisions': '...'}
        
        Cost: FREE (just API call, no LLM)
        """
        if not self.agent_id:
            return {}
            
        try:
            client = await self._ensure_client()
            response = await client.get(f"/v1/agents/{self.agent_id}")
            
            if response.status_code == 200:
                data = response.json()
                blocks = {}
                for block in data.get("memory", {}).get("blocks", []):
                    blocks[block["label"]] = block["value"]
                return blocks
            return {}
            
        except Exception as e:
            logger.warning(f"Error getting Letta memory blocks: {e}")
            return {}
    
    async def update_memory_block(
        self,
        label: str,
        value: str
    ) -> bool:
        """
        Directly update a memory block value.
        
        Use sparingly - prefer consolidate_day() for structured updates.
        
        Cost: FREE (just API call, no LLM)
        """
        if not self.agent_id:
            return False
            
        try:
            client = await self._ensure_client()
            
            # First get the block ID
            response = await client.get(f"/v1/agents/{self.agent_id}")
            if response.status_code != 200:
                return False
            
            data = response.json()
            block_id = None
            for block in data.get("memory", {}).get("blocks", []):
                if block["label"] == label:
                    block_id = block["id"]
                    break
            
            if not block_id:
                logger.warning(f"Memory block '{label}' not found")
                return False
            
            # Update the block
            response = await client.patch(
                f"/v1/blocks/{block_id}",
                json={"value": value}
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.warning(f"Error updating memory block: {e}")
            return False
    
    # =========================================================================
    # CONTEXT RETRIEVAL (For Chat)
    # =========================================================================
    
    async def get_context_for_chat(self, query: str = "") -> str:
        """
        Get formatted context from Letta for inclusion in chat system prompt.
        
        Returns a formatted string with:
        - Current memory block values
        - Relevant archival memory results (if query provided)
        
        Cost: ~$0.001 if query provided (embedding), FREE if no query
        """
        try:
            # Get memory blocks (FREE)
            blocks = await self.get_memory_blocks()
            
            # Search archival for relevant context (only if query provided)
            archival = []
            if query and len(query) > 10:
                archival = await self.search_archival(query, limit=3)
            
            # Format output
            lines = []
            
            if blocks.get("recent_topics") and "No topics" not in blocks["recent_topics"]:
                lines.append(f"📋 **Recent Topics:**\n{blocks['recent_topics']}")
            
            if blocks.get("decisions") and "No decisions" not in blocks["decisions"]:
                lines.append(f"✅ **Recent Decisions:**\n{blocks['decisions']}")
            
            if blocks.get("action_items") and "No action" not in blocks["action_items"]:
                lines.append(f"📌 **Action Items:**\n{blocks['action_items']}")
            
            if archival:
                lines.append("🔍 **Relevant Past Context:**")
                for item in archival[:3]:
                    text = item.get("text", "")[:200]
                    if text:
                        lines.append(f"  • {text}...")
            
            if not lines:
                return ""
                
            return "\n\n**EPISODIC CONTEXT (from Letta):**\n" + "\n\n".join(lines)
            
        except Exception as e:
            logger.warning(f"Error getting Letta context: {e}")
            return ""
    
    # =========================================================================
    # BATCH CONSOLIDATION (Called by Scheduler)
    # =========================================================================
    
    async def process_unprocessed_messages(
        self,
        mode: str = "lightweight"
    ) -> Dict[str, Any]:
        """
        Process messages from chat_messages table that haven't been sent to Letta.
        
        Modes:
        - "lightweight": Just insert to archival (cheap, ~$0.001/msg)
        - "full": Send through agent for memory updates (expensive, ~$0.05/msg)
        
        Called by scheduled jobs (hourly for lightweight, daily for full).
        
        Returns: {"processed": count, "skipped": count, "errors": count}
        """
        from app.features.chat.storage import get_chat_storage
        
        storage = get_chat_storage()
        
        try:
            # Get unprocessed messages
            messages = await storage.get_unprocessed_for_letta(limit=100)
            
            if not messages:
                logger.info("No unprocessed messages for Letta")
                return {"processed": 0, "skipped": 0, "errors": 0}
            
            logger.info(f"Processing {len(messages)} messages for Letta (mode: {mode})")
            
            processed = 0
            skipped = 0
            errors = 0
            processed_ids = []
            
            if mode == "lightweight":
                # Batch insert to archival (cheap)
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    created_at = msg.get("created_at", "")
                    msg_id = msg.get("id")
                    
                    # Skip very short messages
                    if len(content) < 20:
                        skipped += 1
                        processed_ids.append(msg_id)  # Mark as processed anyway
                        continue
                    
                    # Format for archival
                    archival_text = f"[{created_at[:10]}] {role.upper()}: {content}"
                    
                    success = await self.insert_to_archival(
                        text=archival_text,
                        metadata={
                            "role": role,
                            "date": created_at[:10],
                            "source": "chat_messages"
                        }
                    )
                    
                    if success:
                        processed += 1
                        processed_ids.append(msg_id)
                    else:
                        errors += 1
            
            elif mode == "full":
                # Group messages into conversation chunks
                conversation_chunks = self._group_messages_into_chunks(messages)
                
                for chunk in conversation_chunks:
                    # Build conversation summary
                    summary = "\n".join([
                        f"{m['role'].upper()}: {m['content'][:200]}"
                        for m in chunk
                    ])
                    
                    # Send to agent for processing
                    result = await self.send_message(
                        f"Process this conversation segment:\n\n{summary}"
                    )
                    
                    if result:
                        processed += len(chunk)
                        processed_ids.extend([m.get("id") for m in chunk])
                    else:
                        errors += len(chunk)
            
            # Mark messages as processed
            if processed_ids:
                await storage.mark_letta_processed(processed_ids)
            
            result = {
                "processed": processed,
                "skipped": skipped,
                "errors": errors,
                "mode": mode
            }
            logger.info(f"Letta processing complete: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing messages for Letta: {e}")
            return {"processed": 0, "skipped": 0, "errors": 1, "error_message": str(e)}
    
    def _group_messages_into_chunks(
        self,
        messages: List[Dict],
        max_chunk_size: int = 10
    ) -> List[List[Dict]]:
        """Group messages into conversation chunks for efficient processing."""
        chunks = []
        current_chunk = []
        
        for msg in messages:
            current_chunk.append(msg)
            if len(current_chunk) >= max_chunk_size:
                chunks.append(current_chunk)
                current_chunk = []
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    # =========================================================================
    # AGENT MANAGEMENT
    # =========================================================================
    
    async def create_agent(
        self,
        name: str = "jarvis-memory",
        model: str = "claude-sonnet-4-5-20250929"
    ) -> Optional[str]:
        """
        Create a Letta agent for memory management.
        
        Returns agent_id if successful.
        """
        try:
            client = await self._ensure_client()
            
            # Define memory blocks
            memory_blocks = [
                {
                    "label": "human",
                    "value": "Aaron Pütting. 26yo German engineer. Currently traveling (Ho Chi Minh City as of Jan 2026). Building Jarvis AI system. Former first employee at Algenie (biotech). Interested in FoodTech, Climate Tech, startups, longevity.",
                    "limit": 5000
                },
                {
                    "label": "recent_topics",
                    "value": "No topics recorded yet. This block will be updated with topics discussed in recent conversations.",
                    "limit": 4000
                },
                {
                    "label": "decisions",
                    "value": "No decisions recorded yet. This block will track decisions Aaron makes.",
                    "limit": 3000
                },
                {
                    "label": "action_items",
                    "value": "No action items recorded yet. This block will track commitments and todos.",
                    "limit": 2000
                }
            ]
            
            # System prompt for the memory agent
            system_prompt = """You are a memory management agent for Jarvis, Aaron's personal AI assistant.

Your role is to maintain episodic memory - tracking WHAT HAPPENED in conversations, not permanent facts.

WHEN PROCESSING MESSAGES:
1. Update 'recent_topics' with conversation topics (keep recent, prune old)
2. Update 'decisions' when Aaron decides something specific
3. Update 'action_items' when Aaron commits to doing something
4. Archive detailed conversation logs to archival memory

MEMORY BLOCK GUIDELINES:
- recent_topics: Last 5-7 topics with brief context, newest first
- decisions: Active decisions (remove once implemented/changed)
- action_items: Pending items only (remove when done)

ARCHIVAL MEMORY:
- Store detailed conversation summaries
- Include dates for temporal search
- Good for: "What did we discuss about X last week?"

Be concise. Prioritize recency. Remove stale information proactively."""

            response = await client.post(
                "/v1/agents",
                json={
                    "name": name,
                    "model": model,
                    "system": system_prompt,
                    "memory_blocks": memory_blocks,
                    "tools": [
                        "memory_replace",
                        "memory_insert", 
                        "memory_rethink",
                        "archival_memory_insert",
                        "archival_memory_search",
                        "conversation_search"
                    ]
                }
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                agent_id = data.get("id")
                logger.info(f"Created Letta agent: {agent_id}")
                return agent_id
            else:
                logger.error(f"Failed to create Letta agent: {response.text}")
                return None
                
        except Exception as e:
            logger.exception(f"Error creating Letta agent: {e}")
            return None
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_letta_service: Optional[LettaService] = None


def get_letta_service() -> LettaService:
    """Get or create the Letta service singleton."""
    global _letta_service
    if _letta_service is None:
        _letta_service = LettaService()
    return _letta_service
