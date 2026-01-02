"""LLM-powered transcript analysis for multi-database routing."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from anthropic import Anthropic

from app.core.config import settings
from app.features.analysis.prompts import build_multi_analysis_prompt

logger = logging.getLogger("Jarvis.Intelligence.LLM")

# Token limits (approximate - Claude uses ~4 chars per token for English)
MAX_TRANSCRIPT_CHARS = 180000  # ~45K tokens for transcript, leaving room for prompt/response
CHUNK_SIZE = 60000  # ~15K tokens per chunk for very long transcripts


class ClaudeMultiAnalyzer:
    """Analyze transcripts for meetings, journals, reflections, tasks, and CRM."""

    VALID_PRIMARY_CATEGORIES = {
        "meeting",
        "reflection",
        "journal",
        "task_planning",
        "other",
    }

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.client = Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)

        primary_model = model or settings.CLAUDE_MODEL_PRIMARY
        fallback_models: List[str] = []
        for candidate in settings.CLAUDE_MODEL_OPTIONS:
            if candidate and candidate not in fallback_models and candidate != primary_model:
                fallback_models.append(candidate)

        self.model_primary = primary_model
        self.model_candidates = [primary_model] + fallback_models
        self.model = primary_model  # Backwards compatibility for older call sites

        logger.info(
            "Claude Multi-Database analyzer initialized with models: %s",
            ", ".join(self.model_candidates),
        )

    def analyze_transcript(
        self,
        transcript: str,
        filename: str,
        recording_date: Optional[str] = None,
        existing_topics: Optional[List[Dict[str, str]]] = None,
    ) -> Dict:
        """Analyze transcript text and return structured routing guidance."""

        try:
            logger.info("Analyzing transcript for multi-database routing (length: %d chars)", len(transcript))

            if not recording_date:
                recording_date = datetime.now().date().isoformat()

            # Calculate stats for adaptive output
            transcript_stats = {
                "char_count": len(transcript),
                "word_count": len(transcript.split()),
                "is_long": len(transcript) > 50000,
                "is_very_long": len(transcript) > 100000,
            }
            
            # Handle very long transcripts
            if len(transcript) > MAX_TRANSCRIPT_CHARS:
                logger.warning(
                    "Transcript is very long (%d chars), truncating to %d chars",
                    len(transcript),
                    MAX_TRANSCRIPT_CHARS
                )
                # Smart truncation: keep beginning and end, summarize middle
                transcript = self._smart_truncate(transcript, MAX_TRANSCRIPT_CHARS)

            prompt = self._build_multi_analysis_prompt(
                transcript=transcript,
                filename=filename,
                recording_date=recording_date,
                existing_topics=existing_topics or [],
                transcript_stats=transcript_stats,
            )

            last_error: Optional[Exception] = None

            for model_name in self.model_candidates:
                try:
                    result_text = self._invoke_model(prompt, model_name)
                    analysis = json.loads(result_text)
                    analysis = self._ensure_analysis_schema(
                        analysis,
                        transcript=transcript,
                        filename=filename,
                        recording_date=recording_date,
                    )
                    analysis = self._process_due_dates(analysis, recording_date)
                    analysis = self._consolidate_meetings(analysis)  # NEW: Merge duplicate meetings
                    analysis = self._ensure_analysis_schema(
                        analysis,
                        transcript=transcript,
                        filename=filename,
                        recording_date=recording_date,
                    )

                    primary = analysis.get("primary_category", "other")
                    task_count = len(analysis.get("tasks", []))
                    crm_count = len(analysis.get("crm_updates", []))

                    logger.info(
                        "Analysis complete with model %s: category=%s, tasks=%s, crm_updates=%s",
                        model_name,
                        primary,
                        task_count,
                        crm_count,
                    )
                    return analysis

                except json.JSONDecodeError as exc:
                    snippet = result_text[:500] if "result_text" in locals() else "<empty>"
                    logger.error(
                        "Model %s returned unparsable JSON: %s | snippet=%s",
                        model_name,
                        exc,
                        snippet,
                    )
                    last_error = exc
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Model %s failed: %s", model_name, exc)
                    last_error = exc

            if last_error:
                logger.error(
                    "All Claude models failed, falling back to default analysis: %s",
                    last_error,
                )
            return self._default_analysis(transcript, filename, recording_date)

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Unexpected error analyzing transcript: %s", exc, exc_info=True)
            return self._default_analysis(transcript, filename, recording_date or datetime.now().date().isoformat())

    def _smart_truncate(self, transcript: str, max_chars: int) -> str:
        """
        Intelligently truncate very long transcripts while preserving key content.
        Keeps beginning (context setup) and end (conclusions/tasks) with middle summarized.
        """
        if len(transcript) <= max_chars:
            return transcript
        
        # Keep 40% from start, 40% from end, truncate middle
        keep_each = int(max_chars * 0.4)
        start_part = transcript[:keep_each]
        end_part = transcript[-keep_each:]
        
        middle_note = f"\n\n[... TRANSCRIPT TRUNCATED - {len(transcript) - (2 * keep_each)} characters omitted from middle for processing ...]\n\n"
        
        return start_part + middle_note + end_part

    def _consolidate_meetings(self, analysis: Dict) -> Dict:
        """
        Merge meetings with the same person into a single meeting entry.
        This handles cases where the LLM incorrectly splits one conversation into multiple meetings.
        """
        meetings = analysis.get("meetings", [])
        if len(meetings) <= 1:
            return analysis
        
        # Group by person_name (case-insensitive)
        person_meetings: Dict[str, List[Dict]] = {}
        for meeting in meetings:
            person = (meeting.get("person_name") or "Unknown").lower().strip()
            if person not in person_meetings:
                person_meetings[person] = []
            person_meetings[person].append(meeting)
        
        # Consolidate meetings for same person
        consolidated = []
        for person_key, person_meeting_list in person_meetings.items():
            if len(person_meeting_list) == 1:
                consolidated.append(person_meeting_list[0])
            else:
                # Merge multiple meetings into one
                merged = self._merge_meetings(person_meeting_list)
                consolidated.append(merged)
                logger.info(
                    "Consolidated %d meetings with '%s' into one",
                    len(person_meeting_list),
                    person_key
                )
        
        analysis["meetings"] = consolidated
        return analysis

    def _merge_meetings(self, meetings: List[Dict]) -> Dict:
        """Merge multiple meeting records into a single comprehensive one."""
        if not meetings:
            return {}
        
        base = meetings[0].copy()
        
        # Collect all topics from all meetings
        all_topics = []
        all_people = set()
        all_follow_ups = []
        summaries = []
        
        for m in meetings:
            # Collect topics
            topics = m.get("topics_discussed", [])
            if isinstance(topics, list):
                all_topics.extend(topics)
            
            # Collect people mentioned
            people = m.get("people_mentioned", [])
            if isinstance(people, list):
                all_people.update(people)
            
            # Collect follow-ups
            follow_ups = m.get("follow_up_conversation", [])
            if isinstance(follow_ups, list):
                all_follow_ups.extend(follow_ups)
            
            # Collect summaries
            summary = m.get("summary", "")
            if summary:
                summaries.append(summary)
        
        # Use first meeting's title and person_name (they should be same person)
        # Merge summaries
        if len(summaries) > 1:
            base["summary"] = " ".join(summaries)
        
        # Deduplicate topics by name
        seen_topics = set()
        unique_topics = []
        for topic in all_topics:
            topic_name = topic.get("topic", "") if isinstance(topic, dict) else str(topic)
            if topic_name.lower() not in seen_topics:
                seen_topics.add(topic_name.lower())
                unique_topics.append(topic)
        
        base["topics_discussed"] = unique_topics
        base["people_mentioned"] = list(all_people)
        base["follow_up_conversation"] = all_follow_ups
        
        return base

    def _build_multi_analysis_prompt(
        self,
        transcript: str,
        filename: str,
        recording_date: str,
        existing_topics: List[Dict[str, str]],
        transcript_stats: Dict = None,
    ) -> str:
        """Generate the instruction block sent to Claude using centralized prompts."""
        return build_multi_analysis_prompt(
            transcript=transcript,
            filename=filename,
            recording_date=recording_date,
            existing_topics=existing_topics,
            transcript_stats=transcript_stats,
        )

    def _invoke_model(self, prompt: str, model_name: str) -> str:
        """Send the prompt to Claude and return raw text output."""
        
        # Scale max_tokens based on prompt size (longer input needs longer output)
        prompt_length = len(prompt)
        if prompt_length > 100000:
            max_tokens = 8000  # Very long transcript needs comprehensive output
        elif prompt_length > 50000:
            max_tokens = 6000
        else:
            max_tokens = 4000

        response = self.client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )

        if not response.content:
            raise ValueError(f"Model {model_name} returned empty content")

        block = response.content[0]
        result_text = block.text if hasattr(block, "text") else str(block)
        result_text = result_text.strip()

        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)

        return result_text

    def _process_due_dates(self, analysis: Dict, recording_date: str) -> Dict:
        """Convert natural language due contexts to ISO dates."""

        try:
            base_date = datetime.fromisoformat(recording_date)
        except ValueError:
            base_date = datetime.now()

        tasks = analysis.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []

        for task in tasks:
            if not isinstance(task, dict):
                continue

            due_context = (task.get("due_context") or "").lower()
            if not due_context or task.get("due_date"):
                continue

            due_date: Optional[datetime] = None

            if "tomorrow" in due_context:
                due_date = base_date + timedelta(days=1)
            elif "today" in due_context:
                due_date = base_date
            elif "next week" in due_context or "in a week" in due_context:
                due_date = base_date + timedelta(weeks=1)
            elif "this week" in due_context:
                days_until_sunday = (6 - base_date.weekday()) % 7
                days_until_sunday = days_until_sunday or 7
                due_date = base_date + timedelta(days=days_until_sunday)
            elif "next month" in due_context:
                due_date = base_date + timedelta(days=30)
            else:
                match = re.search(r"(\d+)\s*day", due_context)
                if match:
                    days = int(match.group(1))
                    due_date = base_date + timedelta(days=days)

            if due_date:
                task["due_date"] = due_date.date().isoformat()

        analysis["tasks"] = tasks
        return analysis

    def _ensure_analysis_schema(
        self,
        analysis: Optional[Dict],
        transcript: str,
        filename: str,
        recording_date: str,
    ) -> Dict:
        """Ensure required keys exist and primary category aligns with content."""

        analysis = analysis or {}

        defaults = {
            "meetings": [],
            "journals": [],
            "reflections": [],
            "tasks": [],
            "crm_updates": [],
        }

        for key, default in defaults.items():
            value = analysis.get(key)
            if not isinstance(value, list):
                analysis[key] = default.copy()

        for journal in analysis.get("journals", []):
            if not isinstance(journal, dict):
                continue
            journal.setdefault("sections", [])
            journal.setdefault("tomorrow_focus", [])
            journal.setdefault("key_events", [])
            journal.setdefault("accomplishments", [])
            journal.setdefault("challenges", [])
            journal.setdefault("gratitude", [])
            journal.setdefault("sports", [])

        for reflection in analysis.get("reflections", []):
            if not isinstance(reflection, dict):
                continue
            reflection.setdefault("sections", [])
            reflection.setdefault("tags", [])

        primary = analysis.get("primary_category") or "other"
        if primary not in self.VALID_PRIMARY_CATEGORIES:
            if analysis["journals"]:
                primary = "journal"
            elif analysis["meetings"]:
                primary = "meeting"
            elif analysis["reflections"]:
                primary = "reflection"
            elif analysis["tasks"]:
                primary = "task_planning"
            else:
                primary = "other"

        analysis["primary_category"] = primary
        return analysis

    def _default_analysis(self, transcript: str, filename: str, recording_date: str) -> Dict:
        """Return a safe fallback structure when Claude fails."""

        logger.warning("Using fallback analysis due to Claude API failure")

        title_text = transcript[:200].strip()
        if "." in title_text:
            title_text = title_text.split(".")[0]
        default_title = (
            title_text[:60]
            or filename.replace(".mp3", "").replace(".m4a", "").replace("_", " ")[:60]
        )

        summary = (
            "WARNING: Automatic analysis failed. Please review and categorize this entry manually."
            f"\n\nAudio file: {filename}\nLength: {len(transcript)} characters"
        )

        return {
            "primary_category": "reflection",
            "meetings": [],
            "journals": [],
            "reflections": [
                {
                    "title": default_title,
                    "date": recording_date,
                    "location": None,
                    "tags": ["failed-analysis"],
                    "sections": [
                        {
                            "heading": "Raw Transcript",
                            "content": transcript[:2000] + "..." if len(transcript) > 2000 else transcript,
                        }
                    ],
                    "content": summary,
                }
            ],
            "tasks": [],
            "crm_updates": [],
        }
