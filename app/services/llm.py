"""LLM-powered transcript analysis for multi-database routing."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from anthropic import Anthropic, AsyncAnthropic

from app.core.config import settings
from app.features.analysis.prompts import build_multi_analysis_prompt

logger = logging.getLogger("Jarvis.Intelligence.LLM")


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
        key = api_key or settings.ANTHROPIC_API_KEY
        self.client = Anthropic(api_key=key)
        self.async_client = AsyncAnthropic(api_key=key)  # Async client for non-blocking calls

        primary_model = model or settings.CLAUDE_MODEL_PRIMARY
        fallback_models: List[str] = []
        for candidate in settings.CLAUDE_MODEL_OPTIONS:
            if candidate and candidate not in fallback_models and candidate != primary_model:
                fallback_models.append(candidate)

        self.model_primary = primary_model
        self.model_candidates = [primary_model] + fallback_models
        self.model = primary_model  # Backwards compatibility for older call sites

        logger.info(
            "Claude Multi-Database analyzer initialized with models: %s (async enabled)",
            ", ".join(self.model_candidates),
        )

    async def analyze_transcript_async(
        self,
        transcript: str,
        filename: str,
        recording_date: Optional[str] = None,
        existing_topics: Optional[List[Dict[str, str]]] = None,
        known_contacts: Optional[List[Dict[str, str]]] = None,
        person_context: Optional[Dict] = None,
        calendar_context: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        ASYNC version - Analyze transcript without blocking the event loop.
        Use this from FastAPI endpoints for non-blocking LLM calls.
        
        Args:
            known_contacts: List of contacts for smart name correction in transcripts
            person_context: Context about who the meeting is with (from Screenpipe bridge)
                - confirmed_person_name: Name from calendar or user confirmation
                - person_confirmed: Whether user explicitly confirmed this
                - contact_id: Linked contact ID if known
                - previous_meetings_summary: Brief summary of past interactions
            calendar_context: Recent calendar events to help identify who the meeting was with
                - Helps correct misheard names (e.g., "Hoy" -> "Hieu")
        """
        try:
            logger.info("Analyzing transcript ASYNC for multi-database routing (length: %d chars)", len(transcript))

            if not recording_date:
                recording_date = datetime.now().date().isoformat()

            transcript_stats = {
                "char_count": len(transcript),
                "word_count": len(transcript.split()),
            }

            prompt = self._build_multi_analysis_prompt(
                transcript=transcript,
                filename=filename,
                recording_date=recording_date,
                existing_topics=existing_topics or [],
                transcript_stats=transcript_stats,
                known_contacts=known_contacts,
                person_context=person_context,
                calendar_context=calendar_context,
            )

            last_error: Optional[Exception] = None

            for model_name in self.model_candidates:
                try:
                    result_text = await self._invoke_model_async(prompt, model_name)
                    analysis = json.loads(result_text)
                    analysis = self._ensure_analysis_schema(
                        analysis,
                        transcript=transcript,
                        filename=filename,
                        recording_date=recording_date,
                    )
                    analysis = self._process_due_dates(analysis, recording_date)
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
                        "Async analysis complete with model %s: category=%s, tasks=%s, crm_updates=%s",
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
                except Exception as exc:
                    logger.warning("Model %s failed: %s", model_name, exc)
                    last_error = exc

            if last_error:
                logger.error(
                    "All Claude models failed (async), falling back to default analysis: %s",
                    last_error,
                )
            return self._default_analysis(transcript, filename, recording_date)

        except Exception as exc:
            logger.error("Unexpected error in async transcript analysis: %s", exc, exc_info=True)
            return self._default_analysis(transcript, filename, recording_date or datetime.now().date().isoformat())

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

            # Calculate stats for adaptive output (longer transcripts get more detailed summaries)
            transcript_stats = {
                "char_count": len(transcript),
                "word_count": len(transcript.split()),
            }

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

    def _build_multi_analysis_prompt(
        self,
        transcript: str,
        filename: str,
        recording_date: str,
        existing_topics: List[Dict[str, str]],
        transcript_stats: Dict = None,
        known_contacts: List[Dict[str, str]] = None,
        person_context: Dict = None,
        calendar_context: List[Dict] = None,
    ) -> str:
        """Generate the instruction block sent to Claude using centralized prompts."""
        return build_multi_analysis_prompt(
            transcript=transcript,
            filename=filename,
            recording_date=recording_date,
            existing_topics=existing_topics,
            transcript_stats=transcript_stats,
            known_contacts=known_contacts,
            person_context=person_context,
            calendar_context=calendar_context,
        )

    def _invoke_model(self, prompt: str, model_name: str) -> str:
        """Send the prompt to Claude and return raw text output."""
        
        # Scale max_tokens based on prompt size
        # 16K tokens for very long transcripts (90+ min meetings)
        # But keep it short for quick notes to save cost and ensure concise output
        prompt_length = len(prompt)
        if prompt_length > 150000:
            max_tokens = 16000  # Very long transcript (90+ min) - need comprehensive output
        elif prompt_length > 100000:
            max_tokens = 12000  # Long transcript (60-90 min)
        elif prompt_length > 50000:
            max_tokens = 8000   # Medium transcript (30-60 min)
        elif prompt_length > 20000:
            max_tokens = 6000   # Shorter transcript (10-30 min)
        elif prompt_length > 5000:
            max_tokens = 4000   # Brief meeting/note
        else:
            max_tokens = 2000   # Very short note - keep response concise

        response = self.client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temperature for consistent JSON output
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

    async def _invoke_model_async(self, prompt: str, model_name: str) -> str:
        """
        ASYNC version - Send the prompt to Claude without blocking.
        Uses the async Anthropic client for non-blocking API calls.
        """
        # Scale max_tokens based on prompt size
        # 16K tokens for very long transcripts (90+ min meetings)
        # But keep it short for quick notes to save cost and ensure concise output
        prompt_length = len(prompt)
        if prompt_length > 150000:
            max_tokens = 16000  # Very long transcript (90+ min) - need comprehensive output
        elif prompt_length > 100000:
            max_tokens = 12000  # Long transcript (60-90 min)
        elif prompt_length > 50000:
            max_tokens = 8000   # Medium transcript (30-60 min)
        elif prompt_length > 20000:
            max_tokens = 6000   # Shorter transcript (10-30 min)
        elif prompt_length > 5000:
            max_tokens = 4000   # Brief meeting/note
        else:
            max_tokens = 2000   # Very short note - keep response concise

        response = await self.async_client.messages.create(
            model=model_name,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temperature for consistent JSON output
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
