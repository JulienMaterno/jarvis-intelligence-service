"""
Features Module - Self-contained feature units.

Each feature is a modular unit with its own logic:
- memory: AI memory layer (Mem0)
- database: Organized data access repositories
- chat: Conversational AI with tools
- analysis: Transcript analysis prompts
- briefing: Meeting briefings
- journaling: Journal analysis
- telegram: Telegram notifications
"""

# Core services that other features depend on
from app.features.memory import get_memory_service, MemoryService, MemoryType
from app.features.database import get_database_client, DatabaseClient

__all__ = [
    "get_memory_service",
    "MemoryService", 
    "MemoryType",
    "get_database_client",
    "DatabaseClient",
]
