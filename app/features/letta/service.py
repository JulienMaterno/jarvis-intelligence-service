"""
Letta Integration Service

Provides episodic memory through Letta's self-editing memory system.
Works alongside Mem0 (semantic memory) for comprehensive context.

Letta handles:
- Conversation history and search
- Topic extraction and accumulation
- Decision tracking
- Self-editing memory blocks

Mem0 handles:
- Permanent facts and preferences
- Relationship information
- Profile data
"""

import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("Jarvis.Intelligence.Letta")


class LettaService:
    """
    Integration with Letta for episodic memory.
    
    Uses Letta's:
    - Memory blocks (always in context)
    - Archival memory (searchable storage)
    - Conversation search (full-text + semantic)
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
                timeout=60.0
            )
        return self._client
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if Letta server is reachable."""
        try:
            client = await self._ensure_client()
            response = await client.get("/v1/health")
            if response.status_code == 200:
                return {"status": "healthy", "letta_url": self.base_url}
            return {"status": "unhealthy", "error": response.text}
        except Exception as e:
            logger.warning(f"Letta health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}
    
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
                    "value": "Aaron Pütting. 26yo German engineer. Currently in Ho Chi Minh City. Building Jarvis AI system. Interested in FoodTech, Climate Tech, startups.",
                    "limit": 5000
                },
                {
                    "label": "recent_topics",
                    "value": "No topics recorded yet.",
                    "limit": 4000
                },
                {
                    "label": "decisions",
                    "value": "No decisions recorded yet.",
                    "limit": 3000
                },
                {
                    "label": "action_items",
                    "value": "No action items recorded yet.",
                    "limit": 2000
                }
            ]
            
            # System prompt for the memory agent
            system_prompt = """You are a memory management agent for Jarvis, Aaron's personal AI assistant.

Your role is to:
1. Maintain accurate context about recent conversations
2. Track topics discussed and accumulate knowledge about them
3. Record decisions Aaron makes
4. Track action items and commitments

When processing messages:
- Update 'recent_topics' when a new topic is discussed
- Update 'decisions' when Aaron makes a decision
- Update 'action_items' when Aaron commits to doing something
- Use archival memory for detailed conversation logs

Keep memory blocks concise but comprehensive. Prioritize recent and important information."""

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
    
    async def send_message(
        self,
        user_message: str,
        assistant_response: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message exchange to Letta for memory processing.
        
        Letta will autonomously decide what to remember in its blocks.
        """
        if not self.agent_id:
            logger.warning("No Letta agent_id configured, skipping message")
            return None
            
        try:
            client = await self._ensure_client()
            
            # Build messages to send (Letta API uses "content" not "text")
            messages = [{"role": "user", "content": user_message}]
            if assistant_response:
                messages.append({"role": "assistant", "content": assistant_response})
            
            response = await client.post(
                f"/v1/agents/{self.agent_id}/messages",
                json={"messages": messages}
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Letta processed message, response: {data.get('messages', [])[:1]}")
                return data
            else:
                logger.warning(f"Letta message failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.warning(f"Error sending to Letta: {e}")
            return None
    
    async def get_memory_blocks(self) -> Dict[str, str]:
        """
        Get current memory block values.
        
        Returns dict like {'recent_topics': '...', 'decisions': '...'}
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
    
    async def search_archival(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search Letta's archival memory for relevant past conversations.
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
                return data.get("results", [])
            return []
            
        except Exception as e:
            logger.warning(f"Error searching Letta archival: {e}")
            return []
    
    async def search_conversations(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search past conversations using Letta's conversation search.
        """
        if not self.agent_id:
            return []
            
        try:
            client = await self._ensure_client()
            response = await client.post(
                f"/v1/agents/{self.agent_id}/messages/search",
                json={"query": query, "limit": limit}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("messages", [])
            return []
            
        except Exception as e:
            logger.warning(f"Error searching Letta conversations: {e}")
            return []
    
    async def get_context_for_chat(self, query: str) -> str:
        """
        Get formatted context from Letta for inclusion in chat system prompt.
        
        Returns a formatted string with:
        - Current memory block values
        - Relevant archival memory results
        """
        try:
            # Get memory blocks
            blocks = await self.get_memory_blocks()
            
            # Search archival for relevant context
            archival = await self.search_archival(query, limit=3)
            
            # Format output
            lines = ["**CONVERSATION CONTEXT (from Letta)**"]
            
            if blocks.get("recent_topics") and blocks["recent_topics"] != "No topics recorded yet.":
                lines.append(f"\n📋 Recent Topics:\n{blocks['recent_topics']}")
            
            if blocks.get("decisions") and blocks["decisions"] != "No decisions recorded yet.":
                lines.append(f"\n✅ Recent Decisions:\n{blocks['decisions']}")
            
            if blocks.get("action_items") and blocks["action_items"] != "No action items recorded yet.":
                lines.append(f"\n📌 Action Items:\n{blocks['action_items']}")
            
            if archival:
                lines.append("\n🔍 Relevant Past Conversations:")
                for item in archival[:3]:
                    text = item.get("text", "")[:200]
                    lines.append(f"  • {text}...")
            
            if len(lines) == 1:
                return ""  # No useful context
                
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"Error getting Letta context: {e}")
            return ""
    
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
