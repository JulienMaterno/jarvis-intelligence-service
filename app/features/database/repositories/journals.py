"""
Journals Repository - Journal data access operations.

Handles all journal-related database operations including:
- Creating daily journals
- Updating existing journals (one per day)
- Getting journal by date
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Jarvis.Database.Journals")


class JournalsRepository:
    """Repository for journal operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
    
    def get_by_date(self, journal_date: str) -> Optional[Dict]:
        """Get a journal entry by date."""
        try:
            result = self.client.table("journals").select("*").eq(
                "date", journal_date
            ).is_("deleted_at", "null").execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching journal for {journal_date}: {e}")
            return None
    
    def create_or_update(
        self,
        journal_data: Dict,
        transcript: str = None,
        duration: float = None,
        filename: str = None,
        transcript_id: str = None,
        contact_id: str = None,
    ) -> Tuple[str, str]:
        """
        Create or update journal entry in Supabase.
        Since journals are one-per-day, this will update if exists.
        
        Returns:
            Tuple of (journal_id, url)
        """
        try:
            journal_date = journal_data.get('date')
            if not journal_date:
                raise ValueError("Journal must have a date")
            
            summary = journal_data.get('summary', '')
            mood = journal_data.get('mood')
            effort = journal_data.get('effort')
            sports = journal_data.get('sports', [])
            key_events = journal_data.get('key_events', [])
            accomplishments = journal_data.get('accomplishments', [])
            challenges = journal_data.get('challenges', [])
            gratitude = journal_data.get('gratitude', [])
            tomorrow_focus = journal_data.get('tomorrow_focus', [])
            sections = journal_data.get('sections', [])
            
            logger.info(f"Creating/updating journal for: {journal_date}")
            
            # Check if journal exists for this date
            existing = self.get_by_date(journal_date)
            
            payload = {
                "date": journal_date,
                "title": f"Journal - {journal_date}",
                "summary": summary,
                "mood": mood,
                "effort": effort,
                "sports": sports if sports else None,
                "key_events": key_events if key_events else None,
                "accomplishments": accomplishments if accomplishments else None,
                "challenges": challenges if challenges else None,
                "gratitude": gratitude if gratitude else None,
                "tomorrow_focus": tomorrow_focus if tomorrow_focus else None,
                "sections": sections if sections else None,
                "content": transcript[:5000] if transcript else None,
                "source": "voice",
                "source_file": filename,
                "audio_duration_seconds": int(duration) if duration else None,
                "last_sync_source": "supabase",
            }
            
            if transcript_id:
                payload["transcript_id"] = transcript_id
                
            if contact_id:
                payload["contact_id"] = contact_id
            
            if existing:
                # Update existing journal
                journal_id = existing['id']
                # Merge with existing data (don't overwrite with null)
                for key in ['mood', 'effort', 'sports', 'key_events', 'accomplishments', 
                           'challenges', 'gratitude', 'tomorrow_focus']:
                    if payload.get(key) is None and existing.get(key):
                        payload[key] = existing[key]
                
                self.client.table("journals").update(payload).eq("id", journal_id).execute()
                logger.info(f"Journal updated: {journal_id}")
            else:
                # Create new journal
                result = self.client.table("journals").insert(payload).execute()
                journal_id = result.data[0]["id"]
                logger.info(f"Journal created: {journal_id}")
            
            journal_url = f"supabase://journals/{journal_id}"
            return journal_id, journal_url
            
        except Exception as e:
            logger.error(f"Error creating/updating journal: {e}")
            raise
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent journals."""
        try:
            result = self.client.table("journals").select("*").is_(
                "deleted_at", "null"
            ).order("date", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting recent journals: {e}")
            return []
    
    def get_by_id(self, journal_id: str) -> Optional[Dict]:
        """Get a journal by ID."""
        try:
            result = self.client.table("journals").select("*").eq("id", journal_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting journal {journal_id}: {e}")
            return None
    
    def update(self, journal_id: str, updates: Dict) -> bool:
        """Update a journal."""
        try:
            updates["last_sync_source"] = "supabase"
            self.client.table("journals").update(updates).eq("id", journal_id).execute()
            logger.info(f"Updated journal {journal_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating journal {journal_id}: {e}")
            return False
