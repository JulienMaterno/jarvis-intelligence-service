"""
Memory Feature Module - Supabase-Native AI Memory Layer

Provides persistent memory storage using Supabase:
- No external dependencies (no Qdrant, no OpenAI embeddings)
- Persists across restarts
- Simple text search (can add pgvector later)

Memory Types:
- Facts: Persistent user facts (preferences, background, relationships)
- Interactions: Meeting summaries, key conversations
- Insights: Patterns and observations
- Preferences: User preferences
- Relationships: Info about contacts

Usage:
    from app.features.memory import get_memory_service
    
    mem = get_memory_service()
    
    # Add memories from any feature
    await mem.add("Aaron prefers morning meetings", memory_type="preference")
    
    # Search memories
    results = await mem.search("meetings")
    
    # Get context for prompts
    context = await mem.get_context("meeting with John")
"""

# Use Supabase-native implementation (simple, persistent, no external deps)
from app.features.memory.service_supabase import (
    MemoryService,
    get_memory_service,
    MemoryType,
)

__all__ = [
    "MemoryService",
    "get_memory_service", 
    "MemoryType",
]
