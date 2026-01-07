"""
Memory Feature Module - Centralized AI Memory Layer using Mem0

Provides persistent, semantic memory using Mem0 library:
- Intelligent deduplication and conflict resolution
- Automatic memory updates (new facts update old ones)
- Semantic search (finds related memories by meaning)
- Supabase/pgvector as vector store (all in one database)

Memory Types:
- Facts: Persistent user facts (preferences, background, relationships)
- Interactions: Meeting summaries, key conversations
- Insights: Patterns and observations
- Preferences: User preferences
- Relationships: Info about contacts

Usage:
    from app.features.memory import get_memory_service
    
    mem = get_memory_service()
    
    # Add memories (Mem0 handles deduplication automatically)
    await mem.add("Aaron prefers morning meetings", MemoryType.PREFERENCE)
    
    # Search memories semantically
    results = await mem.search("meeting preferences")
    
    # Get context for prompts
    context = await mem.get_context("meeting with John")
"""

# Use Mem0-based implementation (smart deduplication, semantic search)
from app.features.memory.service import (
    MemoryService,
    get_memory_service,
    MemoryType,
)

__all__ = [
    "MemoryService",
    "get_memory_service", 
    "MemoryType",
]
