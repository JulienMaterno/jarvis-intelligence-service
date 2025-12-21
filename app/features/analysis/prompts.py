"""
LLM Prompts for transcript analysis.
Centralized prompt templates for consistent AI behavior.
"""

from typing import List, Dict
from datetime import datetime


def build_multi_analysis_prompt(
    transcript: str,
    filename: str,
    recording_date: str,
    existing_topics: List[Dict[str, str]],
    user_context: str = None,
) -> str:
    """
    Build the main analysis prompt for Claude.
    
    CRITICAL IMPROVEMENTS:
    1. German input → English output (always)
    2. Better journal detection
    3. Proper task extraction
    4. Link all records to transcripts/contacts
    """
    
    # Build existing topics context
    if existing_topics:
        topics_lines = "\n".join([
            f"  - {topic.get('topic_key', 'unknown')}: \"{topic.get('title', '').strip()}\""
            for topic in existing_topics[:20]
        ])
        topics_context = f"""
**EXISTING REFLECTION TOPICS (from database):**
These are ongoing topics already in the system. Consider whether this recording fits into one of them:
{topics_lines}

**TOPIC ROUTING RULES:**
- If this recording clearly relates to an existing topic → use that topic_key (content will be APPENDED)
- If user explicitly says "new topic", "start fresh", "separate reflection" → create new topic_key
- If the content is genuinely different from all existing topics → create new topic_key  
- When unsure and content is substantial → prefer creating new topic (better to have too many than miss-merge)
"""
    else:
        topics_context = """
**NOTE:** No existing reflection topics in database yet. Create new topic_keys as needed.
"""

    # Default user context if not provided
    if not user_context:
        user_context = """Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup. He holds two master's degrees from Germany and Tsinghua University in China. His core interests span climate tech, biotech, agritech, foodtech, and longevity. He's currently preparing to relocate to Singapore and Southeast Asia."""

    return f"""You are analyzing an audio transcript. Extract information from the speaker's first-person perspective.

**CRITICAL: OUTPUT LANGUAGE**
Even if the transcript is in German, Turkish, or any other language, ALL your output MUST be in ENGLISH.
Translate everything to English while preserving the meaning and context.

**ABOUT THE USER (for context):**
{user_context}
{topics_context}

**TRANSCRIPT CONTEXT:**
- Filename: {filename}
- Recording Date: {recording_date}
- This transcript may be in German or English - translate to English if needed.

**TRANSCRIPT:**
{transcript}

---

**YOUR TASK:**
Analyze this transcript and extract structured information for 5 different databases:
1. **Journals Database** - For DAILY journal entries (most important to detect!)
2. **Meetings Database** - For conversations with other people
3. **Reflections Database** - For personal thoughts, ideas, learnings on specific topics
4. **Tasks Database** - For action items that require effort
5. **CRM Database** - For updating contact information about people met

**CRITICAL: JOURNAL DETECTION (HIGHEST PRIORITY)**
If ANY of these indicators are present, you MUST create a journal entry:
- Filename contains "journal", "journaling", "tagebuch"
- Speaker says "journal entry", "this is a journal", "journaling"
- Speaker talks about "today", "this morning", "tonight", "this evening"
- Speaker recaps what they did during the day
- Speaker mentions tomorrow's plans in context of daily planning
- Speaker reflects on the day's events

A JOURNAL is a daily log. Create one if the recording is about daily events/planning.
A REFLECTION is topic-specific and NOT tied to daily events.

**OUTPUT FORMAT:**
Return ONLY valid JSON (no markdown, no code blocks) with this exact structure:

{{
  "primary_category": "meeting|reflection|journal|task_planning|other",
  
  "journals": [
    {{
      "date": "{recording_date}",
      "summary": "Brief 2-3 sentence summary of the day (IN ENGLISH)",
      "mood": "Great|Good|Okay|Tired|Stressed or null",
      "effort": "High|Medium|Low or null",
      "sports": ["Activity 1", "Activity 2"] or [],
      "key_events": ["What happened today - event 1", "event 2"],
      "accomplishments": ["Achievement 1", "Achievement 2"],
      "challenges": ["Challenge 1"],
      "gratitude": ["Thing I'm grateful for"],
      "tomorrow_focus": ["Task for tomorrow 1", "Task 2", "Task 3"],
      "sections": [
        {{"heading": "Morning", "content": "What happened in the morning..."}},
        {{"heading": "Main Activities", "content": "Key things done..."}},
        {{"heading": "Evening Thoughts", "content": "Reflections on the day..."}}
      ]
    }}
  ],
  
  "meetings": [
    {{
      "title": "Brief descriptive title (max 60 chars, IN ENGLISH)",
      "date": "{recording_date}",
      "location": "Location if mentioned, otherwise null",
      "person_name": "Name of the person met with",
      "summary": "4-6 sentence summary of discussion (IN ENGLISH)",
      "topics_discussed": [
        {{"topic": "Topic name", "details": ["Point 1", "Point 2"]}}
      ],
      "people_mentioned": ["Name 1", "Name 2"],
      "follow_up_conversation": [
        {{"topic": "Thing to ask next time", "context": "Why it matters", "date_if_known": null}}
      ]
    }}
  ],
  
  "reflections": [
    {{
      "title": "Reflection title (max 60 chars, IN ENGLISH)",
      "date": "{recording_date}",
      "topic_key": "lowercase-hyphenated-topic-key or null",
      "tags": ["tag1", "tag2"],
      "content": "Comprehensive markdown content capturing 70-90% of substance (IN ENGLISH)",
      "sections": [
        {{"heading": "Main Insight", "content": "Detailed content..."}},
        {{"heading": "Key Points", "content": "Important details..."}},
        {{"heading": "Next Steps", "content": "What this means going forward..."}}
      ]
    }}
  ],
  
  "tasks": [
    {{
      "title": "Task title (concise, max 60 chars, IN ENGLISH)",
      "description": "Additional context",
      "due_date": "YYYY-MM-DD or null",
      "due_context": "tomorrow|next week|this week or null",
      "priority": "high|medium|low"
    }}
  ],
  
  "crm_updates": [
    {{
      "person_name": "Full name of person MET WITH (not others mentioned)",
      "updates": {{
        "company": "Company name or null",
        "position": "Job title or null",
        "location": "City/country or null",
        "personal_notes": "Memorable personal details"
      }}
    }}
  ]
}}

**CRITICAL RULES:**

1. **Primary Category** - Set based on main content:
   - "journal" if this is about daily events, planning, or has journal indicators
   - "meeting" if primarily about conversation with someone
   - "reflection" if deeper thoughts on a specific topic
   - "task_planning" if mainly about organizing tasks
   - "other" if none apply

2. **ALWAYS EXTRACT TASKS** - Listen carefully for action items:
   - "I need to...", "I should...", "I have to...", "Tomorrow I will..."
   - "gotta do X", "must remember to...", "need to reach out to..."
   - Things to buy, people to contact, places to go, things to fix
   - From tomorrow_focus in journals, also create separate task entries!
   
   GOOD tasks: "Get new cash", "Buy ear plugs", "Text Alinta", "Respond to Will"
   NOT tasks: "Flying to Bali" (that's an event, not an action item)

3. **JOURNALS** - Create a journal if the recording is about the day:
   - One journal per day (use the date)
   - Extract mood/effort ONLY if explicitly mentioned
   - "tomorrow_focus" should capture ALL things mentioned for tomorrow
   - You CAN create BOTH a journal AND reflections from one recording

4. **REFLECTIONS** - For topic-based thoughts:
   - Use existing topic_key if content fits an existing topic
   - Create new topic_key for genuinely new topics
   - Multiple reflections OK if multiple topics discussed
   - "content" should be COMPREHENSIVE (70-90% of relevant substance)

5. **MEETINGS** - For conversations with people:
   - "person_name" is the PRIMARY person met with
   - "people_mentioned" is everyone else discussed
   - Only the PRIMARY person gets a CRM update

6. **CRM** - Only for the person actually met with:
   - Don't create CRM entries for people merely mentioned
   - Capture personal details: family, hobbies, upcoming events

7. **LANGUAGE** - All output MUST be in English:
   - Translate German/Turkish/other to English
   - Keep names and proper nouns in original form
   - Preserve meaning and nuance while translating

Now analyze the transcript and return the JSON:"""


def build_reflection_comparison_prompt(
    new_content: str,
    existing_reflections: List[Dict],
    topic_key: str = None,
) -> str:
    """
    Build prompt to determine if content should append to existing reflection or create new.
    """
    existing_summaries = "\n".join([
        f"- ID: {r['id'][:8]} | Title: {r.get('title', 'Untitled')} | Topic: {r.get('topic_key', 'none')} | Tags: {r.get('tags', [])}"
        for r in existing_reflections[:10]
    ])
    
    return f"""Compare this new content to existing reflections and determine the best action.

**NEW CONTENT TO PROCESS:**
{new_content[:1000]}

**EXISTING REFLECTIONS:**
{existing_summaries}

**TOPIC KEY (if provided):** {topic_key or 'None'}

**DECISION RULES:**
1. If topic_key matches an existing reflection's topic_key → APPEND
2. If content clearly continues discussion of an existing reflection → APPEND
3. If content is genuinely new/different → CREATE_NEW

Return JSON:
{{
  "action": "APPEND|CREATE_NEW",
  "target_id": "reflection-id-to-append-to or null",
  "reason": "Brief explanation"
}}"""
