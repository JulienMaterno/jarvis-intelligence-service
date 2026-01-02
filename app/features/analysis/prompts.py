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
    transcript_stats: Dict = None,
) -> str:
    """
    Build the main analysis prompt for Claude.
    
    CRITICAL IMPROVEMENTS:
    1. German input → English output (always)
    2. Better journal detection
    3. Proper task extraction
    4. Link all records to transcripts/contacts
    5. CORRECT PERSPECTIVE - user is the speaker
    6. Scale output detail based on transcript length
    7. Consolidate multiple conversations into ONE meeting per person
    """
    
    # Calculate transcript stats for scaling output
    if transcript_stats is None:
        transcript_stats = {
            "char_count": len(transcript),
            "word_count": len(transcript.split()),
            "is_long": len(transcript) > 50000,  # ~10K words
            "is_very_long": len(transcript) > 100000,  # ~20K words
        }
    
    # Scale summary length based on transcript length
    word_count = transcript_stats.get("word_count", len(transcript.split()))
    if word_count > 15000:
        summary_guidance = "12-20 sentences (this is a LONG recording - be comprehensive)"
        content_guidance = "Capture 80-90% of substance - this is a long recording that deserves detailed documentation"
    elif word_count > 8000:
        summary_guidance = "8-12 sentences (medium-length recording)"
        content_guidance = "Capture 75-85% of substance"
    elif word_count > 3000:
        summary_guidance = "5-8 sentences"
        content_guidance = "Capture 70-80% of substance"
    else:
        summary_guidance = "3-5 sentences"
        content_guidance = "Capture 60-70% of substance"
    
    # Build existing topics context
    if existing_topics:
        topics_lines = "\n".join([
            f"  - topic_key: \"{topic.get('topic_key', 'unknown')}\" | title: \"{topic.get('title', '').strip()}\""
            for topic in existing_topics[:20]
        ])
        topics_context = f"""
**EXISTING REFLECTION TOPICS (from database):**
Review these existing high-level topics before creating any new reflections:
{topics_lines}

**IMPORTANT - TOPIC ROUTING:**
- If this recording relates to ANY existing topic above → use that EXACT topic_key (content will be APPENDED)
- Only create a NEW topic_key if the content is genuinely different from ALL existing topics
- topic_keys are HIGH-LEVEL categories (e.g., "life-in-australia" not "kangaroos")
- When in doubt, PREFER using an existing topic_key over creating a new one
"""
    else:
        topics_context = """
**NOTE:** No existing reflection topics in database yet. Create HIGH-LEVEL topic_keys as needed.
Remember: topic_keys should be broad themes (e.g., "career-development" not "job-interview-prep")
"""

    # Default user context if not provided
    if not user_context:
        user_context = """Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup. He holds two master's degrees from Germany and Tsinghua University in China. His core interests span climate tech, biotech, agritech, foodtech, and longevity. He's currently preparing to relocate to Singapore and Southeast Asia."""

    return f"""You are analyzing an audio transcript. The speaker is Aaron (the user) who recorded this voice memo.

**⚠️ CRITICAL: PERSPECTIVE**
Aaron is the speaker who recorded this. When he talks about meeting someone, Aaron MET WITH that person.
- If Aaron says "had coffee with Alinta" → Meeting title: "Coffee with Alinta" (Aaron met WITH Alinta)
- If Aaron mentions "Aaron" in third person or another person mentions "Aaron" → That's still referring to the user
- The person_name in meetings should be THE OTHER PERSON, not Aaron
- CRM updates are for THE OTHER PERSON (the one Aaron met), not for Aaron

**CRITICAL: OUTPUT LANGUAGE**
Even if the transcript is in German, Turkish, or any other language, ALL your output MUST be in ENGLISH.
Translate everything to English while preserving the meaning and context.

**ABOUT THE USER (Aaron - THE SPEAKER):**
{user_context}
{topics_context}

**TRANSCRIPT CONTEXT:**
- Filename: {filename}
- Recording Date: {recording_date}
- Transcript Length: ~{word_count} words ({summary_guidance})
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

**⚠️ CRITICAL: ONE MEETING PER PERSON**
Even if a long conversation with the same person covers many topics, create ONLY ONE meeting entry.
- Consolidate all topics discussed into ONE meeting record
- Use topics_discussed array for different subjects covered
- Do NOT create multiple meeting entries for the same conversation
- A "meeting" is a single interaction/conversation, regardless of length or topics covered

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
      "summary": "Brief summary of the day ({summary_guidance}, IN ENGLISH)",
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
      "title": "Brief descriptive title - e.g., 'Coffee Chat with [Person Name]' (max 60 chars, IN ENGLISH)",
      "date": "{recording_date}",
      "location": "Location if mentioned, otherwise null",
      "person_name": "Name of THE OTHER PERSON Aaron met with (NOT Aaron)",
      "summary": "Comprehensive summary ({summary_guidance}, IN ENGLISH) - {content_guidance}",
      "topics_discussed": [
        {{"topic": "Topic name", "details": ["Point 1", "Point 2", "Point 3"]}}
      ],
      "people_mentioned": ["Other names mentioned in conversation"],
      "follow_up_conversation": [
        {{"topic": "Thing to ask next time", "context": "Why it matters", "date_if_known": null}}
      ]
    }}
  ],
  
  "reflections": [
    {{
      "title": "Reflection title (max 60 chars, IN ENGLISH)",
      "date": "{recording_date}",
      "topic_key": "high-level-topic-key (REQUIRED - see rules below)",
      "tags": ["tag1", "tag2"],
      "content": "Comprehensive markdown content - {content_guidance} (IN ENGLISH)",
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

1. **RESPECT USER INSTRUCTIONS** - This is the MOST IMPORTANT rule:
   - If the user explicitly says "don't create a meeting", "no meeting record", "skip the meeting" → DO NOT create a meeting entry
   - If the user says "this is not a task", "don't add as task", "just noting" → DO NOT create a task
   - If the user says "don't record this", "off the record", "just thinking out loud" → minimize/skip extraction
   - Listen for phrases like "I'm not asking you to...", "don't make a...", "this is just for context"
   - The user's explicit instructions ALWAYS override your automatic categorization
   - When in doubt about user intent, err on the side of NOT creating records

2. **Primary Category** - Set based on main content:
   - "journal" if this is about daily events, planning, or has journal indicators
   - "meeting" if primarily about conversation with someone
   - "reflection" if deeper thoughts on a specific topic
   - "task_planning" if mainly about organizing tasks
   - "other" if none apply

3. **AGGRESSIVE TASK EXTRACTION** - Extract tasks liberally! Look for:
   
   ✅ GOOD tasks (create tasks for ALL of these):
   - "I need to get new cash" → task: "Get new cash"
   - "Buy ear plugs before the flight" → task: "Buy ear plugs"
   - "Text Alinta about dinner" → task: "Text Alinta about dinner"
   - "Respond to Will's email" → task: "Respond to Will's email"
   - "Book dentist appointment" → task: "Book dentist appointment"
   - "Need to work through this" → task: "Work through [topic being discussed]"
   - "Should probably look into that" → task: "Look into [topic]"
   - "Gotta figure out how to..." → task: "Figure out [thing]"
   - "Have to get that sorted" → task: "Sort out [thing]"
   - "Maybe I should..." (if actionable) → task
   - "Would be good to..." (if actionable) → task
   - "Should reach out to [person]" → task: "Reach out to [person]"
   - "Need to follow up on..." → task: "Follow up on [thing]"
   - "Meant to do..." → task
   - "Still haven't done..." → task
   
   ❌ NOT tasks (just context, events, or reminders for conversation):
   - "Next time I talk to John I should ask about his project" → This is MEETING FOLLOW-UP context, put in "follow_up_conversation" field
   - "When I see her again I want to mention X" → MEETING FOLLOW-UP, not a task
   - "Flying to Bali tomorrow" → This is an EVENT, not a task
   - "Meeting with Sarah at 3pm" → This is an EVENT, not a task (unless you need to prepare something)
   - Pure observations without action intent

   KEY DISTINCTION:
   - "Ask John about his vacation" with no specific timing = put in meeting's follow_up_conversation
   - "Send John an email asking about vacation" = THIS is a task (specific action: send email)
   - "Need to work through this presentation" = THIS is a task (implies work needed)

4. **ONE MEETING PER CONVERSATION/PERSON** - CRITICAL:
   - Even if you discuss 10 topics with someone, create ONE meeting entry
   - Use the topics_discussed array to capture different subjects
   - Do NOT split a single conversation into multiple meetings
   - A 2-hour coffee chat = 1 meeting with many topics_discussed entries
   - person_name should be THE OTHER PERSON (not Aaron/the user)

5. **JOURNALS** - Create a journal if the recording is about the day:
   - One journal per day (use the date)
   - Extract mood/effort ONLY if explicitly mentioned
   - "tomorrow_focus" should capture ALL things mentioned for tomorrow
   - You CAN create BOTH a journal AND reflections from one recording
   - Items in "tomorrow_focus" should be brief reminders, not necessarily tasks

6. **REFLECTIONS** - For topic-based thoughts:
   - **topic_key is REQUIRED** for every reflection - never leave it null
   - Use existing topic_key if content fits an existing topic
   - Create new topic_key for genuinely new topics
   - Multiple reflections OK if multiple topics discussed
   - "content" should be COMPREHENSIVE (70-90% of relevant substance)
   
   **TOPIC_KEY CREATION RULES (CRITICAL):**
   - topic_keys must be HIGH-LEVEL, BROAD themes - not narrow subtopics
   - Think "what folder would this live in?" not "what specific thing is mentioned?"
   
   ✅ GOOD topic_keys (high-level):
   - "life-in-australia" (not "kangaroos" or "sydney-beaches")
   - "career-development" (not "salary-negotiation")  
   - "project-jarvis" (not "jarvis-telegram-bot")
   - "relationships" (not "dinner-with-sarah")
   - "health-fitness" (not "morning-jog")
   - "singapore-relocation" (not "visa-application")
   - "climate-tech-thoughts" (not "carbon-capture")
   - "personal-growth" (not "meditation-session")
   
   ❌ BAD topic_keys (too narrow):
   - "kangaroos-in-sydney" → should be "life-in-australia"
   - "monday-gym-session" → should be "health-fitness"
   - "fixing-bug-123" → should be "project-jarvis" or "engineering-work"
   - "call-with-tom" → this should be a MEETING, not a reflection
   
   **ROUTING DECISION:**
   - First: Check if content fits ANY existing topic from the list
   - If yes: Use that exact topic_key (content will be appended)
   - If no: Create a NEW high-level topic_key

7. **MEETINGS** - For conversations with people:
   - "person_name" is the PRIMARY person met with
   - "people_mentioned" is everyone else discussed
   - Only the PRIMARY person gets a CRM update
   - Use "follow_up_conversation" for things to discuss NEXT TIME you see this person
     Example: "Next time I see John, ask about his startup" → goes in follow_up_conversation, NOT tasks
   - follow_up_conversation is for CONVERSATIONAL reminders, not action items

8. **CRM** - Only for the person actually met with:
   - Don't create CRM entries for people merely mentioned
   - Capture personal details: family, hobbies, upcoming events

9. **LANGUAGE** - All output MUST be in English:
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
