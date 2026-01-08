"""
Transcripts Repository - Transcript data access operations.

Handles all transcript-related database operations including:
- Creating transcripts from audio processing
- Fetching transcripts for analysis
- Checking for existing processing
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("Jarvis.Database.Transcripts")


class TranscriptsRepository:
    """Repository for transcript operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
    
    def create(
        self,
        source_file: str,
        full_text: str,
        audio_duration_seconds: float = None,
        language: str = None,
        segments: List[Dict] = None,
        speakers: List[str] = None,
        model_used: str = None,
    ) -> str:
        """
        Create a transcript record.
        
        Returns:
            transcript_id (UUID string)
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
    
    def get_by_id(self, transcript_id: str) -> Optional[Dict]:
        """Fetch a transcript by ID."""
        try:
            result = self.client.table("transcripts").select("*").eq("id", transcript_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error fetching transcript {transcript_id}: {e}")
            return None
    
    def get_records_for_transcript(self, transcript_id: str) -> Dict:
        """
        Check if a transcript has already been processed.
        Used for idempotency protection against duplicate processing.
        
        Returns:
            Dict with already_processed flag and linked record IDs
        """
        result = {
            "already_processed": False,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
        }
        
        try:
            # Check meetings
            meetings = self.client.table("meetings").select("id").eq(
                "transcript_id", transcript_id
            ).execute()
            if meetings.data:
                result["meeting_ids"] = [m["id"] for m in meetings.data]
                result["already_processed"] = True
            
            # Check reflections
            reflections = self.client.table("reflections").select("id").eq(
                "transcript_id", transcript_id
            ).execute()
            if reflections.data:
                result["reflection_ids"] = [r["id"] for r in reflections.data]
                result["already_processed"] = True
            
            if result["already_processed"]:
                logger.info(f"Transcript {transcript_id} already processed")
                
        except Exception as e:
            logger.warning(f"Error checking records for transcript {transcript_id}: {e}")
        
        return result
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent transcripts."""
        try:
            result = self.client.table("transcripts").select(
                "id, source_file, language, audio_duration_seconds, created_at"
            ).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting recent transcripts: {e}")
            return []
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search transcripts by text content."""
        try:
            result = self.client.table("transcripts").select(
                "id, source_file, full_text, created_at"
            ).ilike("full_text", f"%{query}%").limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error searching transcripts: {e}")
            return []
    
    def get_all_for_seeding(self, limit: int = 50) -> List[Dict]:
        """Get transcripts for memory seeding."""
        try:
            result = self.client.table("transcripts").select(
                "id, source_file, full_text, language, created_at"
            ).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting transcripts for seeding: {e}")
            return []
