"""
Database Feature Module - Organized Data Access Layer

Provides clean, organized access to all Supabase tables.
Replaces the monolithic database.py with focused sub-modules.

Usage:
    from app.features.database import db
    
    # Contacts
    contact = await db.contacts.find_by_name("John")
    
    # Meetings  
    meeting_id = await db.meetings.create(meeting_data)
    
    # Tasks
    tasks = await db.tasks.get_pending()
"""

from app.features.database.client import DatabaseClient, get_database_client

# Create singleton alias
db = get_database_client

__all__ = [
    "DatabaseClient",
    "get_database_client",
    "db",
]
