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
    
    def find_contact_by_name(self, name: str) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Find a contact by name using fuzzy matching.
        Returns tuple of (matched_contact, suggestions).
        - matched_contact: The contact dict if found with high confidence, None otherwise
        - suggestions: List of possible matches if no exact match (for user to choose)
        """
        if not name:
            return None, []
        
        try:
            # Split name into parts
            name_parts = name.strip().split()
            if not name_parts:
                return None, []
            
            first_name = name_parts[0].lower()
            last_name = name_parts[-1].lower() if len(name_parts) > 1 else None
            
            # Strategy 1: Exact full name match (case-insensitive)
            if last_name:
                result = self.client.table("contacts").select("*").ilike(
                    "first_name", first_name
                ).ilike(
                    "last_name", last_name
                ).is_("deleted_at", "null").execute()
                
                if result.data:
                    logger.info(f"Found contact by exact name: {name}")
                    return result.data[0], []
            
            # Strategy 2: First name only match
            result = self.client.table("contacts").select("*").ilike(
                "first_name", f"%{first_name}%"
            ).is_("deleted_at", "null").limit(10).execute()
            
            if len(result.data) == 1:
                contact = result.data[0]
                logger.info(f"Found unique contact by first name '{first_name}': {contact.get('first_name')} {contact.get('last_name')}")
                return contact, []
            elif len(result.data) > 1:
                # Multiple matches - return as suggestions
                logger.info(f"Multiple contacts match '{first_name}', returning as suggestions")
                return None, result.data[:5]  # Max 5 suggestions
            
            # Strategy 3: Fuzzy search - search in both first and last name
            result = self.client.table("contacts").select("*").or_(
                f"first_name.ilike.%{first_name}%,last_name.ilike.%{first_name}%"
            ).is_("deleted_at", "null").limit(5).execute()
            
            if result.data:
                logger.info(f"Found {len(result.data)} fuzzy matches for '{name}'")
                return None, result.data
            
            return None, []
            
        except Exception as e:
            logger.error(f"Error finding contact '{name}': {e}")
            return None, []
    
    def search_contacts(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search contacts by partial name match.
        Used for suggesting corrections.
        """
        if not query or len(query) < 2:
            return []
        
        try:
            result = self.client.table("contacts").select(
                "id, first_name, last_name, company, position"
            ).or_(
                f"first_name.ilike.%{query}%,last_name.ilike.%{query}%"
            ).is_("deleted_at", "null").limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            return []
    
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

    def get_records_for_transcript(self, transcript_id: str) -> Dict:
        """
        Check if a transcript has already been processed by looking for linked records.
        Used for idempotency protection against duplicate processing.
        
        Returns:
            Dict with:
                - already_processed: bool
                - meeting_ids: list
                - reflection_ids: list
                - journal_ids: list
                - task_ids: list
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
            meetings = self.client.table("meetings").select("id").eq("source_transcript_id", transcript_id).execute()
            if meetings.data:
                result["meeting_ids"] = [m["id"] for m in meetings.data]
                result["already_processed"] = True
            
            # Check reflections
            reflections = self.client.table("reflections").select("id").eq("source_transcript_id", transcript_id).execute()
            if reflections.data:
                result["reflection_ids"] = [r["id"] for r in reflections.data]
                result["already_processed"] = True
            
            # Check journals - they might have source_file matching
            # Journals don't have source_transcript_id, so we check by pattern
            
            # If any records exist, mark as processed
            if result["meeting_ids"] or result["reflection_ids"]:
                logger.info(f"Transcript {transcript_id} already has {len(result['meeting_ids'])} meetings and {len(result['reflection_ids'])} reflections")
                
        except Exception as e:
            logger.warning(f"Error checking existing records for transcript {transcript_id}: {e}")
            # Don't block processing on check failure
        
        return result

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
            
            # Find contact by name with suggestions
            contact_id = None
            contact_match_info = {
                "searched_name": person_name,
                "matched": False,
                "linked_contact": None,
                "suggestions": []
            }
            
            if person_name:
                contact, suggestions = self.find_contact_by_name(person_name)
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
                    logger.info(f"No exact match for '{person_name}', found {len(suggestions)} suggestions")
            
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
                "last_sync_source": "supabase"  # Mark as created in Supabase - needs sync to Notion
            }
            
            if transcript_id:
                payload["transcript_id"] = transcript_id
            
            result = self.client.table("meetings").insert(payload).execute()
            meeting_id = result.data[0]["id"]
            meeting_url = f"supabase://meetings/{meeting_id}"
            
            logger.info(f"Meeting created: {meeting_id}")
            return meeting_id, meeting_url, contact_match_info
            
        except Exception as e:
            logger.error(f"Error creating meeting: {e}")
            raise
    
    # =========================================================================
    # REFLECTIONS
    # =========================================================================
    
    def get_existing_reflection_topics(self, limit: int = 30) -> List[Dict]:
        """
        Fetch existing reflection topics for smart routing.
        Returns list of {topic_key, title} for topics that have topic_key set.
        
        This is passed to Claude so it can decide whether to append to existing
        topics or create new ones.
        """
        try:
            # Get reflections with topic_key set, ordered by most recent
            result = self.client.table("reflections").select(
                "topic_key, title"
            ).not_.is_(
                "topic_key", "null"
            ).is_(
                "deleted_at", "null"
            ).order(
                "created_at", desc=True
            ).limit(limit).execute()
            
            if result.data:
                # Deduplicate by topic_key (keep first/most recent)
                seen = set()
                unique_topics = []
                for r in result.data:
                    tk = r.get('topic_key')
                    if tk and tk not in seen:
                        seen.add(tk)
                        unique_topics.append({
                            'topic_key': tk,
                            'title': r.get('title', 'Untitled')
                        })
                logger.info(f"Found {len(unique_topics)} existing reflection topics")
                return unique_topics
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching reflection topics: {e}")
            return []
    
    def find_similar_reflection(self, topic_key: str, tags: List[str] = None, title: str = None) -> Optional[Dict]:
        """
        Find an existing reflection that matches by topic_key, tags, or title similarity.
        Used for appending to ongoing topics like "Project Jarvis" or "Explore Out Loud Newsletter".
        
        Priority:
        1. Exact topic_key match (highest confidence)
        2. Topic_key in title (e.g., topic_key="project-jarvis" matches title containing "project jarvis")
        3. Title contains topic_key keywords
        4. Significant tag overlap
        
        IMPORTANT: Numbered topics (e.g., "exploring-out-loud-4") only match exact topic_key.
        This prevents "Exploring Out Loud #4" from appending to "#3".
        
        Returns: The matching reflection dict or None
        """
        import re
        
        if not topic_key:
            return None
            
        try:
            # Normalize topic_key for searching
            topic_lower = topic_key.lower().strip()
            # Convert hyphenated to space-separated for title matching
            topic_as_title = topic_lower.replace("-", " ")
            topic_words = [w for w in topic_lower.replace("-", " ").split() if len(w) > 2]
            
            if not topic_words:
                return None
            
            # Check if topic_key contains a number (like "exploring-out-loud-4")
            # If so, ONLY do exact matching - don't fuzzy match to different numbers
            has_number = bool(re.search(r'\d+', topic_lower))
            
            # Strategy 1: Search by topic_key field (exact match, case-insensitive)
            result = self.client.table("reflections").select("*").ilike(
                "topic_key", topic_lower
            ).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute()
            
            if result.data:
                logger.info(f"Found reflection by exact topic_key: {topic_key} -> '{result.data[0].get('title')}'")
                return result.data[0]
            
            # If topic_key has a number, STOP HERE - don't do fuzzy matching
            # This prevents "exploring-out-loud-4" from matching "Exploring Out Loud #3"
            if has_number:
                logger.info(f"Topic key '{topic_key}' has number - no fuzzy matching, creating new reflection")
                return None
            
            # Strategy 2: Search by title containing the topic (space or hyphen version)
            # This catches reflections created before topic_key was set
            for search_term in [topic_as_title, topic_lower]:
                if len(search_term) >= 5:  # Only search if meaningful
                    result = self.client.table("reflections").select("*").ilike(
                        "title", f"%{search_term}%"
                    ).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute()
                    
                    if result.data:
                        logger.info(f"Found reflection by title match: '{result.data[0].get('title')}' for topic '{topic_key}'")
                        return result.data[0]
            
            # Strategy 3: Search by individual key words in title (for multi-word topics)
            for word in topic_words:
                if len(word) >= 4:  # Only search meaningful words
                    result = self.client.table("reflections").select("*").ilike(
                        "title", f"%{word}%"
                    ).is_("deleted_at", "null").order("created_at", desc=True).limit(5).execute()
                    
                    if result.data:
                        # Check for good match - at least 2 words match or strong keyword
                        for ref in result.data:
                            ref_title_lower = ref.get('title', '').lower()
                            matching_words = sum(1 for w in topic_words if w in ref_title_lower)
                            # Good match if 2+ words match, or if topic_as_title is in title
                            if matching_words >= 2 or topic_as_title in ref_title_lower:
                                logger.info(f"Found reflection by keyword match: '{ref['title']}' for topic '{topic_key}'")
                                return ref
            
            # Strategy 4: Tag overlap (if tags provided)
            if tags and len(tags) >= 1:
                for tag in tags:
                    result = self.client.table("reflections").select("*").contains(
                        "tags", [tag]
                    ).is_("deleted_at", "null").order("created_at", desc=True).limit(5).execute()
                    
                    if result.data:
                        # Check for significant overlap
                        for ref in result.data:
                            ref_tags = ref.get('tags', [])
                            if ref_tags:
                                overlap = set(tags) & set(ref_tags)
                                if len(overlap) >= 1 and any(w in ref.get('title', '').lower() for w in topic_words):
                                    logger.info(f"Found reflection by tag+title match: {ref['title']}")
                                    return ref
            
            logger.info(f"No existing reflection found for topic: {topic_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding similar reflection for '{topic_key}': {e}")
            return None
    
    def append_to_reflection(
        self,
        reflection_id: str,
        new_sections: List[Dict],
        new_content: str = None,
        additional_tags: List[str] = None,
        source_file: str = None,
        transcript_id: str = None
    ) -> Tuple[str, str]:
        """
        Append new content to an existing reflection.
        Adds new sections at the end and optionally merges tags.
        
        Returns: Tuple of (reflection_id, url)
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
            
            # Merge sections - add divider and new sections
            from datetime import datetime
            divider_section = {
                "heading": f"--- Added {datetime.now().strftime('%Y-%m-%d %H:%M')} ---",
                "content": f"From: {source_file}" if source_file else ""
            }
            
            updated_sections = existing_sections + [divider_section] + new_sections
            
            # Merge content - generate from new_sections if new_content not provided
            # Always add visible timestamp header for timeline tracking
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            updated_content = existing_content
            if new_content:
                # Add timestamp to user-provided content
                timestamped_content = f"\n\n---\n\n### 📝 Update: {timestamp_str}\n\n{new_content}"
                updated_content = f"{existing_content}{timestamped_content}" if existing_content else f"### 📝 Entry: {timestamp_str}\n\n{new_content}"
            elif new_sections:
                # Generate content from sections as fallback with visible timestamp
                content_parts = [f"\n\n---\n\n### 📝 Update: {timestamp_str}\n"]
                for section in new_sections:
                    heading = section.get('heading', '')
                    section_content = section.get('content', '')
                    if heading:
                        content_parts.append(f"## {heading}")
                    if section_content:
                        content_parts.append(section_content)
                    content_parts.append("")
                new_content_generated = "\n".join(content_parts).strip()
                updated_content = f"{existing_content}{new_content_generated}" if existing_content else new_content_generated.replace("Update:", "Entry:")
            
            # Merge tags (unique)
            updated_tags = list(set(existing_tags + (additional_tags or [])))
            
            # Update the reflection
            update_payload = {
                "sections": updated_sections,
                "content": updated_content,
                "tags": updated_tags,
                "updated_at": datetime.now().isoformat(),
                "last_sync_source": "supabase"  # Mark that Supabase changed - needs sync to Notion
            }
            
            self.client.table("reflections").update(update_payload).eq("id", reflection_id).execute()
            
            logger.info(f"Appended to reflection {reflection_id}: +{len(new_sections)} sections")
            return reflection_id, f"supabase://reflections/{reflection_id}"
            
        except Exception as e:
            logger.error(f"Error appending to reflection {reflection_id}: {e}")
            raise
    
    def create_reflection(
        self,
        reflection_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None,
        contact_id: str = None
    ) -> Tuple[str, str]:
        """
        Create reflection entry in Supabase.
        Returns: Tuple of (reflection_id, "supabase://reflections/{id}")
        """
        try:
            from datetime import datetime
            
            title = reflection_data.get('title', 'Untitled Reflection')
            date = reflection_data.get('date')
            location = reflection_data.get('location')
            tags = reflection_data.get('tags', [])
            sections = reflection_data.get('sections', [])
            content = reflection_data.get('content', '')
            topic_key = reflection_data.get('topic_key')  # New field for topic matching
            
            # Add timestamp header to content for tracking development over time
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M')
            timestamp_header = f"### 📝 Entry: {timestamp_str}\n\n"
            
            # Fallback: generate content from sections if content is empty
            if not content and sections:
                content_parts = [timestamp_header]
                for section in sections:
                    heading = section.get('heading', '')
                    section_content = section.get('content', '')
                    if heading:
                        content_parts.append(f"## {heading}")
                    if section_content:
                        content_parts.append(section_content)
                    content_parts.append("")  # Empty line between sections
                content = "\n".join(content_parts).strip()
                logger.info(f"Generated content from {len(sections)} sections")
            elif content:
                # Prepend timestamp to existing content
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
                "last_sync_source": "supabase"  # Mark as created in Supabase - needs sync to Notion
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
    
    # =========================================================================
    # TASKS
    # =========================================================================
    
    def create_tasks(
        self,
        tasks_data: List[Dict],
        origin_id: str,
        origin_type: str = "meeting",
        contact_id: str = None
    ) -> List[str]:
        """
        Create tasks in Supabase.
        Checks for existing tasks with same title to prevent duplicates.
        """
        created_ids = []
        if not tasks_data:
            return created_ids
            
        try:
            logger.info(f"Creating {len(tasks_data)} tasks linked to {origin_type} {origin_id}")
            
            for task in tasks_data:
                # Support both 'title' and 'task' keys for task name
                title = task.get('title') or task.get('task', 'Untitled Task')
                
                # Check if task with same title already exists (not deleted)
                existing = self.client.table("tasks").select("id, title").eq(
                    "title", title
                ).is_("deleted_at", "null").limit(1).execute()
                
                if existing.data:
                    logger.info(f"Task already exists, skipping: {title}")
                    created_ids.append(existing.data[0]["id"])  # Return existing ID
                    continue
                
                payload = {
                    "title": title,
                    "description": task.get('description', ''),
                    "status": "pending",
                    "priority": task.get('priority', 'medium').lower(),
                    "due_date": task.get('due_date'),
                    "origin_type": origin_type,
                    "origin_id": origin_id,
                    "last_sync_source": "supabase"  # Mark as created in Supabase - needs sync to Notion
                }
                
                if contact_id:
                    payload["contact_id"] = contact_id
                
                result = self.client.table("tasks").insert(payload).execute()
                created_ids.append(result.data[0]["id"])
                logger.info(f"Created task: {title}")
                
            return created_ids
            
        except Exception as e:
            logger.error(f"Error creating tasks: {e}")
            # Don't raise here, we want to return what we created
            return created_ids

    # =========================================================================
    # JOURNALS
    # =========================================================================
    
    def get_journal_by_date(self, journal_date: str) -> Optional[Dict]:
        """
        Get a journal entry by date.
        Returns None if not found.
        """
        try:
            result = self.client.table("journals").select("*").eq(
                "date", journal_date
            ).is_("deleted_at", "null").execute()
            
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching journal for {journal_date}: {e}")
            return None
    
    def create_journal(
        self,
        journal_data: Dict,
        transcript: str,
        duration: float,
        filename: str,
        transcript_id: str = None,
        contact_id: str = None
    ) -> Tuple[str, str]:
        """
        Create or update journal entry in Supabase.
        Since journals are one-per-day, this will update if exists.
        Returns: Tuple of (journal_id, "supabase://journals/{id}")
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
            existing = self.get_journal_by_date(journal_date)
            
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
                "content": transcript[:5000] if transcript else None,  # Store truncated transcript
                "source": "voice",
                "source_file": filename,
                "audio_duration_seconds": int(duration) if duration else None,
                "last_sync_source": "supabase",  # Mark that Supabase is the source
            }
            
            if transcript_id:
                payload["transcript_id"] = transcript_id
                
            if contact_id:
                payload["contact_id"] = contact_id
            
            if existing:
                # Update existing journal
                journal_id = existing['id']
                # Merge with existing data if needed (don't overwrite null with null)
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
    
    # =========================================================================
    # CONTACT OPERATIONS - ENHANCED
    # =========================================================================
    
    def find_contact_by_email(self, email: str) -> Optional[Dict]:
        """
        Find a contact by email address.
        Checks both primary email and alternative_emails.
        
        Returns: The contact dict if found, None otherwise
        """
        if not email:
            return None
        
        try:
            email_lower = email.lower().strip()
            
            # Strategy 1: Check primary email
            result = self.client.table("contacts").select("*").ilike(
                "email", email_lower
            ).is_("deleted_at", "null").execute()
            
            if result.data:
                logger.info(f"Found contact by primary email: {email}")
                return result.data[0]
            
            # Strategy 2: Check alternative emails (if column exists)
            # Using contains for jsonb array
            result = self.client.table("contacts").select("*").contains(
                "alternative_emails", [email_lower]
            ).is_("deleted_at", "null").execute()
            
            if result.data:
                logger.info(f"Found contact by alternative email: {email}")
                return result.data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding contact by email '{email}': {e}")
            return None
            
    def link_past_interactions(self, contact_id: str, email: str) -> Dict:
        """
        Manually trigger retroactive linking for a contact.
        Useful if the database trigger fails or for maintenance.
        """
        try:
            logger.info(f"Triggering retroactive linking for {email} ({contact_id})")
            result = self.client.rpc('link_past_interactions', {
                'contact_uuid': contact_id,
                'contact_email': email
            }).execute()
            
            logger.info(f"Retroactive linking result: {result.data}")
            return result.data
        except Exception as e:
            logger.error(f"Error running retroactive linking: {e}")
            return {"status": "error", "message": str(e)}
    
    def find_contact_by_name_or_email(self, name: str = None, email: str = None) -> Tuple[Optional[Dict], List[Dict]]:
        """
        Find a contact by name and/or email with intelligent matching.
        
        Args:
            name: Full name or partial name
            email: Email address
        
        Returns:
            Tuple of (matched_contact, suggestions)
        """
        # Try email first (most reliable)
        if email:
            contact = self.find_contact_by_email(email)
            if contact:
                return contact, []
        
        # Fall back to name matching
        if name:
            return self.find_contact_by_name(name)
        
        return None, []
    
    def update_contact_interaction_stats(self, contact_id: str) -> None:
        """
        Update contact interaction statistics.
        This is typically called automatically by database triggers,
        but can be called manually if needed.
        """
        try:
            # Call the database function
            self.client.rpc('update_contact_interaction_stats', {
                'contact_uuid': contact_id
            }).execute()
            logger.info(f"Updated interaction stats for contact {contact_id}")
        except Exception as e:
            logger.error(f"Error updating contact stats: {e}")
    
    def get_contact_interactions(self, contact_id: str, limit: int = 50) -> List[Dict]:
        """
        Get all interactions for a specific contact.
        Uses the interaction_log view.
        
        Returns: List of interactions ordered by date (newest first)
        """
        try:
            result = self.client.table("interaction_log").select("*").eq(
                "contact_id", contact_id
            ).limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error fetching interactions for contact {contact_id}: {e}")
            return []
    
    # =========================================================================
    # EMAILS
    # =========================================================================
    
    def create_email(
        self,
        subject: str,
        from_email: str,
        to_emails: List[str],
        body_text: str = None,
        body_html: str = None,
        from_name: str = None,
        cc_emails: List[str] = None,
        direction: str = "inbound",
        sent_at: str = None,
        received_at: str = None,
        message_id: str = None,
        thread_id: str = None,
        contact_id: str = None,
        contact_name: str = None,
        meeting_id: str = None,
        category: str = None,
        tags: List[str] = None,
        has_attachments: bool = False,
        attachment_names: List[str] = None,
        source_provider: str = None,
        raw_data: Dict = None
    ) -> Tuple[str, str]:
        """
        Create an email record in Supabase.
        
        Args:
            subject: Email subject
            from_email: Sender email address
            to_emails: List of recipient emails
            body_text: Plain text body
            body_html: HTML body (optional)
            from_name: Sender name
            cc_emails: CC recipients
            direction: 'inbound' or 'outbound'
            sent_at: ISO timestamp when sent
            received_at: ISO timestamp when received
            message_id: Unique message ID from email provider
            thread_id: Thread/conversation ID
            contact_id: Linked contact ID
            contact_name: Contact name (before linking)
            meeting_id: Related meeting ID
            category: Email category ('work', 'personal', etc.)
            tags: List of tags
            has_attachments: Whether email has attachments
            attachment_names: List of attachment filenames
            source_provider: Email provider ('gmail', 'outlook', etc.)
            raw_data: Raw email data
        
        Returns:
            Tuple of (email_id, "supabase://emails/{id}")
        """
        try:
            logger.info(f"Creating email: {subject} from {from_email}")
            
            # Auto-link to contact if not provided
            if not contact_id and from_email and direction == "inbound":
                contact = self.find_contact_by_email(from_email)
                if contact:
                    contact_id = contact.get('id')
                    logger.info(f"Auto-linked email to contact: {from_email} -> {contact_id}")
            elif not contact_id and to_emails and direction == "outbound":
                # For outbound, try to match primary recipient
                contact = self.find_contact_by_email(to_emails[0])
                if contact:
                    contact_id = contact.get('id')
                    logger.info(f"Auto-linked email to contact: {to_emails[0]} -> {contact_id}")
            
            # Generate snippet from body
            snippet = None
            if body_text:
                snippet = body_text[:200] + "..." if len(body_text) > 200 else body_text
            
            payload = {
                "subject": subject,
                "from_email": from_email,
                "to_emails": to_emails,
                "direction": direction,
            }
            
            # Add optional fields
            if body_text:
                payload["body_text"] = body_text
            if body_html:
                payload["body_html"] = body_html
            if snippet:
                payload["snippet"] = snippet
            if from_name:
                payload["from_name"] = from_name
            if cc_emails:
                payload["cc_emails"] = cc_emails
            if sent_at:
                payload["sent_at"] = sent_at
            if received_at:
                payload["received_at"] = received_at
            if message_id:
                payload["message_id"] = message_id
            if thread_id:
                payload["thread_id"] = thread_id
            if contact_id:
                payload["contact_id"] = contact_id
            if contact_name:
                payload["contact_name"] = contact_name
            if meeting_id:
                payload["meeting_id"] = meeting_id
            if category:
                payload["category"] = category
            if tags:
                payload["tags"] = tags
            if has_attachments:
                payload["has_attachments"] = has_attachments
                payload["attachment_count"] = len(attachment_names) if attachment_names else 0
            if attachment_names:
                payload["attachment_names"] = attachment_names
            if source_provider:
                payload["source_provider"] = source_provider
            if raw_data:
                payload["raw_data"] = raw_data
            
            result = self.client.table("emails").insert(payload).execute()
            email_id = result.data[0]["id"]
            email_url = f"supabase://emails/{email_id}"
            
            logger.info(f"Email created: {email_id}")
            return email_id, email_url
            
        except Exception as e:
            logger.error(f"Error creating email: {e}")
            raise
    
    def get_emails_by_contact(self, contact_id: str, limit: int = 50) -> List[Dict]:
        """
        Get all emails for a specific contact.
        
        Returns: List of emails ordered by date (newest first)
        """
        try:
            result = self.client.table("emails").select("*").eq(
                "contact_id", contact_id
            ).is_("deleted_at", "null").order(
                "sent_at", desc=True
            ).limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error fetching emails for contact {contact_id}: {e}")
            return []
    
    def get_emails_by_thread(self, thread_id: str) -> List[Dict]:
        """
        Get all emails in a conversation thread.
        
        Returns: List of emails ordered by date (oldest first)
        """
        try:
            result = self.client.table("emails").select("*").eq(
                "thread_id", thread_id
            ).is_("deleted_at", "null").order(
                "sent_at", desc=False
            ).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error fetching email thread {thread_id}: {e}")
            return []
    
    def link_email_to_meeting(self, email_id: str, meeting_id: str) -> None:
        """
        Link an email to a meeting.
        """
        try:
            self.client.table("emails").update({
                "meeting_id": meeting_id
            }).eq("id", email_id).execute()
            logger.info(f"Linked email {email_id} to meeting {meeting_id}")
        except Exception as e:
            logger.error(f"Error linking email to meeting: {e}")
            raise
    
    # =========================================================================
    # CALENDAR EVENTS
    # =========================================================================
    
    def create_calendar_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = None,
        location: str = None,
        organizer_email: str = None,
        organizer_name: str = None,
        attendees: List[Dict] = None,
        all_day: bool = False,
        status: str = "confirmed",
        contact_id: str = None,
        contact_name: str = None,
        meeting_id: str = None,
        email_id: str = None,
        event_type: str = None,
        tags: List[str] = None,
        meeting_url: str = None,
        is_recurring: bool = False,
        recurrence_rule: str = None,
        source_provider: str = None,
        source_event_id: str = None,
        raw_data: Dict = None
    ) -> Tuple[str, str]:
        """
        Create a calendar event record in Supabase.
        
        Args:
            title: Event title
            start_time: ISO timestamp for start
            end_time: ISO timestamp for end
            description: Event description
            location: Event location
            organizer_email: Organizer's email
            organizer_name: Organizer's name
            attendees: List of attendee dicts with {email, name, response_status}
            all_day: Whether it's an all-day event
            status: 'confirmed', 'tentative', or 'cancelled'
            contact_id: Linked contact ID
            contact_name: Contact name (before linking)
            meeting_id: Related meeting ID (if notes created)
            email_id: Related email ID (invitation)
            event_type: 'meeting', 'appointment', etc.
            tags: List of tags
            meeting_url: Video conference link
            is_recurring: Whether event repeats
            recurrence_rule: RRULE for recurrence
            source_provider: Calendar provider ('google_calendar', etc.)
            source_event_id: Original event ID from provider
            raw_data: Raw event data
        
        Returns:
            Tuple of (event_id, "supabase://calendar_events/{id}")
        """
        try:
            logger.info(f"Creating calendar event: {title} at {start_time}")
            
            # Auto-link to contact if not provided
            if not contact_id and organizer_email:
                contact = self.find_contact_by_email(organizer_email)
                if contact:
                    contact_id = contact.get('id')
                    logger.info(f"Auto-linked event to contact: {organizer_email} -> {contact_id}")
            
            payload = {
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "all_day": all_day,
                "status": status,
            }
            
            # Add optional fields
            if description:
                payload["description"] = description
            if location:
                payload["location"] = location
            if organizer_email:
                payload["organizer_email"] = organizer_email
            if organizer_name:
                payload["organizer_name"] = organizer_name
            if attendees:
                payload["attendees"] = attendees
            if contact_id:
                payload["contact_id"] = contact_id
            if contact_name:
                payload["contact_name"] = contact_name
            if meeting_id:
                payload["meeting_id"] = meeting_id
            if email_id:
                payload["email_id"] = email_id
            if event_type:
                payload["event_type"] = event_type
            if tags:
                payload["tags"] = tags
            if meeting_url:
                payload["meeting_url"] = meeting_url
            if is_recurring:
                payload["is_recurring"] = is_recurring
            if recurrence_rule:
                payload["recurrence_rule"] = recurrence_rule
            if source_provider:
                payload["source_provider"] = source_provider
            if source_event_id:
                payload["source_event_id"] = source_event_id
            if raw_data:
                payload["raw_data"] = raw_data
            
            result = self.client.table("calendar_events").insert(payload).execute()
            event_id = result.data[0]["id"]
            event_url = f"supabase://calendar_events/{event_id}"
            
            logger.info(f"Calendar event created: {event_id}")
            return event_id, event_url
            
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            raise
    
    def get_calendar_events_by_contact(self, contact_id: str, limit: int = 50) -> List[Dict]:
        """
        Get all calendar events for a specific contact.
        
        Returns: List of events ordered by date (newest first)
        """
        try:
            result = self.client.table("calendar_events").select("*").eq(
                "contact_id", contact_id
            ).order(
                "start_time", desc=True
            ).limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error fetching calendar events for contact {contact_id}: {e}")
            return []
    
    def get_upcoming_events(self, limit: int = 20) -> List[Dict]:
        """
        Get upcoming calendar events.
        
        Returns: List of future events ordered by date (soonest first)
        """
        try:
            from datetime import datetime
            now = datetime.utcnow().isoformat()
            
            result = self.client.table("calendar_events").select("*").gte(
                "start_time", now
            ).neq(
                "status", "cancelled"
            ).order(
                "start_time", desc=False
            ).limit(limit).execute()
            
            return result.data
        except Exception as e:
            logger.error(f"Error fetching upcoming events: {e}")
            return []
    
    def link_calendar_event_to_meeting(self, event_id: str, meeting_id: str) -> None:
        """
        Link a calendar event to a meeting record.
        """
        try:
            # Update calendar event
            self.client.table("calendar_events").update({
                "meeting_id": meeting_id
            }).eq("id", event_id).execute()
            
            # Also update meeting with calendar event reference
            self.client.table("meetings").update({
                "calendar_event_id": event_id
            }).eq("id", meeting_id).execute()
            
            logger.info(f"Linked calendar event {event_id} to meeting {meeting_id}")
        except Exception as e:
            logger.error(f"Error linking calendar event to meeting: {e}")
            raise
