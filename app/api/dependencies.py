from functools import lru_cache

# New modular imports
from app.features.database.client import DatabaseClient, get_database_client
from app.features.memory import get_memory_service, MemoryService

# Legacy import for backward compatibility
from app.services.database_legacy import SupabaseMultiDatabase
from app.services.llm import ClaudeMultiAnalyzer


@lru_cache(maxsize=1)
def get_analyzer() -> ClaudeMultiAnalyzer:
    """Provide a singleton Claude analyzer for request handlers."""
    return ClaudeMultiAnalyzer()


@lru_cache(maxsize=1)
def get_database() -> SupabaseMultiDatabase:
    """
    Provide a singleton Supabase interface for request handlers.
    
    DEPRECATED: Use get_database_client() for new code.
    This maintains backward compatibility with existing code.
    """
    return SupabaseMultiDatabase()


def get_services() -> tuple[ClaudeMultiAnalyzer, SupabaseMultiDatabase]:
    """
    Convenience accessor returning analyzer and database together.
    
    DEPRECATED: Use get_analyzer() and get_database_client() separately.
    """
    return get_analyzer(), get_database()


# New recommended accessors
def get_db() -> DatabaseClient:
    """Get the new modular database client."""
    return get_database_client()


def get_memory() -> MemoryService:
    """Get the memory service for AI memory operations."""
    return get_memory_service()
