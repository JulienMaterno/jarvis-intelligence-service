"""
Multi-Database Supabase Helper.
Handles creation and updates across Meetings, Reflections, Tasks, and Contacts.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from app.core.database import supabase

logger = logging.getLogger('Jarvis.Intelligence.Database')

class SupabaseMultiDatabase:
    """Handle operations across multiple Supabase tables."""
    
    def __init__(self):
        self.client = supabase
        logger.info("Multi-database Supabase client initialized")
    
    # =========================================================================
    # PIPELINE LOGGING
    # =========================================================================
    
    def log_pipeline_event(
        self, 
        run_id: str,
        event_type: str,
        status: str,
        message: str,
        source_file: str = None,
        duration_ms: int = None,
        details: dict = None
    ) -> None:
        """
        Log a pipeline event to pipeline_logs table.
        """
        try:
            payload = {
                "run_id": run_id,
                "event_type": event_type,
                "status": status,
                "message": message,
            }
            if source_file:
                payload["source_file"] = source_file
            if duration_ms is not None:
                payload["duration_ms"] = duration_ms
            if details:
                payload["details"] = details
            
            self.client.table("pipeline_logs").insert(payload).execute()
            logger.debug(f"[{event_type}] {status}: {message}")
        except Exception as e:
            logger.error(f"Failed to log pipeline event: {e}")
    
    # =========================================================================
    # CONTACT LOOKUP
    # =========================================================================
    
    def find_contact_by_name(self, name: str) -> Optional[Dict]:
        """
        Find a contact by name using fuzzy matching.
        Returns the contact dict if found, None otherwise.
        """
        if not name:
            return None
        
        try:
            # Split name into parts
            name_parts = name.strip().split()
            if not name_parts:
                return None
            
            first_name = name_parts[0]
            last_name = name_parts[-1] if len(name_parts) > 1 else None
            
            # Strategy 1: Exact full name match
            if last_name:
                result = self.client.table("contacts").select("*").ilike(
                    "first_name", first_name
                ).ilike(
                    "last_name", last_name
                ).is_("deleted_at", "null").execute()
                
                if result.data:
                    logger.info(f"Found contact by exact name: {name}")
                    return result.data[0]
            
            # Strategy 2: First name only (if unique)
            result = self.client.table("contacts").select("*").ilike(
                "first_name", first_name
            ).is_("deleted_at", "null").execute()
            
            if len(result.data) == 1:
                contact = result.data[0]
                logger.info(f"Found unique contact by first name '{first_name}': {contact.get('first_name')} {contact.get('last_name')}")
                return contact
            elif len(result.data) > 1:
                logger.info(f"Multiple contacts match first name '{first_name}', skipping auto-link")
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding contact '{name}': {e}")
            return None
    
    # =========================================================================
    # TRANSCRIPTS
    # =========================================================================
    
    def get_transcript(self, transcript_id: str) -> Optional[Dict]:
        """
        Fetch a transcript by ID.
        """
        try:
            result = self.client.table("transcripts").select("*").eq("id", transcript_id).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching transcript {transcript_id}: {e}")
            return None

    def create_transcript(
        self,
        source_file: str,
        full_text: str,
        audio_duration_seconds: float = None,
        language: str = None,
        segments: List[Dict] = None,
        speakers: List[str] = None,
        model_used: str = None
    ) -> str:
        """
        Create a transcript record.
        Returns: transcript_id (UUID string)
        """
        try:
            payload = {
                "source_file": source_file,
                "full_text": full_text,
            }
            if audio_duration_seconds is not None:
                payload["audio_duration_seconds"] = audio_duration_seconds
            if language:
                payload["language"] = language
            if segments:
                payload["segments"] = segments
            if speakers:
                payload["speakers"] = speakers
            if model_used:
                payload["model_used"] = model_used
            
            result = self.client.table("transcripts").insert(payload).execute()
            transcript_id = result.data[0]["id"]
            logger.info(f"Transcript created: {transcript_id}")
            return transcript_id
            
        except Exception as e:
            logger.error(f"Error creating transcript: {e}")
            raise
    
    # =========================================================================
    # MEETINGS
    # =========================================================================
    
    def create_meeting(
        self,
        meeting_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None
    ) -> Tuple[str, str]:
        """
        Create meeting entry in Supabase.
        Returns: Tuple of (meeting_id, "supabase://meetings/{id}")
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
            
            # Find contact by name
            contact_id = None
            if person_name:
                contact = self.find_contact_by_name(person_name)
                if contact:
                    contact_id = contact.get('id')
                    logger.info(f"Linked meeting to contact: {person_name} ({contact_id})")
            
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
                "audio_duration_seconds": duration,
            }
            
            if transcript_id:
                payload["transcript_id"] = transcript_id
            
            result = self.client.table("meetings").insert(payload).execute()
            meeting_id = result.data[0]["id"]
            meeting_url = f"supabase://meetings/{meeting_id}"
            
            logger.info(f"Meeting created: {meeting_id}")
            return meeting_id, meeting_url
            
        except Exception as e:
            logger.error(f"Error creating meeting: {e}")
            raise
    
    # =========================================================================
    # REFLECTIONS
    # =========================================================================
    
    def create_reflection(
        self,
        reflection_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None
    ) -> Tuple[str, str]:
        """
        Create reflection entry in Supabase.
        Returns: Tuple of (reflection_id, "supabase://reflections/{id}")
        """
        try:
            title = reflection_data.get('title', 'Untitled Reflection')
            date = reflection_data.get('date')
            location = reflection_data.get('location')
            tags = reflection_data.get('tags', [])
            sections = reflection_data.get('sections', [])
            content = reflection_data.get('content', '')
            
            logger.info(f"Creating reflection: {title}")
            
            payload = {
                "title": title,
                "date": date,
                "location": location,
                "tags": tags,
                "sections": sections,
                "content": content,
                "source_file": filename,
                "audio_duration_seconds": duration,
            }
            
            if transcript_id:
                payload["transcript_id"] = transcript_id
            
            result = self.client.table("reflections").insert(payload).execute()
            reflection_id = result.data[0]["id"]
            reflection_url = f"supabase://reflections/{reflection_id}"
            
            logger.info(f"Reflection created: {reflection_id}")
            return reflection_id, reflection_url
            
        except Exception as e:
            logger.error(f"Error creating reflection: {e}")
            raise
    
    # =========================================================================
    # TASKS
    # =========================================================================
    
    def create_tasks(
        self,
        tasks_data: List[Dict],
        origin_id: str,
        origin_type: str = "meeting"
    ) -> List[str]:
        """
        Create tasks in Supabase.
        """
        created_ids = []
        if not tasks_data:
            return created_ids
            
        try:
            logger.info(f"Creating {len(tasks_data)} tasks linked to {origin_type} {origin_id}")
            
            for task in tasks_data:
                payload = {
                    "title": task.get('task', 'Untitled Task'),
                    "status": "todo",
                    "priority": task.get('priority', 'medium').lower(),
                    "due_date": task.get('due_date'),
                    "assignee": task.get('assignee'),
                    "origin_table": origin_type + "s", # meetings or reflections
                    "origin_id": origin_id
                }
                
                result = self.client.table("tasks").insert(payload).execute()
                created_ids.append(result.data[0]["id"])
                
            return created_ids
            
        except Exception as e:
            logger.error(f"Error creating tasks: {e}")
            # Don't raise here, we want to return what we created
            return created_ids
