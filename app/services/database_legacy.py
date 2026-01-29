"""
Legacy Database Adapter - Backward Compatibility Layer

This module provides backward compatibility for code using the old
SupabaseMultiDatabase class. It delegates to the new modular repositories.

MIGRATION NOTE:
- New code should use: from app.features.database import db
- Old code using SupabaseMultiDatabase continues to work

This layer will be removed after all code is migrated to the new structure.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any

from app.core.database import supabase
from app.features.database.repositories.contacts import ContactsRepository
from app.features.database.repositories.meetings import MeetingsRepository
from app.features.database.repositories.tasks import TasksRepository
from app.features.database.repositories.transcripts import TranscriptsRepository
from app.features.database.repositories.reflections import ReflectionsRepository
from app.features.database.repositories.journals import JournalsRepository

logger = logging.getLogger('Jarvis.Intelligence.Database')


class SupabaseMultiDatabase:
    """
    Legacy compatibility wrapper.
    
    Delegates to new repository structure while maintaining old interface.
    """
    
    def __init__(self):
        self.client = supabase
        
        # Initialize new repositories
        self._contacts = ContactsRepository(self.client)
        self._meetings = MeetingsRepository(self.client)
        self._tasks = TasksRepository(self.client)
        self._transcripts = TranscriptsRepository(self.client)
        self._reflections = ReflectionsRepository(self.client)
        self._journals = JournalsRepository(self.client)
        
        logger.info("Multi-database Supabase client initialized (legacy adapter)")
    
    # =========================================================================
    # CONTACT METHODS (delegated)
    # =========================================================================
    
    def find_contact_by_name(self, name: str) -> Tuple[Optional[Dict], List[Dict]]:
        return self._contacts.find_by_name(name)
    
    def find_contact_by_email(self, email: str) -> Optional[Dict]:
        return self._contacts.find_by_email(email)
    
    def search_contacts(self, query: str, limit: int = 5) -> List[Dict]:
        return self._contacts.search(query, limit)
    
    def find_contact_by_name_or_email(self, name: str = None, email: str = None) -> Tuple[Optional[Dict], List[Dict]]:
        if email:
            contact = self._contacts.find_by_email(email)
            if contact:
                return contact, []
        if name:
            return self._contacts.find_by_name(name)
        return None, []
    
    # =========================================================================
    # TRANSCRIPT METHODS (delegated)
    # =========================================================================
    
    def get_transcript(self, transcript_id: str) -> Optional[Dict]:
        return self._transcripts.get_by_id(transcript_id)
    
    def get_records_for_transcript(self, transcript_id: str) -> Dict:
        return self._transcripts.get_records_for_transcript(transcript_id)
    
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
        return self._transcripts.create(
            source_file=source_file,
            full_text=full_text,
            audio_duration_seconds=audio_duration_seconds,
            language=language,
            segments=segments,
            speakers=speakers,
            model_used=model_used,
        )

    def update_transcript_linkage(
        self,
        transcript_id: str,
        meeting_ids: List[str],
        reflection_ids: List[str],
        journal_ids: List[str] = None,
    ) -> bool:
        """Update transcript with IDs of created records for cross-referencing."""
        return self._transcripts.update_linkage(
            transcript_id=transcript_id,
            meeting_ids=meeting_ids,
            reflection_ids=reflection_ids,
            journal_ids=journal_ids or [],
        )

    # =========================================================================
    # MEETING METHODS (delegated)
    # =========================================================================
    
    def create_meeting(
        self,
        meeting_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None,
        calendar_event_id: str = None,
        person_email: str = None,
    ) -> Tuple[str, str, Dict]:
        return self._meetings.create(
            meeting_data=meeting_data,
            transcript=transcript,
            duration=duration,
            filename=filename,
            transcript_id=transcript_id,
            calendar_event_id=calendar_event_id,
            person_email=person_email,
        )
    
    # =========================================================================
    # REFLECTION METHODS (delegated)
    # =========================================================================
    
    def get_existing_reflection_topics(self, limit: int = 30) -> List[Dict]:
        return self._reflections.get_existing_topics(limit)
    
    def get_reflection_by_id(self, reflection_id: str) -> Optional[Dict]:
        return self._reflections.get_by_id(reflection_id)
    
    def find_similar_reflection(self, topic_key: str, tags: List[str] = None, title: str = None) -> Optional[Dict]:
        return self._reflections.find_similar(topic_key, tags, title)
    
    def create_reflection(
        self,
        reflection_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None,
        contact_id: str = None
    ) -> Tuple[str, str]:
        return self._reflections.create(
            reflection_data=reflection_data,
            transcript=transcript,
            duration=duration,
            filename=filename,
            transcript_id=transcript_id,
            contact_id=contact_id,
        )
    
    def append_to_reflection(
        self,
        reflection_id: str,
        new_sections: List[Dict],
        new_content: str = None,
        additional_tags: List[str] = None,
        source_file: str = None,
        transcript_id: str = None
    ) -> Tuple[str, str]:
        return self._reflections.append(
            reflection_id=reflection_id,
            new_sections=new_sections,
            new_content=new_content,
            additional_tags=additional_tags,
            source_file=source_file,
            transcript_id=transcript_id,
        )
    
    # =========================================================================
    # TASK METHODS (delegated)
    # =========================================================================
    
    def create_tasks(
        self,
        tasks_data: List[Dict],
        origin_id: str,
        origin_type: str = "meeting",
        contact_id: str = None
    ) -> List[str]:
        return self._tasks.create_batch(
            tasks_data=tasks_data,
            origin_id=origin_id,
            origin_type=origin_type,
            contact_id=contact_id,
        )
    
    # =========================================================================
    # JOURNAL METHODS (delegated)
    # =========================================================================
    
    def get_journal_by_date(self, journal_date: str) -> Optional[Dict]:
        return self._journals.get_by_date(journal_date)
    
    def create_journal(
        self,
        journal_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None,
        contact_id: str = None
    ) -> Tuple[str, str]:
        return self._journals.create_or_update(
            journal_data=journal_data,
            transcript=transcript,
            duration=duration,
            filename=filename,
            transcript_id=transcript_id,
            contact_id=contact_id,
        )
    
    # =========================================================================
    # PIPELINE LOGGING (keep here - not worth extracting)
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
    # CRM OPERATIONS (keep here - complex business logic)
    # =========================================================================
    
    def apply_crm_updates(self, crm_updates: List[Dict]) -> Dict[str, Any]:
        """Apply CRM updates extracted from meeting analysis."""
        result = {"updated": [], "not_found": [], "errors": []}
        
        if not crm_updates:
            return result
        
        for update in crm_updates:
            person_name = update.get("person_name", "").strip()
            updates = update.get("updates", {})
            
            if not person_name or not updates:
                continue
            
            try:
                contact, suggestions = self._contacts.find_by_name(person_name)
                
                if not contact:
                    result["not_found"].append({
                        "name": person_name,
                        "suggestions": [
                            f"{s.get('first_name', '')} {s.get('last_name', '')}"
                            for s in suggestions[:3]
                        ]
                    })
                    continue
                
                update_payload = {}
                
                if updates.get("company"):
                    current = contact.get("company", "")
                    if not current or len(updates["company"]) > len(current):
                        update_payload["company"] = updates["company"]
                
                if updates.get("position"):
                    current = contact.get("job_title", "")
                    if not current or len(updates["position"]) > len(current):
                        update_payload["job_title"] = updates["position"]
                
                if updates.get("location"):
                    if not contact.get("location"):
                        update_payload["location"] = updates["location"]
                
                if updates.get("personal_notes"):
                    current_notes = contact.get("notes", "") or ""
                    new_note = updates["personal_notes"]
                    if new_note and new_note not in current_notes:
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y-%m-%d")
                        if current_notes:
                            update_payload["notes"] = f"{current_notes}\n\n[{timestamp}] {new_note}"
                        else:
                            update_payload["notes"] = f"[{timestamp}] {new_note}"
                
                if update_payload:
                    self._contacts.update(contact["id"], update_payload)
                    result["updated"].append({
                        "name": person_name,
                        "contact_id": contact["id"],
                        "fields_updated": list(update_payload.keys())
                    })
                    logger.info(f"CRM update applied for {person_name}")
                
            except Exception as e:
                logger.error(f"Error applying CRM update for {person_name}: {e}")
                result["errors"].append({"name": person_name, "error": str(e)})
        
        return result
    
    # =========================================================================
    # ADDITIONAL METHODS USED BY EXISTING CODE
    # =========================================================================
    
    def get_contact_interactions(self, contact_id: str, limit: int = 50) -> List[Dict]:
        """Get all interactions for a specific contact."""
        try:
            result = self.client.table("interaction_log").select("*").eq(
                "contact_id", contact_id
            ).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching interactions: {e}")
            return []
    
    def link_past_interactions(self, contact_id: str, email: str) -> Dict:
        """Trigger retroactive linking for a contact."""
        try:
            result = self.client.rpc('link_past_interactions', {
                'contact_uuid': contact_id,
                'contact_email': email
            }).execute()
            return result.data
        except Exception as e:
            logger.error(f"Error running retroactive linking: {e}")
            return {"status": "error", "message": str(e)}
    
    def update_contact_interaction_stats(self, contact_id: str) -> None:
        """Update contact interaction statistics."""
        try:
            self.client.rpc('update_contact_interaction_stats', {
                'contact_uuid': contact_id
            }).execute()
        except Exception as e:
            logger.error(f"Error updating contact stats: {e}")

    def get_contacts_for_transcription(self, limit: int = 100) -> List[Dict]:
        """
        Get a list of contacts for smart transcription correction.
        
        Returns contacts with names and companies to help AI correct
        misheard names in transcripts.
        
        Returns: List of dicts with first_name, last_name, company
        """
        try:
            result = self.client.table("contacts").select(
                "first_name, last_name, company"
            ).is_(
                "deleted_at", "null"
            ).order(
                "updated_at", desc=True  # Recent contacts first
            ).limit(limit).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error fetching contacts for transcription: {e}")
            return []
