"""
Memory Service - Supabase-Native Implementation

Simple, persistent memory storage using Supabase:
- Text-based search (no external embeddings needed)
- Persists across restarts
- Single database for everything
- Optional: pgvector for semantic search later

This replaces the Mem0/Qdrant approach with native Supabase.
"""

import logging
import os
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("Jarvis.Memory")


class MemoryType(Enum):
    """Types of memories stored."""
    FACT = "fact"  # User facts: "User is vegetarian", "Works at Algenie"
    INTERACTION = "interaction"  # Meeting/conversation summaries
    INSIGHT = "insight"  # Patterns and observations
    PREFERENCE = "preference"  # User preferences
    RELATIONSHIP = "relationship"  # Info about contacts/relationships


class MemoryService:
    """
    Supabase-native memory service.
    
    Simple and persistent - no external dependencies.
    Uses text search for retrieval (can add embeddings later).
    """
    
    _instance: Optional["MemoryService"] = None
    
    def __init__(self):
        """Initialize memory service."""
        self.user_id = os.getenv("JARVIS_USER_ID", "aaron")
        self._db = None
        self._llm = None
    
    def _ensure_db(self):
        """Lazy load database client."""
        if self._db is None:
            from app.core.database import supabase
            self._db = supabase
        return self._db
    
    def _ensure_llm(self):
        """Lazy load LLM for memory extraction."""
        if self._llm is None:
            from anthropic import Anthropic
            self._llm = Anthropic()
        return self._llm
    
    async def add(
        self,
        memory: str,
        memory_type: str = "fact",
        source: str = "manual",
        source_id: Optional[str] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[str]:
        """
        Add a memory.
        
        Args:
            memory: The memory text
            memory_type: fact, interaction, insight, preference, relationship
            source: Where it came from (chat, transcript, beeper, manual)
            source_id: ID of source record
            category: Optional grouping
            metadata: Extra data (stored in memory text as context)
            
        Returns:
            Memory ID if successful
        """
        db = self._ensure_db()
        
        # Check for duplicate/similar memory
        existing = await self.search(memory, limit=3)
        for mem in existing:
            # Simple similarity check - if very similar, skip
            if self._is_similar(memory, mem.get("memory", "")):
                logger.debug(f"Skipping duplicate memory: {memory[:50]}...")
                return mem.get("id")
        
        mem_id = str(uuid4())
        record = {
            "id": mem_id,
            "memory": memory,
            "memory_type": memory_type,
            "user_id": self.user_id,
            "source": source,
            "source_id": source_id,
            "category": category,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        try:
            db.table("memories").insert(record).execute()
            logger.info(f"Added memory [{memory_type}]: {memory[:50]}...")
            return mem_id
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return None
    
    def _is_similar(self, text1: str, text2: str, threshold: float = 0.85) -> bool:
        """Check if two texts are very similar (simple word overlap)."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return False
        overlap = len(words1 & words2) / max(len(words1), len(words2))
        return overlap > threshold
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        memory_type: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search memories by text.
        
        Uses PostgreSQL full-text search for relevance ranking.
        """
        db = self._ensure_db()
        
        try:
            # Build query with filters
            q = db.table("memories").select("*").is_("deleted_at", "null")
            
            if memory_type:
                q = q.eq("memory_type", memory_type)
            if source:
                q = q.eq("source", source)
            
            # Text search using ILIKE (simple but effective)
            # For better results, use the search_memories_text function
            words = query.lower().split()
            for word in words[:3]:  # Limit to first 3 words for performance
                q = q.ilike("memory", f"%{word}%")
            
            result = q.order("created_at", desc=True).limit(limit).execute()
            return result.data or []
            
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return []
    
    async def get_all(
        self,
        limit: int = 100,
        memory_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all memories."""
        db = self._ensure_db()
        
        try:
            q = db.table("memories").select("*").is_("deleted_at", "null")
            
            if memory_type:
                q = q.eq("memory_type", memory_type)
            
            result = q.order("created_at", desc=True).limit(limit).execute()
            return result.data or []
            
        except Exception as e:
            logger.error(f"Failed to get memories: {e}")
            return []
    
    async def delete(self, memory_id: str) -> bool:
        """Soft delete a memory."""
        db = self._ensure_db()
        
        try:
            db.table("memories").update({
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", memory_id).execute()
            logger.info(f"Deleted memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    async def update(self, memory_id: str, new_memory: str) -> bool:
        """Update a memory's text."""
        db = self._ensure_db()
        
        try:
            db.table("memories").update({
                "memory": new_memory,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", memory_id).execute()
            logger.info(f"Updated memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update memory: {e}")
            return False
    
    async def extract_from_text(
        self,
        text: str,
        source: str = "transcript",
        source_id: Optional[str] = None,
    ) -> int:
        """
        Extract and store memories from a block of text.
        
        Uses Claude to identify facts, preferences, and insights.
        Returns number of memories created.
        """
        llm = self._ensure_llm()
        
        prompt = f"""Analyze this text and extract key facts, preferences, and insights about Aaron.

TEXT:
{text}

Extract information in these categories:
1. FACTS - Personal info, background, work, relationships
2. PREFERENCES - Likes, dislikes, habits
3. INSIGHTS - Patterns, observations, goals

Output as JSON array:
[
  {{"type": "fact", "memory": "Aaron works at Algenie as CTO"}},
  {{"type": "preference", "memory": "Aaron prefers morning meetings"}},
  ...
]

Rules:
- Be specific and actionable
- Write in third person ("Aaron...")
- Skip generic/obvious information
- Max 15 memories
- Only include information EXPLICITLY stated or strongly implied

Output ONLY the JSON array, nothing else."""

        try:
            response = llm.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            import json
            result_text = response.content[0].text.strip()
            
            # Clean up response
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            memories = json.loads(result_text)
            count = 0
            
            for mem in memories:
                mem_type = mem.get("type", "fact")
                mem_text = mem.get("memory", "")
                
                if mem_text:
                    await self.add(
                        memory=mem_text,
                        memory_type=mem_type,
                        source=source,
                        source_id=source_id,
                    )
                    count += 1
            
            logger.info(f"Extracted {count} memories from {source}")
            return count
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return 0
    
    async def get_context(
        self,
        query: str,
        max_memories: int = 10,
    ) -> str:
        """
        Get memory context for a query.
        
        Returns formatted string of relevant memories for injection into prompts.
        """
        memories = await self.search(query, limit=max_memories)
        
        if not memories:
            return ""
        
        context_parts = ["## Relevant Memories"]
        for mem in memories:
            mem_type = mem.get("memory_type", "fact")
            mem_text = mem.get("memory", "")
            context_parts.append(f"- [{mem_type}] {mem_text}")
        
        return "\n".join(context_parts)
    
    async def count(self) -> int:
        """Get total memory count."""
        db = self._ensure_db()
        try:
            result = db.table("memories").select("id", count="exact").is_("deleted_at", "null").execute()
            return result.count or 0
        except:
            return 0
    
    # =========================================================================
    # CONVENIENCE METHODS (for seeding and specific use cases)
    # =========================================================================
    
    async def remember_fact(self, fact: str, source: str = "manual") -> Optional[str]:
        """Add a fact about the user."""
        return await self.add(memory=fact, memory_type="fact", source=source)
    
    async def remember_preference(self, pref: str, source: str = "manual") -> Optional[str]:
        """Add a user preference."""
        return await self.add(memory=pref, memory_type="preference", source=source)
    
    async def remember_relationship(self, info: str, contact_name: str = None) -> Optional[str]:
        """Add relationship/contact information."""
        return await self.add(
            memory=info,
            memory_type="relationship",
            source="contacts",
            category=contact_name
        )
    
    async def remember_interaction(self, summary: str, source_id: str = None) -> Optional[str]:
        """Add a meeting/interaction summary."""
        return await self.add(
            memory=summary,
            memory_type="interaction",
            source="meeting",
            source_id=source_id
        )
    
    async def seed_from_raw_transcript(
        self,
        transcript_text: str,
        source_id: str = None
    ) -> int:
        """Extract and store memories from a transcript."""
        return await self.extract_from_text(
            text=transcript_text,
            source="transcript",
            source_id=source_id
        )


@lru_cache(maxsize=1)
def get_memory_service() -> MemoryService:
    """Get singleton memory service instance."""
    if MemoryService._instance is None:
        MemoryService._instance = MemoryService()
    return MemoryService._instance
