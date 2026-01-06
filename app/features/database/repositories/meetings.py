"""
Meetings Repository - Meeting data access operations.

Handles all meeting-related database operations including:
- Creating meetings from transcript analysis
- Linking meetings to contacts
- Finding and querying meetings
"""

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Jarvis.Database.Meetings")


class MeetingsRepository:
    """Repository for meeting operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
        # Import contacts repo lazily to avoid circular imports
        self._contacts_repo = None
    
    @property
    def contacts(self):
        """Lazy load contacts repository."""
        if self._contacts_repo is None:
            from app.features.database.repositories.contacts import ContactsRepository
            self._contacts_repo = ContactsRepository(self.client)
        return self._contacts_repo
    
    def create(
        self,
        meeting_data: Dict,
        transcript: str = None,
        duration: float = None,
        filename: str = None,
        transcript_id: str = None,
        calendar_event_id: str = None,
    ) -> Tuple[str, str, Dict]:
        """
        Create meeting entry in Supabase.
        
        Returns:
            Tuple of (meeting_id, url, contact_match_info)
        """
        try:
            title = meeting_data.get('title', 'Untitled Meeting')
            date = meeting_data.get('date')
            location = meeting_data.get('location')
            person_name = meeting_data.get('person_name')
            summary = meeting_data.get('summary', '')
            topics_discussed = meeting_data.get('topics_discussed', [])
            follow_ups = meeting_data.get('follow_up_conversation', [])
            people_mentioned = meeting_data.get('people_mentioned', [])
            key_points = meeting_data.get('key_points', [])
            
            logger.info(f"Creating meeting: {title}")
            
            # Find contact by name with suggestions
            contact_id = None
            contact_match_info = {
                "searched_name": person_name,
                "matched": False,
                "linked_contact": None,
                "suggestions": []
            }
            
            if person_name:
                contact, suggestions = self.contacts.find_by_name(person_name)
                if contact:
                    contact_id = contact.get('id')
                    contact_match_info["matched"] = True
                    contact_match_info["linked_contact"] = {
                        "id": contact.get("id"),
                        "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                        "company": contact.get("company"),
                        "position": contact.get("position")
                    }
                    logger.info(f"Linked meeting to contact: {person_name} ({contact_id})")
                elif suggestions:
                    contact_match_info["suggestions"] = [
                        {
                            "id": s.get("id"),
                            "name": f"{s.get('first_name', '')} {s.get('last_name', '')}".strip(),
                            "company": s.get("company"),
                            "position": s.get("position")
                        }
                        for s in suggestions
                    ]
            
            payload = {
                "title": title,
                "date": date,
                "location": location,
                "summary": summary,
                "topics_discussed": topics_discussed,
                "follow_up_items": follow_ups,
                "people_mentioned": people_mentioned,
                "key_points": key_points,
                "contact_id": contact_id,
                "contact_name": person_name,
                "source_file": filename,
                "audio_duration_seconds": int(duration) if duration else None,
                "last_sync_source": "supabase",
            }
            
            if transcript_id:
                payload["source_transcript_id"] = transcript_id
            
            if calendar_event_id:
                payload["calendar_event_id"] = calendar_event_id
            
            result = self.client.table("meetings").insert(payload).execute()
            meeting_id = result.data[0]["id"]
            meeting_url = f"supabase://meetings/{meeting_id}"
            
            logger.info(f"Meeting created: {meeting_id}")
            return meeting_id, meeting_url, contact_match_info
            
        except Exception as e:
            logger.error(f"Error creating meeting: {e}")
            raise
    
    def get_by_id(self, meeting_id: str) -> Optional[Dict]:
        """Get a meeting by ID."""
        try:
            result = self.client.table("meetings").select("*").eq("id", meeting_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error getting meeting {meeting_id}: {e}")
            return None
    
    def get_by_contact(self, contact_id: str, limit: int = 10) -> List[Dict]:
        """Get meetings for a specific contact."""
        try:
            result = self.client.table("meetings").select("*").eq(
                "contact_id", contact_id
            ).order("date", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting meetings for contact {contact_id}: {e}")
            return []
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent meetings."""
        try:
            result = self.client.table("meetings").select("*").order(
                "date", desc=True
            ).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting recent meetings: {e}")
            return []
    
    def link_contact(self, meeting_id: str, contact_id: str) -> bool:
        """Link a meeting to a contact."""
        try:
            self.client.table("meetings").update({
                "contact_id": contact_id,
                "last_sync_source": "supabase",
            }).eq("id", meeting_id).execute()
            logger.info(f"Linked meeting {meeting_id} to contact {contact_id}")
            return True
        except Exception as e:
            logger.error(f"Error linking meeting to contact: {e}")
            return False
    
    def get_by_transcript(self, transcript_id: str) -> List[Dict]:
        """Get meetings linked to a transcript."""
        try:
            result = self.client.table("meetings").select("*").eq(
                "source_transcript_id", transcript_id
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting meetings for transcript {transcript_id}: {e}")
            return []
    
    def get_all_for_seeding(self, limit: int = 100) -> List[Dict]:
        """Get meetings for memory seeding (recent with summaries)."""
        try:
            result = self.client.table("meetings").select(
                "id, title, summary, contact_name, date, topics_discussed"
            ).not_.is_("summary", "null").order(
                "date", desc=True
            ).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting meetings for seeding: {e}")
            return []
