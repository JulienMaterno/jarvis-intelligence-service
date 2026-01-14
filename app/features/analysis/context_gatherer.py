"""
Stage 1: Context Gatherer (Haiku - Fast & Cheap)

This module intelligently gathers relevant context from the database
before the main analysis. It uses a cheap/fast model (Haiku) to:

1. Extract entities from the transcript (names, companies, topics, projects)
2. Query the database for relevant context
3. Build a rich context package for Stage 2 (Sonnet)

The goal is to give Stage 2 ALL the context it needs to make smart decisions,
while keeping costs low by using a cheap model for entity extraction.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from anthropic import AsyncAnthropic

from app.core.config import settings

logger = logging.getLogger("Jarvis.Intelligence.ContextGatherer")

# Model for entity extraction (cheap/fast)
ENTITY_EXTRACTION_MODEL = "claude-haiku-4-5-20251001"

# Context window budget for Stage 2 (leave room for transcript + response)
# Sonnet has 200K context, we reserve 150K for context + transcript
MAX_CONTEXT_CHARS = 100_000  # ~25K tokens for context


class ContextGatherer:
    """
    Stage 1: Extract entities and gather rich context for transcript analysis.
    
    Uses Haiku (cheap model) to identify what context to fetch,
    then queries the database for relevant information.
    """
    
    def __init__(self, api_key: Optional[str] = None, db=None):
        key = api_key or settings.ANTHROPIC_API_KEY
        self.async_client = AsyncAnthropic(api_key=key)
        self.model = ENTITY_EXTRACTION_MODEL
        self.db = db
        logger.info("Context Gatherer initialized with model: %s", self.model)
    
    async def gather_context(
        self,
        transcript: str,
        filename: str,
        recording_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point: Extract entities and gather context.
        
        Returns a context package with:
        - extracted_entities: What the transcript mentions
        - contacts: Relevant contact records
        - meetings: Recent meetings with mentioned people
        - tasks: Related tasks (open tasks, tasks mentioning same topics)
        - reflections: Related reflections (by topic)
        - journals: Recent journals for continuity
        - calendar_events: Upcoming/recent events
        - emails: Recent relevant emails
        - applications: Job applications if mentioned
        
        All context is bounded to fit in Stage 2's context window.
        """
        recording_date = recording_date or datetime.now().date().isoformat()
        
        # Step 1: Use Haiku to extract entities from transcript
        logger.info("Stage 1: Extracting entities with Haiku...")
        entities = await self._extract_entities(transcript, filename)
        logger.info("Extracted entities: %s names, %s companies, %s topics",
                   len(entities.get("person_names", [])),
                   len(entities.get("companies", [])),
                   len(entities.get("topics", [])))
        
        # Step 2: Query database for relevant context
        logger.info("Stage 1: Fetching relevant context from database...")
        context = await self._fetch_context(entities, transcript, recording_date)
        
        # Step 3: Trim context to fit budget
        context = self._trim_context_to_budget(context)
        
        logger.info("Context gathered: %d chars total", self._count_context_chars(context))
        
        return {
            "extracted_entities": entities,
            **context
        }
    
    async def _extract_entities(self, transcript: str, filename: str) -> Dict[str, List[str]]:
        """
        Use Haiku to extract entities from the transcript.
        
        This is a quick/cheap operation to identify what to look up.
        """
        # For very short transcripts, skip Haiku and do simple regex
        if len(transcript.split()) < 50:
            return self._simple_entity_extraction(transcript)
        
        prompt = self._build_extraction_prompt(transcript, filename)
        
        try:
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.1,  # Very low temp for consistent extraction
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Clean markdown code blocks
            if result_text.startswith("```"):
                result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
                result_text = re.sub(r"\n?```$", "", result_text)
            
            entities = json.loads(result_text)
            return self._normalize_entities(entities)
            
        except Exception as e:
            logger.warning("Entity extraction failed, using simple extraction: %s", e)
            return self._simple_entity_extraction(transcript)
    
    def _build_extraction_prompt(self, transcript: str, filename: str) -> str:
        """Build prompt for entity extraction."""
        # Sample transcript for extraction (first 10K chars usually enough)
        transcript_sample = transcript[:10000]
        if len(transcript) > 10000:
            transcript_sample += f"\n... [truncated, {len(transcript)} total chars]"
        
        return f"""Extract key entities from this voice memo transcript.

**TRANSCRIPT** (from file "{filename}"):
{transcript_sample}

**EXTRACT:**
- Person names (people mentioned or met with)
- Company/organization names
- Project names
- Topics/themes discussed
- Locations mentioned
- Dates/times mentioned (other than "today")

**RETURN JSON ONLY:**
{{
  "person_names": ["Name 1", "Name 2"],
  "companies": ["Company 1"],
  "projects": ["Project Name"],
  "topics": ["Topic 1", "Topic 2"],
  "locations": ["Sydney", "Singapore"],
  "time_references": ["next week", "March"],
  "content_type": "meeting|journal|reflection|task_planning|voice_note",
  "primary_person": "Main person being discussed/met with, or null",
  "mood_indicators": ["positive", "stressed", "reflective"],
  "action_intent": ["schedule meeting", "follow up", "research"]
}}

Return ONLY the JSON, no explanation."""
    
    def _simple_entity_extraction(self, transcript: str) -> Dict[str, List[str]]:
        """
        Fallback: Simple regex-based entity extraction for short transcripts.
        """
        # Find capitalized words that might be names
        words = re.findall(r'\b[A-Z][a-z]+\b', transcript)
        potential_names = [w for w in words if len(w) > 2 and w.lower() not in 
                         {'the', 'this', 'that', 'what', 'when', 'where', 'which', 'who', 
                          'today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday',
                          'friday', 'saturday', 'sunday', 'january', 'february', 'march',
                          'april', 'may', 'june', 'july', 'august', 'september', 'october',
                          'november', 'december'}]
        
        return {
            "person_names": list(set(potential_names))[:10],
            "companies": [],
            "projects": [],
            "topics": [],
            "locations": [],
            "time_references": [],
            "content_type": "voice_note",
            "primary_person": None,
            "mood_indicators": [],
            "action_intent": []
        }
    
    def _normalize_entities(self, entities: Dict) -> Dict[str, List[str]]:
        """Ensure entity dict has all expected keys with list values."""
        defaults = {
            "person_names": [],
            "companies": [],
            "projects": [],
            "topics": [],
            "locations": [],
            "time_references": [],
            "content_type": "voice_note",
            "primary_person": None,
            "mood_indicators": [],
            "action_intent": []
        }
        
        for key, default in defaults.items():
            if key not in entities:
                entities[key] = default
            elif isinstance(default, list) and not isinstance(entities[key], list):
                entities[key] = [entities[key]] if entities[key] else []
        
        return entities
    
    async def _fetch_context(
        self, 
        entities: Dict[str, Any],
        transcript: str,
        recording_date: str
    ) -> Dict[str, Any]:
        """
        Fetch relevant context from all database tables.
        
        This is where the "smarts" come in - we fetch everything that could
        be relevant based on extracted entities.
        """
        if not self.db:
            logger.warning("No database connection, returning empty context")
            return {}
        
        context = {}
        
        # 1. CONTACTS - Fetch contacts matching mentioned names
        person_names = entities.get("person_names", [])
        primary_person = entities.get("primary_person")
        
        contacts = []
        contact_ids = set()
        
        # First, try to find primary person
        if primary_person:
            matched, suggestions = self.db.find_contact_by_name(primary_person)
            if matched:
                contacts.append(self._format_contact(matched, is_primary=True))
                contact_ids.add(matched["id"])
            elif suggestions:
                for s in suggestions[:3]:
                    contacts.append(self._format_contact(s, is_suggestion=True))
                    contact_ids.add(s["id"])
        
        # Then other mentioned names
        for name in person_names[:10]:  # Limit to top 10 names
            if name == primary_person:
                continue
            matched, suggestions = self.db.find_contact_by_name(name)
            if matched and matched["id"] not in contact_ids:
                contacts.append(self._format_contact(matched))
                contact_ids.add(matched["id"])
            elif suggestions:
                for s in suggestions[:2]:
                    if s["id"] not in contact_ids:
                        contacts.append(self._format_contact(s, is_suggestion=True))
                        contact_ids.add(s["id"])
        
        context["contacts"] = contacts[:15]  # Max 15 contacts
        
        # 2. RECENT MEETINGS - With the people we found
        meetings = []
        for contact_id in list(contact_ids)[:5]:  # Top 5 contacts
            try:
                contact_meetings = self.db.get_contact_interactions(contact_id, limit=3)
                for m in contact_meetings:
                    meetings.append(self._format_meeting(m))
            except Exception as e:
                logger.debug(f"Could not fetch meetings for contact: {e}")
        
        context["recent_meetings"] = meetings[:10]  # Max 10 meetings
        
        # 3. REFLECTIONS - By topic
        topics = entities.get("topics", [])
        reflections = []
        
        # Get existing reflection topics for smart routing
        try:
            existing_reflections = self.db.get_existing_reflection_topics(limit=30)
            context["existing_reflections"] = existing_reflections
        except Exception as e:
            logger.debug(f"Could not fetch existing reflections: {e}")
            context["existing_reflections"] = []
        
        # Search for related reflections
        for topic in topics[:5]:
            try:
                # Use search if available
                results = self.db.search_reflections_by_topic(topic, limit=2)
                for r in results:
                    reflections.append(self._format_reflection(r))
            except Exception as e:
                logger.debug(f"Could not search reflections for topic '{topic}': {e}")
        
        context["related_reflections"] = reflections[:8]
        
        # 4. OPEN TASKS - For context on what's already tracked
        try:
            open_tasks = self._get_open_tasks(limit=20)
            context["open_tasks"] = open_tasks
        except Exception as e:
            logger.debug(f"Could not fetch open tasks: {e}")
            context["open_tasks"] = []
        
        # 5. RECENT JOURNALS - For continuity
        try:
            recent_journals = self._get_recent_journals(days=7, limit=3)
            context["recent_journals"] = recent_journals
        except Exception as e:
            logger.debug(f"Could not fetch recent journals: {e}")
            context["recent_journals"] = []
        
        # 6. CALENDAR EVENTS - Upcoming and recent
        try:
            calendar_events = self.db.get_recent_calendar_events(hours_back=24)
            context["calendar_events"] = [self._format_calendar_event(e) for e in calendar_events[:10]]
        except Exception as e:
            logger.debug(f"Could not fetch calendar events: {e}")
            context["calendar_events"] = []
        
        # 7. APPLICATIONS - If job search mentioned
        if any(kw in transcript.lower() for kw in ['job', 'application', 'interview', 'role', 'position', 'applied']):
            try:
                applications = self._get_relevant_applications(limit=10)
                context["applications"] = applications
            except Exception as e:
                logger.debug(f"Could not fetch applications: {e}")
                context["applications"] = []
        
        # 8. EMAILS - Recent from/to mentioned contacts
        emails = []
        for contact_id in list(contact_ids)[:3]:
            try:
                contact_emails = self.db.get_emails_by_contact(contact_id, limit=3)
                for e in contact_emails:
                    emails.append(self._format_email(e))
            except Exception as e:
                logger.debug(f"Could not fetch emails for contact: {e}")
        
        context["relevant_emails"] = emails[:10]
        
        return context
    
    def _format_contact(self, contact: Dict, is_primary: bool = False, is_suggestion: bool = False) -> Dict:
        """Format contact for context, keeping essential fields."""
        return {
            "id": contact.get("id"),
            "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
            "company": contact.get("company"),
            "job_title": contact.get("job_title"),
            "location": contact.get("location"),
            "notes": contact.get("notes", "")[:200] if contact.get("notes") else None,
            "is_primary_match": is_primary,
            "is_suggestion": is_suggestion,
        }
    
    def _format_meeting(self, meeting: Dict) -> Dict:
        """Format meeting for context."""
        return {
            "id": meeting.get("id"),
            "title": meeting.get("title"),
            "date": meeting.get("date"),
            "summary": meeting.get("summary", "")[:300] if meeting.get("summary") else None,
            "topics": meeting.get("topics_discussed", [])[:5],
            "contact_name": meeting.get("contact_name"),
        }
    
    def _format_reflection(self, reflection: Dict) -> Dict:
        """Format reflection for context."""
        return {
            "id": reflection.get("id"),
            "title": reflection.get("title"),
            "topic_key": reflection.get("topic_key"),
            "tags": reflection.get("tags", [])[:5],
            "date": reflection.get("date"),
            "content_preview": reflection.get("content", "")[:200] if reflection.get("content") else None,
        }
    
    def _format_calendar_event(self, event: Dict) -> Dict:
        """Format calendar event for context."""
        return {
            "summary": event.get("summary"),
            "start_time": event.get("start_time"),
            "attendees": event.get("attendee_names", [])[:5],
        }
    
    def _format_email(self, email: Dict) -> Dict:
        """Format email for context."""
        return {
            "subject": email.get("subject"),
            "sender": email.get("sender"),
            "date": email.get("date"),
            "snippet": email.get("snippet", "")[:150] if email.get("snippet") else None,
        }
    
    def _get_open_tasks(self, limit: int = 20) -> List[Dict]:
        """Fetch open tasks from database."""
        try:
            result = self.db.client.table("tasks").select(
                "id, title, description, due_date, priority, project"
            ).neq(
                "status", "Done"
            ).is_(
                "deleted_at", "null"
            ).order(
                "created_at", desc=True
            ).limit(limit).execute()
            
            return [{
                "id": t["id"],
                "title": t["title"],
                "due_date": t.get("due_date"),
                "priority": t.get("priority"),
                "project": t.get("project"),
            } for t in result.data or []]
        except Exception as e:
            logger.error(f"Error fetching open tasks: {e}")
            return []
    
    def _get_recent_journals(self, days: int = 7, limit: int = 3) -> List[Dict]:
        """Fetch recent journals for continuity."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
            
            result = self.db.client.table("journals").select(
                "id, date, title, mood, energy, summary, tomorrow_focus"
            ).gte(
                "date", cutoff
            ).order(
                "date", desc=True
            ).limit(limit).execute()
            
            return [{
                "date": j["date"],
                "title": j.get("title"),
                "mood": j.get("mood"),
                "summary": j.get("summary", "")[:200] if j.get("summary") else None,
                "tomorrow_focus": j.get("tomorrow_focus", [])[:5],
            } for j in result.data or []]
        except Exception as e:
            logger.error(f"Error fetching recent journals: {e}")
            return []
    
    def _get_relevant_applications(self, limit: int = 10) -> List[Dict]:
        """Fetch relevant job applications."""
        try:
            result = self.db.client.table("applications").select(
                "id, name, company, status, stage, position"
            ).not_.in_(
                "status", ["Rejected", "Withdrawn", "Closed"]
            ).order(
                "updated_at", desc=True
            ).limit(limit).execute()
            
            return [{
                "name": a["name"],
                "company": a.get("company"),
                "status": a.get("status"),
                "stage": a.get("stage"),
                "position": a.get("position"),
            } for a in result.data or []]
        except Exception as e:
            logger.error(f"Error fetching applications: {e}")
            return []
    
    def _trim_context_to_budget(self, context: Dict) -> Dict:
        """
        Trim context to fit within the context window budget.
        
        Prioritizes:
        1. Contacts (essential for name correction)
        2. Recent meetings with contacts
        3. Existing reflections (for routing)
        4. Open tasks
        5. Recent journals
        6. Calendar events
        7. Everything else
        """
        total_chars = self._count_context_chars(context)
        
        if total_chars <= MAX_CONTEXT_CHARS:
            return context
        
        logger.info(f"Context too large ({total_chars} chars), trimming to {MAX_CONTEXT_CHARS}...")
        
        # Trim in reverse priority order
        trim_order = [
            "relevant_emails",
            "applications", 
            "related_reflections",
            "calendar_events",
            "recent_journals",
            "open_tasks",
            "recent_meetings",
        ]
        
        for key in trim_order:
            if key in context and context[key]:
                # Halve the list
                context[key] = context[key][:len(context[key])//2]
                
                total_chars = self._count_context_chars(context)
                if total_chars <= MAX_CONTEXT_CHARS:
                    logger.info(f"Context trimmed to {total_chars} chars by reducing {key}")
                    return context
        
        return context
    
    def _count_context_chars(self, context: Dict) -> int:
        """Count total characters in context dict."""
        return len(json.dumps(context, default=str))


async def gather_context_for_transcript(
    transcript: str,
    filename: str,
    db,
    recording_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to gather context for a transcript.
    
    This is the main entry point for Stage 1 processing.
    """
    gatherer = ContextGatherer(db=db)
    return await gatherer.gather_context(transcript, filename, recording_date)
