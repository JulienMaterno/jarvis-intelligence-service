"""
Database Client - Unified Access to All Data Repositories

Provides organized access to data through domain-specific repositories.
This is a thin wrapper that delegates to focused repository classes.
"""

import logging
from functools import lru_cache
from typing import Optional

from app.core.database import supabase
from app.features.database.repositories.contacts import ContactsRepository
from app.features.database.repositories.meetings import MeetingsRepository
from app.features.database.repositories.tasks import TasksRepository
from app.features.database.repositories.transcripts import TranscriptsRepository
from app.features.database.repositories.reflections import ReflectionsRepository
from app.features.database.repositories.journals import JournalsRepository

logger = logging.getLogger("Jarvis.Database")


class DatabaseClient:
    """
    Unified database client providing access to all repositories.
    
    Usage:
        db = get_database_client()
        contact = db.contacts.find_by_name("John")
        meeting = db.meetings.create(data)
    """
    
    _instance: Optional["DatabaseClient"] = None
    
    def __init__(self):
        """Initialize database client with all repositories."""
        self._client = supabase
        
        # Initialize repositories
        self.contacts = ContactsRepository(self._client)
        self.meetings = MeetingsRepository(self._client)
        self.tasks = TasksRepository(self._client)
        self.transcripts = TranscriptsRepository(self._client)
        self.reflections = ReflectionsRepository(self._client)
        self.journals = JournalsRepository(self._client)
        
        logger.info("Database client initialized with all repositories")
    
    @property
    def client(self):
        """Direct access to Supabase client for advanced queries."""
        return self._client
    
    def table(self, name: str):
        """Direct table access for one-off queries."""
        return self._client.table(name)


@lru_cache(maxsize=1)
def get_database_client() -> DatabaseClient:
    """Get the singleton database client."""
    if DatabaseClient._instance is None:
        DatabaseClient._instance = DatabaseClient()
    return DatabaseClient._instance
