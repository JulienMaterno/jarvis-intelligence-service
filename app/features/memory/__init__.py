"""
Memory Feature Module - Centralized AI Memory Layer

Provides persistent, semantic memory across all features using Mem0.
This is THE source of truth for what Jarvis "remembers" about the user.

Memory Levels:
- Facts: Persistent user facts (preferences, background, relationships)
- Interactions: Meeting summaries, key conversations
- Context: Short-term context for ongoing tasks

Usage:
    from app.features.memory import memory_service
    
    # Add memories from any feature
    await memory_service.remember_fact("User is vegetarian")
    await memory_service.remember_interaction(meeting_summary)
    
    # Get relevant context for any operation
    context = await memory_service.get_context("meeting with John")
"""

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
