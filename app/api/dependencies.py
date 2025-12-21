from functools import lru_cache

from app.services.database import SupabaseMultiDatabase
from app.services.llm import ClaudeMultiAnalyzer


@lru_cache(maxsize=1)
def get_analyzer() -> ClaudeMultiAnalyzer:
    """Provide a singleton Claude analyzer for request handlers."""
    return ClaudeMultiAnalyzer()


@lru_cache(maxsize=1)
def get_database() -> SupabaseMultiDatabase:
    """Provide a singleton Supabase interface for request handlers."""
    return SupabaseMultiDatabase()


def get_services() -> tuple[ClaudeMultiAnalyzer, SupabaseMultiDatabase]:
    """Convenience accessor returning analyzer and database together."""
    return get_analyzer(), get_database()
