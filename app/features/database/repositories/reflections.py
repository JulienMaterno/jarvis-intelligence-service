"""
Reflections Repository - Reflection data access operations.

Handles all reflection-related database operations including:
- Creating and appending to reflections
- Topic-based routing and matching
- Finding similar reflections
"""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Jarvis.Database.Reflections")


class ReflectionsRepository:
    """Repository for reflection operations."""
    
    def __init__(self, client):
        """Initialize with Supabase client."""
        self.client = client
    
    def get_existing_topics(self, limit: int = 30) -> List[Dict]:
        """
        Fetch existing reflection topics for AI-driven routing.
        
        Returns:
            List of {id, topic_key, title} for AI to decide routing
        """
        try:
            result = self.client.table("reflections").select(
                "id, topic_key, title"
            ).is_(
                "deleted_at", "null"
            ).order(
                "created_at", desc=True
            ).limit(limit).execute()
            
            if result.data:
                reflections = []
                for r in result.data:
                    reflections.append({
                        'id': r.get('id'),
                        'topic_key': r.get('topic_key', 'none'),
                        'title': r.get('title', 'Untitled')
                    })
                logger.info(f"Found {len(reflections)} existing reflections for routing")
                return reflections
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching reflections for routing: {e}")
            return []
    
    def get_by_id(self, reflection_id: str) -> Optional[Dict]:
        """Fetch a reflection by its ID."""
        if not reflection_id:
            return None
            
        try:
            result = self.client.table("reflections").select(
                "id, title, topic_key, tags, content, sections"
            ).eq("id", reflection_id).is_("deleted_at", "null").execute()
            
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Error fetching reflection by id '{reflection_id}': {e}")
            return None
    
    def find_similar(
        self,
        topic_key: str,
        tags: List[str] = None,
        title: str = None,
    ) -> Optional[Dict]:
        """
        Find an existing reflection that matches by topic_key.
        
        NOTE: This is a FALLBACK method. Primary routing is AI-driven via append_to_id.
        """
        if not topic_key:
            return None
            
        try:
            topic_lower = topic_key.lower().strip()
            topic_as_title = topic_lower.replace("-", " ")
            topic_words = [w for w in topic_lower.replace("-", " ").split() if len(w) > 2]
            
            if not topic_words:
                return None
            
            # Check if topic_key contains a number
            has_number = bool(re.search(r'\d+', topic_lower))
            
            # Strategy 1: Exact topic_key match
            result = self.client.table("reflections").select("*").ilike(
                "topic_key", topic_lower
            ).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute()
            
            if result.data:
                logger.info(f"Found reflection by exact topic_key: {topic_key}")
                return result.data[0]
            
            # Don't fuzzy match numbered topics
            if has_number:
                return None
            
            # Strategy 2: Title contains the topic
            for search_term in [topic_as_title, topic_lower]:
                if len(search_term) >= 5:
                    result = self.client.table("reflections").select("*").ilike(
                        "title", f"%{search_term}%"
                    ).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute()
                    
                    if result.data:
                        logger.info(f"Found reflection by title match for topic '{topic_key}'")
                        return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding similar reflection for '{topic_key}': {e}")
            return None
    
    def create(
        self,
        reflection_data: Dict,
        transcript: str = None,
        duration: float = None,
        filename: str = None,
        transcript_id: str = None,
        contact_id: str = None,
    ) -> Tuple[str, str]:
        """
        Create reflection entry in Supabase.
        
        Returns:
            Tuple of (reflection_id, url)
        """
        try:
            title = reflection_data.get('title', 'Untitled Reflection')
            date = reflection_data.get('date')
            location = reflection_data.get('location')
            tags = reflection_data.get('tags', [])
            sections = reflection_data.get('sections', [])
            content = reflection_data.get('content', '')
            topic_key = reflection_data.get('topic_key')
            
            # Add timestamp header
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            timestamp_header = f"### 📝 Entry: {timestamp_str}\n\n"
            
            # Generate content from sections if empty
            if not content and sections:
                content_parts = [timestamp_header]
                for section in sections:
                    heading = section.get('heading', '')
                    section_content = section.get('content', '')
                    if heading:
                        content_parts.append(f"## {heading}")
                    if section_content:
                        content_parts.append(section_content)
                    content_parts.append("")
                content = "\n".join(content_parts).strip()
            elif content:
                content = timestamp_header + content
            
            logger.info(f"Creating reflection: {title}")
            
            payload = {
                "title": title,
                "date": date,
                "location": location,
                "tags": tags,
                "sections": sections,
                "content": content,
                "source_file": filename,
                "audio_duration_seconds": int(duration) if duration else None,
                "last_sync_source": "supabase",
            }
            
            if topic_key:
                payload["topic_key"] = topic_key
            if transcript_id:
                payload["transcript_id"] = transcript_id
            if contact_id:
                payload["contact_id"] = contact_id
            
            result = self.client.table("reflections").insert(payload).execute()
            reflection_id = result.data[0]["id"]
            reflection_url = f"supabase://reflections/{reflection_id}"
            
            logger.info(f"Reflection created: {reflection_id}")
            return reflection_id, reflection_url
            
        except Exception as e:
            logger.error(f"Error creating reflection: {e}")
            raise
    
    def append(
        self,
        reflection_id: str,
        new_sections: List[Dict],
        new_content: str = None,
        additional_tags: List[str] = None,
        source_file: str = None,
        transcript_id: str = None,
    ) -> Tuple[str, str]:
        """
        Append new content to an existing reflection.
        
        Returns:
            Tuple of (reflection_id, url)
        """
        try:
            # Fetch existing reflection
            result = self.client.table("reflections").select("*").eq("id", reflection_id).execute()
            if not result.data:
                raise ValueError(f"Reflection {reflection_id} not found")
            
            existing = result.data[0]
            existing_sections = existing.get('sections', []) or []
            existing_tags = existing.get('tags', []) or []
            existing_content = existing.get('content', '') or ''
            
            # Add divider section
            divider_section = {
                "heading": f"--- Added {datetime.now().strftime('%Y-%m-%d %H:%M')} ---",
                "content": f"From: {source_file}" if source_file else ""
            }
            
            updated_sections = existing_sections + [divider_section] + new_sections
            
            # Update content with timestamp
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            if new_content:
                timestamped_content = f"\n\n---\n\n### 📝 Update: {timestamp_str}\n\n{new_content}"
                updated_content = f"{existing_content}{timestamped_content}"
            elif new_sections:
                content_parts = [f"\n\n---\n\n### 📝 Update: {timestamp_str}\n"]
                for section in new_sections:
                    heading = section.get('heading', '')
                    section_content = section.get('content', '')
                    if heading:
                        content_parts.append(f"## {heading}")
                    if section_content:
                        content_parts.append(section_content)
                    content_parts.append("")
                updated_content = f"{existing_content}\n".join(content_parts).strip()
            else:
                updated_content = existing_content
            
            # Merge tags
            updated_tags = list(set(existing_tags + (additional_tags or [])))
            
            # Update the reflection
            update_payload = {
                "sections": updated_sections,
                "content": updated_content,
                "tags": updated_tags,
                "updated_at": datetime.now().isoformat(),
                "last_sync_source": "supabase",
            }
            
            self.client.table("reflections").update(update_payload).eq("id", reflection_id).execute()
            
            logger.info(f"Appended to reflection {reflection_id}: +{len(new_sections)} sections")
            return reflection_id, f"supabase://reflections/{reflection_id}"
            
        except Exception as e:
            logger.error(f"Error appending to reflection {reflection_id}: {e}")
            raise
    
    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent reflections."""
        try:
            result = self.client.table("reflections").select("*").is_(
                "deleted_at", "null"
            ).order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting recent reflections: {e}")
            return []
    
    def get_by_topic(self, topic_key: str) -> List[Dict]:
        """Get reflections by topic key."""
        try:
            result = self.client.table("reflections").select("*").ilike(
                "topic_key", topic_key
            ).is_("deleted_at", "null").order("created_at", desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting reflections for topic {topic_key}: {e}")
            return []
