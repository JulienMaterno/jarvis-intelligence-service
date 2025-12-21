"""LLM-powered transcript analysis for multi-database routing."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from anthropic import Anthropic

from app.core.config import settings

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
            logger.info("Analyzing transcript for multi-database routing")

            if not recording_date:
                recording_date = datetime.now().date().isoformat()

            prompt = self._build_multi_analysis_prompt(
                transcript=transcript,
                filename=filename,
                recording_date=recording_date,
                existing_topics=existing_topics or [],
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
    ) -> str:
        """Generate the instruction block sent to Claude."""

        if existing_topics:
            topics_lines = "\n".join(
                [
                    f"  - {topic.get('topic_key', 'unknown')}: \"{topic.get('title', '').strip()}\""
                    for topic in existing_topics[:20]
                ]
            )
            topics_context = f"""
**EXISTING REFLECTION TOPICS (from database):**
These are ongoing topics I've already been building. Consider whether this recording fits into one of them:
{topics_lines}

**TOPIC ROUTING RULES:**
- If this recording clearly relates to an existing topic -> use that topic_key (content will be APPENDED)
- If I explicitly say "new topic", "start fresh", "separate reflection" -> create new topic_key
- If the content is genuinely different from all existing topics -> create new topic_key  
- If unsure and content is substantial -> prefer creating new topic (better to have too many than miss-merge)
"""
        else:
            topics_context = """
**NOTE:** No existing reflection topics in database yet. Create new topic_keys as needed.
"""

        return f"""You are analyzing an audio transcript recorded by Aaron. Extract information from Aaron's perspective (first person).

**ABOUT AARON (for context):**
Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup developing photobioreactor technology for algae and cyanobacteria cultivation. He holds two master's degrees from Germany and Tsinghua University in China, and previously worked in consulting before moving into the startup world.

His core interests span climate tech, biotech, agritech, foodtech, and longevity. He has a strong technical background bridging hardware and software - comfortable with embedded systems (Arduino, ESP32), automation tools like Python, and building custom infrastructure. He prefers self-hosted and open-source tools over subscription services.

Aaron is systematic about relationship management, maintaining a comprehensive Notion CRM for professional and personal contacts. He's currently preparing to relocate to Singapore and Southeast Asia to explore new opportunities in the startup ecosystem there.
{topics_context}
**TRANSCRIPT CONTEXT:**
- Filename: {filename}
- Recording Date: {recording_date}
- Speaker: Aaron (the transcript is from Aaron's perspective)

**TRANSCRIPT:**
{transcript}

---

**YOUR TASK:**
Analyze this transcript from Aaron's perspective and extract structured information for routing to 5 different databases:
1. **Meetings Database** - For conversations with other people
2. **Reflections Database** - For personal thoughts, ideas, learnings (NOT daily journals)
3. **Journals Database** - For DAILY journal entries (evening reflections on the day, daily planning, what happened today)
4. **Tasks Database** - For TRUE action items that require active effort
5. **CRM Database** - For updating contact information ONLY about the person I met with (not everyone mentioned!)

**IMPORTANT DISTINCTIONS:**
- TASKS vs NON-TASKS: "Fly to Bali" is NOT a task (it's a plan that happens anyway). "Need to change my Medicare" IS a task (requires active effort). Only extract things that require me to take action.
- CRM: Only create CRM update for the PRIMARY person I'm meeting/talking with, NOT every person mentioned in conversation.
- JOURNAL vs REFLECTION: A JOURNAL is a daily entry (talks about "today", "this morning", "tonight", mentions the day's events). A REFLECTION is a deeper thought piece on a specific topic that's not tied to daily events.

**OUTPUT FORMAT:**
Return ONLY valid JSON (no markdown, no code blocks) with this exact structure:

{{
  "primary_category": "meeting|reflection|journal|task_planning|other",
  
  "meetings": [
    {{
      "title": "Brief descriptive title (max 60 chars)",
      "date": "{recording_date}",
      "location": "Location if mentioned, otherwise null",
      "person_name": "Name of the person I met with",
      "summary": "Comprehensive 4-6 sentence summary of what we discussed, key outcomes, and overall context.",
      "topics_discussed": [
        {{
          "topic": "Main topic name",
          "details": ["Specific point 1", "Specific point 2", "Specific point 3"]
        }},
        {{
          "topic": "Another topic",
          "details": ["Detail about this topic", "Another detail"]
        }}
      ],
      "people_mentioned": ["Name 1", "Name 2"],
      "follow_up_conversation": [
        {{
          "topic": "Something to bring up next time",
          "context": "Why it matters - e.g., their vacation to Japan in March",
          "date_if_known": "YYYY-MM-DD or null"
        }}
      ]
    }}
  ],
  
  "journals": [
    {{
      "date": "{recording_date}",
      "summary": "Brief 2-3 sentence summary of the day",
      "mood": "Great|Good|Okay|Tired|Stressed or null if not clear",
      "effort": "High|Medium|Low or null if not mentioned",
      "sports": ["Running", "Gym", "Yoga", etc] or empty array,
      "key_events": ["Event 1 that happened today", "Event 2"],
      "accomplishments": ["What I achieved today"],
      "challenges": ["Difficulties faced"],
      "gratitude": ["Things I'm grateful for"],
      "tomorrow_focus": ["What I plan to focus on tomorrow"],
      "sections": [
        {{
          "heading": "Morning",
          "content": "What happened in the morning..."
        }},
        {{
          "heading": "Main Activities",
          "content": "Key things I did..."
        }},
        {{
          "heading": "Evening Thoughts",
          "content": "Reflections on the day..."
        }}
      ]
    }}
  ],
  
  "reflections": [
    {{
      "title": "Brief reflection title (max 60 chars)",
      "date": "{recording_date}",
      "topic_key": "project-jarvis|exploring-out-loud-2|career-thoughts|etc (lowercase, hyphenated identifier for recurring topics, or null if one-off)",
      "tags": ["tag1", "tag2"],
      "content": "COMPREHENSIVE markdown content capturing 70-90% of the transcript's substance. Include: key points, nuances, examples mentioned, and context. Use headers (##), bullet points, and quotes where appropriate. Longer transcripts = longer content. Aim for thoroughness over brevity - this is a knowledge repository.",
      "sections": [
        {{
          "heading": "Main Insight or Theme",
          "content": "Detailed, thorough content for this section - capture the full context and reasoning, not just bullet points"
        }},
        {{
          "heading": "Key Points & Details",
          "content": "All important details, examples, and specifics mentioned"
        }},
        {{
          "heading": "Implications & Next Steps",
          "content": "What this means going forward, connections to other topics"
        }}
      ]
    }}
  ],
  
  "tasks": [
    {{
      "title": "Task title (concise, max 60 chars)",
      "description": "Additional context or details",
      "due_date": "YYYY-MM-DD or null if not mentioned",
      "due_context": "natural language like 'tomorrow', 'next week' or null"
    }}
  ],
  
  "crm_updates": [
    {{
      "person_name": "Full name of person I MET WITH (not others mentioned!)",
      "updates": {{
        "company": "Company name or null",
        "position": "Job title or null",
        "location": "City/country or null",
        "personal_notes": "Memorable personal details: family, hobbies, upcoming events"
      }}
    }}
  ]
}}

**CRITICAL RULES:**

1. **Primary Category:**
   - "meeting" if discussing conversation(s) with other people
   - "journal" if talking about the day (today's events, evening recap, daily planning, what happened today/tomorrow)
   - "reflection" if personal thoughts, learnings, ideas on a SPECIFIC TOPIC (not daily events)
   - "task_planning" if primarily about organizing tasks
   - "other" if none of above

2. **Meetings Array:**
   - Create SEPARATE meeting objects for each distinct conversation
   - "topics_discussed": Break down ALL topics into separate objects with topic name and specific bullet points. Each topic should have 2-5 detail bullets capturing what was said.
   - "people_mentioned": List everyone mentioned in the conversation (for reference, NOT for CRM)
   - "follow_up_conversation": Things I should bring up next time I see this person - their upcoming vacation, stressful exam, new job, etc. Include dates when known. This helps me show I remember and care.
   - "summary": Write a thorough 4-6 sentence summary

3. **Journals Array (DAILY ENTRIES):**
   - Use for daily journals: evening recaps, morning planning, "what happened today"
   - Keywords that indicate journal: "today", "this morning", "tonight", "this evening", "tomorrow", "woke up", "journal", "journaling"
   - If filename contains "Journal" or "Journaling", FORCE this category.
   - If the transcript is primarily a daily recap, ALWAYS create a journal object (even if there are reflective insights too)
   - Extract mood/effort/sports ONLY if explicitly mentioned, otherwise null/empty
   - Structure into sections: Morning, Main Activities, Evening Thoughts, etc.
   - Extract tasks mentioned for tomorrow into "tomorrow_focus"
   - One journal entry per recording (tied to the date)
   - You CAN ALSO create a reflection if there is a longer-term theme, but never skip the journal when it's a daily recap

4. **Reflections Array (SMART TOPIC ROUTING):**
   - Only 1-2 tags per reflection (keep it focused)
   - "content": COMPREHENSIVE markdown capturing 70-90% of the transcript substance. This is a knowledge repository - be THOROUGH, not brief. Longer transcript = longer content.
   - "sections": Structure into 3-5 detailed sections. Each section should have substantial content, not just bullet points.
   - Include specific examples, quotes, nuances, and context from the transcript
   - Make it scannable BUT complete - someone reading should get the full picture without listening to the audio
   - Use for TOPIC-BASED reflections, NOT daily journals

   **MULTIPLE REFLECTIONS (IMPORTANT):**
   - If the recording contains content for MULTIPLE distinct topics, create MULTIPLE reflection objects
   - Example: If I say "some thoughts for the newsletter... also about Project Jarvis..." -> create TWO reflections
   - Each with its own topic_key, title, and content
   - Don't merge unrelated topics into one reflection

   **"topic_key" DECISION LOGIC (CRITICAL):**
   - Look at the EXISTING TOPICS list above first!
   - If recording content fits an existing topic -> USE THAT EXACT topic_key (will append)
   - If I say "for the newsletter", "about project X", "continuing my thoughts on Y" -> match to existing or create consistent key
   - If I say "new topic", "fresh reflection", "separate thought", "create a new reflection about X" -> create NEW topic_key
   - If content is genuinely unrelated to all existing topics -> create NEW topic_key
   - Format: lowercase, hyphenated (e.g., "project-jarvis", "career-transition", "startup-ideas")
   - When in doubt about merging: prefer creating new topic (can be merged later, but splitting is harder)

5. **Tasks Array - BE SELECTIVE:**
    - ONLY extract TRUE tasks that require active effort from me
    - GOOD tasks: "Need to call the bank", "Should email John the proposal", "Have to renew passport", "Follow up with Sarah"
    - NOT tasks: "Flying to Bali next month", "Meeting with John on Tuesday", "Birthday party on Saturday" (these are events/plans, not action items)
   - Ask yourself: "Does this require me to actively DO something, or will it just happen?"

6. **CRM Updates - ONE PERSON ONLY:**
   - ONLY create CRM entry for the person I'm MEETING WITH
   - Do NOT create entries for people merely mentioned in conversation
   - If I meet with John and we discuss Sarah and Mike, only John gets a CRM update
   - "personal_notes": Things to remember - their family situation, hobbies, upcoming travel, stressful situations, preferences
   - Skip CRM entirely if it's a reflection, journal, or no clear meeting person

7. **Follow-up Conversation Section (IMPORTANT):**
   - Capture things I should ask about next time: "How was Japan?", "How did the exam go?", "Did you get the promotion?"
   - Include context so I remember why I'm asking
   - Add dates if mentioned (vacation dates, exam dates, etc.)

7. **General:**
   - Be precise and factual
   - Don't invent information not in the transcript
   - Always populate every top-level array (use empty arrays if nothing applies)
   - Return ONLY the JSON object

Now analyze the transcript and return the JSON:"""

    def _invoke_model(self, prompt: str, model_name: str) -> str:
        """Send the prompt to Claude and return raw text output."""

        response = self.client.messages.create(
            model=model_name,
            max_tokens=4000,
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
