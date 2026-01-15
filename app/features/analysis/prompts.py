"""
LLM Prompts for transcript analysis.
Centralized prompt templates for consistent AI behavior.

TWO-STAGE ARCHITECTURE:
- Stage 1 (Haiku): Entity extraction + context gathering (in context_gatherer.py)
- Stage 2 (Sonnet): Main analysis with rich context (this file)
"""

from typing import List, Dict, Optional, Any
from datetime import datetime


def build_multi_analysis_prompt(
    transcript: str,
    filename: str,
    recording_date: str,
    existing_topics: List[Dict[str, str]],
    user_context: str = None,
    transcript_stats: Dict = None,
    known_contacts: List[Dict[str, str]] = None,
    person_context: Dict = None,
    calendar_context: List[Dict] = None,
    rich_context: Dict[str, Any] = None,  # NEW: Rich context from Stage 1
) -> str:
    """
    Build the main analysis prompt for Claude (Stage 2).
    
    Args:
        rich_context: Pre-gathered context from Stage 1 (ContextGatherer), including:
            - extracted_entities: Names, companies, topics detected
            - contacts: Matched contacts with details
            - recent_meetings: Past meetings with mentioned people
            - existing_reflections: For routing decisions
            - open_tasks: Current task list
            - recent_journals: For continuity
            - calendar_events: Upcoming/recent events
            - relevant_emails: Emails from mentioned contacts
            - applications: Job applications if relevant
    
    CRITICAL IMPROVEMENTS:
    1. German input → English output (always)
    2. Better journal detection
    3. Proper task extraction
    4. Link all records to transcripts/contacts
    5. CORRECT PERSPECTIVE - user is the speaker
    6. Scale output detail based on transcript length
    7. Consolidate multiple conversations into ONE meeting per person
    8. AI-DRIVEN reflection routing (no code-based fuzzy matching)
    9. SMART TRANSCRIPTION CORRECTION using known contacts
    10. PERSON CONTEXT - Use confirmed person name when provided
    11. RICH CONTEXT from Stage 1 for better understanding (NEW!)
    """
    
    # Calculate transcript stats for scaling output
    if transcript_stats is None:
        transcript_stats = {
            "char_count": len(transcript),
            "word_count": len(transcript.split()),
            "is_long": len(transcript) > 50000,  # ~10K words
            "is_very_long": len(transcript) > 100000,  # ~20K words
            "is_short": len(transcript.split()) < 100,  # Quick reminder/note
        }
    
    # Scale summary length based on transcript length
    # IMPORTANT: Keep summaries as CLEAN PROSE, not bullet-heavy
    word_count = transcript_stats.get("word_count", len(transcript.split()))
    if word_count > 15000:
        summary_guidance = "2-3 paragraphs of flowing prose. Cover main themes comprehensively but AVOID bullet points in summary."
        content_guidance = "Capture key substance in CLEAN PROSE. Use topics_discussed for details, NOT the summary."
    elif word_count > 8000:
        summary_guidance = "2 paragraphs of flowing prose. Focus on what was discussed and decided."
        content_guidance = "Capture main points in clean prose. Details go in topics_discussed."
    elif word_count > 3000:
        summary_guidance = "1 paragraph (5-8 sentences). Clean prose, no bullets."
        content_guidance = "Be concise. Specific details go in topics_discussed array."
    elif word_count < 50:
        summary_guidance = "1-2 sentences MAX. This is a quick note."
        content_guidance = "Focus on TASK EXTRACTION - short recordings are quick reminders."
    elif word_count < 150:
        summary_guidance = "2-3 sentences. Keep it brief."
        content_guidance = "Capture core intent. Prioritize task extraction."
    else:
        summary_guidance = "1 paragraph (3-5 sentences). Clean prose."
        content_guidance = "Be concise and clear."
    
    # Build existing reflections context with IDs for AI-driven routing
    if existing_topics:
        topics_lines = "\n".join([
            f"  - ID: \"{topic.get('id', 'unknown')}\" | topic_key: \"{topic.get('topic_key', 'none')}\" | title: \"{topic.get('title', '').strip()}\""
            for topic in existing_topics[:25]
        ])
        topics_context = f"""
**EXISTING REFLECTIONS IN DATABASE (HIGH-LEVEL BUCKETS):**
{topics_lines}

**🎯 CRITICAL: PREFER APPENDING TO EXISTING BUCKETS!**
These reflections are HIGH-LEVEL life themes, NOT individual diary entries. 
Aaron wants to build up comprehensive reflections over time, not scatter them.

**STRONG PREFERENCE: APPEND unless user explicitly says "create new"**

**ROUTING DECISION (in order of priority):**

1. **USER EXPLICIT INSTRUCTIONS** (only if clearly stated):
   - "create new reflection", "new entry", "start fresh" → CREATE NEW
   - "add to [title]", "continue [topic]", "append to" → APPEND
   - Numbered series (e.g., "Exploring Out Loud #4") → CREATE NEW with that number
   
2. **MATCH BY TOPIC_KEY THEME** (DEFAULT - be generous with matching!):
   - Gym, workout, exercise, running, diet, nutrition → `health-sport-nutrition`
   - Vietnamese food, customs, local observations, markets → `vietnam-cultural-observations`  
   - Career moves, job hunting, VC meetings, business → `career-development`
   - Singapore planning, SE Asia relocation → `singapore-relocation`
   - Relationships, dating, personal connections → `relationships`
   - Jarvis system, AI assistant, automation → `project-jarvis`
   
3. **TO APPEND (PREFERRED)**: Set `append_to_id` to the existing reflection's ID
4. **TO CREATE NEW (RARE)**: Only if genuinely new high-level topic not covered above

**IMPORTANT:** A reflection titled "Health, Sport & Nutrition Journey" should get ALL fitness/diet content.
Do NOT create "Gym Session Today" - append to the existing health bucket instead!
"""
    else:
        topics_context = """
**NOTE:** No existing reflections in database yet. All reflections will be created as new.
Remember: topic_keys should be broad themes (e.g., "career-development" not "job-interview-prep")
"""

    # Default user context if not provided
    if not user_context:
        user_context = """Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup. He holds two master's degrees from Germany and Tsinghua University in China. His core interests span climate tech, biotech, agritech, foodtech, and longevity. He's currently preparing to relocate to Singapore and Southeast Asia."""

    # Build known contacts context for smart name correction
    contacts_context = ""
    if known_contacts:
        contact_lines = []
        for c in known_contacts[:200]:  # Top 200 most recently interacted contacts
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            company = c.get('company', '')
            if name:
                if company:
                    contact_lines.append(f"  - {name} ({company})")
                else:
                    contact_lines.append(f"  - {name}")
        if contact_lines:
            contacts_context = f"""
**AARON'S KNOWN CONTACTS (for name correction - {len(contact_lines)} of ~500+ total):**
This is a PARTIAL list of Aaron's contacts, ordered by recent interaction. Not everyone is listed!

When you hear names in the transcript:
1. If it matches or sounds like someone in this list → use the correct spelling
2. If it's a NEW name not in this list → that's fine! Aaron knows many people not listed here
3. Use CONTEXT to determine if a name is a known contact vs a new person

{chr(10).join(contact_lines)}

**IMPORTANT:** Don't assume a name is wrong just because it's not in this list. Aaron has hundreds 
more contacts. Only correct names that SOUND SIMILAR to someone listed (phonetic matching).
"""

    # Build person context for meeting attribution
    person_context_section = ""
    if person_context and person_context.get("confirmed_person_name"):
        confirmed_name = person_context.get("confirmed_person_name")
        is_confirmed = person_context.get("person_confirmed", False)
        prev_meetings = person_context.get("previous_meetings_summary", "")
        
        if is_confirmed:
            person_context_section = f"""
**🎯 CONFIRMED MEETING PARTICIPANT (USER VERIFIED):**
Aaron has CONFIRMED he is meeting with: **{confirmed_name}**
- This is NOT a guess - Aaron explicitly confirmed this
- Use "{confirmed_name}" as the person_name in the meeting record
- Do NOT change this name based on other names mentioned in the transcript
"""
        else:
            person_context_section = f"""
**📅 CALENDAR-DETECTED MEETING PARTICIPANT:**
Based on Aaron's calendar, this appears to be a meeting with: **{confirmed_name}**
- Use "{confirmed_name}" as the person_name unless the transcript clearly indicates otherwise
- Other names mentioned might be people discussed in the conversation, not the meeting participant
"""
        
        if prev_meetings:
            person_context_section += f"""
**📚 PREVIOUS MEETINGS WITH {confirmed_name.upper()}:**
{prev_meetings}
- Consider this context when summarizing the current meeting
- Note any follow-up items from previous discussions
"""

    # Build calendar context for name correction (if no explicit person_context)
    calendar_context_section = ""
    if calendar_context and not (person_context and person_context.get("confirmed_person_name")):
        # Only show calendar context if we don't already have confirmed person
        event_lines = []
        for event in calendar_context[:5]:  # Top 5 recent events
            summary = event.get("summary", "")
            attendees = event.get("attendee_names", [])
            if attendees:
                attendee_str = ", ".join(attendees[:3])
                event_lines.append(f'  - "{summary}" with {attendee_str}')
            elif summary:
                event_lines.append(f'  - "{summary}"')
        
        if event_lines:
            calendar_context_section = f"""
**📅 RECENT CALENDAR EVENTS (for name correction):**
Aaron had these events in the last few hours. If the transcript mentions names that SOUND SIMILAR 
to people in these events, the calendar name is likely correct (speech recognition often mishears names).

{chr(10).join(event_lines)}

EXAMPLE CORRECTIONS:
- If calendar shows "meeting with Hieu" and transcript says "Hoy" or "Hugh" → Use "Hieu"
- If calendar shows "coffee with Alinta" and transcript says "a Linta" → Use "Alinta"
- But if a name is clearly different from calendar attendees, it might be someone else discussed

**CRITICAL:** Cross-reference the calendar to identify who Aaron actually MET WITH vs who they DISCUSSED.
"""

    # Build rich context section from Stage 1 (if available)
    rich_context_section = ""
    if rich_context:
        rich_context_section = _build_rich_context_section(rich_context)

    return f"""You are analyzing an audio transcript. The speaker is Aaron (the user) who recorded this voice memo.
{person_context_section}
{calendar_context_section}
{rich_context_section}
**⚠️ CRITICAL: TRANSCRIPTION ERROR CORRECTION**
The transcript was created by automatic speech recognition which often makes mistakes. You must INTELLIGENTLY CORRECT errors using context:
{contacts_context}
COMMON TRANSCRIPTION ERRORS TO FIX:
- "Java", "Jarvis", "jardin" → Usually means "Jarvis" (Aaron's AI system he's building)
- "Aaron" misheard as "Erin", "Aron", "Erin" → Correct to "Aaron"  
- Names of people Aaron knows may be misspelled - use context to identify likely correct names
- Technical terms may be garbled - use context to infer the correct term
- "Sydney" might be heard as "city" or similar - use geographic context

CORRECTION STRATEGY:
1. If Aaron is discussing his personal AI project development → "Java/jardin/Jarvis" = "Jarvis"
2. If a name sounds similar to someone Aaron has mentioned before, use the correct name
3. For technical terms, use your knowledge of the domain to infer correct terms
4. When uncertain, preserve the original but flag it in `clarifications_needed`

**🔍 UNCERTAINTY DETECTION (IMPORTANT):**
Pay attention to things that seem UNUSUAL or UNCLEAR:
- Aaron mentions a person/project/company casually as if it's well-known, but you've never heard of it
- Names that don't match any contacts AND don't sound like typical names
- Technical terms or acronyms that seem project-specific but aren't explained
- References to past conversations/events that seem important but lack context

When you detect something unclear, add it to `clarifications_needed` in your output. This helps Aaron 
know what context might be missing from his system. Examples:
- "Who is 'Marco'? Not found in contacts - is this a new person or transcription error?"
- "What is 'Project Phoenix'? Mentioned casually but no context in system."
- "Name 'Schwerzenbach' unclear - is this a person, place, or company?"

Apply corrections silently - produce the correct interpretation in your output without explicitly noting every fix.

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

⚠️ **VALIDATION BEFORE OUTPUT:**
Before returning your JSON, CHECK:
1. Does the transcript contain "journal", "journaling", or daily recap phrases?
   - If YES → primary_category MUST be "journal" and journals array MUST NOT be empty
   - A reflection titled "Journaling for today" is WRONG - that should be a JOURNAL
2. Does this describe what happened TODAY or plans for TOMORROW?
   - If YES → This is a JOURNAL, not a reflection
3. If you created a reflection with title containing "journal", "journaling", "today" → STOP, recategorize as journal

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
      "title": "Meeting with [Person Name] (max 50 chars, IN ENGLISH, clean and simple)",
      "date": "{recording_date}",
      "location": "Online",
      "person_name": "Name of THE OTHER PERSON Aaron met with (NOT Aaron)",
      "summary": "Clean paragraph summary ({summary_guidance}, IN ENGLISH). NO bullet points here - just flowing prose that captures the conversation essence.",
      "topics_discussed": [
        {{"topic": "Topic Name (concise, 3-6 words)", "details": ["Use 1-7 key points as needed - not always 3! Match complexity of topic"]}}
      ],
      "people_mentioned": ["Other names mentioned in conversation"],
      "follow_up_conversation": [
        {{"topic": "Thing to discuss next time (brief)", "context": "One sentence context"}}
      ]
    }}
  ],
  
  "reflections": [
    {{
      "append_to_id": "UUID of existing reflection to append to, OR null to create new",
      "title": "Reflection title (max 60 chars, IN ENGLISH) - REQUIRED even when appending",
      "date": "{recording_date}",
      "topic_key": "high-level-topic-key (REQUIRED for new reflections, can match existing for appends)",
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
  ],
  
  "clarifications_needed": [
    {{
      "item": "The unclear term/name/reference",
      "context": "How it was mentioned in the transcript",
      "question": "What clarification would help? Is this a person, project, error?"
    }}
  ],
  
  "proactive_outreach": {{
    "should_reach_out": true/false,
    "reason": "Why reaching out would be valuable (or why not needed)",
    "message": "A thoughtful, warm message to send Aaron via Telegram. Write as Jarvis, his AI assistant. Be supportive, not robotic.",
    "research_needed": ["topic1 to research", "topic2"] or [],
    "outreach_type": "support|research|pattern_observation|follow_up|none"
  }}
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

3. **SMART TASK EXTRACTION** - Only extract REAL action items the user needs to do:
   
   ✅ CREATE tasks for these (clear action required):
   - "I need to get new cash" → task: "Get new cash"
   - "Buy ear plugs before the flight" → task: "Buy ear plugs"
   - "Text Alinta about dinner" → task: "Text Alinta about dinner"
   - "Respond to Will's email" → task: "Respond to Will's email"
   - "Book dentist appointment" → task: "Book dentist appointment"
   - "Send that proposal by Friday" → task with due date
   
   ❌ DO NOT create tasks for:
   - Vague intentions: "Maybe I should...", "Would be nice to...", "I wonder if..."
   - Observations: "I noticed that...", "It seems like..."
   - Things to discuss later: "Ask John about X next time" → put in follow_up_conversation
   - Events/appointments: "Meeting at 3pm", "Flight tomorrow" → NOT tasks
   - Passive thoughts: "Need to think about...", "Should consider..."
   - Things already done: "I did X today"
   
   **KEY PRINCIPLE**: If it's not something that would go on a to-do list, don't create a task.
   Quality over quantity - 2-3 real tasks are better than 10 vague ones.

4. **MEETINGS** - One transcript typically = one meeting:
   - Create ONE meeting entry for the conversation
   - person_name should be THE OTHER PERSON (not Aaron/the user)
   - Use topics_discussed array to capture different subjects covered
   - Each topic should have 1-7 detail points - NOT always 3!
     * Simple topic mentioned briefly → 1-2 details
     * Complex topic with deep discussion → 5-7 details
     * Match the depth of the actual conversation
   - Use follow_up_conversation for things to discuss NEXT TIME

5. **JOURNALS** - Create a journal if the recording is about the day:
   - One journal per day (use the date)
   - Extract mood/effort ONLY if explicitly mentioned
   - "tomorrow_focus" should capture ALL things mentioned for tomorrow
   - You CAN create BOTH a journal AND reflections from one recording
   - Items in "tomorrow_focus" should be brief reminders, not necessarily tasks

6. **REFLECTIONS** - AI-Driven Routing (YOU DECIDE):

   **🎯 APPEND vs CREATE NEW (YOU HAVE FULL CONTROL):**
   
   **LISTEN FOR USER'S EXPLICIT INSTRUCTIONS:**
   - "create new reflection" / "new entry" / "start fresh" → set `append_to_id: null`
   - "add to [topic]" / "continue [title]" / "append to" → set `append_to_id: <ID from list>`
   - "Exploring Out Loud #4" (numbered) → CREATE NEW with that specific number
   - If user says NOTHING about appending → use semantic judgment below
   
   **SEMANTIC ROUTING (when user doesn't specify):**
   - Does this GENUINELY continue the same exploration/thought?
   - Would appending make the reflection better, or dilute it?
   - Is there significant time gap or shift in perspective?
   - When in doubt → CREATE NEW (it's cleaner)
   
   **OUTPUT FIELD:**
   - To APPEND: `"append_to_id": "<UUID from existing reflections list>"`
   - To CREATE NEW: `"append_to_id": null`
   
   **TOPIC_KEY RULES (for new reflections):**
   - topic_keys must be HIGH-LEVEL, BROAD themes
   - Think "what folder would this live in?"
   
   ✅ GOOD topic_keys:
   - "life-in-australia", "career-development", "project-jarvis"
   - "relationships", "health-fitness", "singapore-relocation"
   - "exploring-out-loud-4" (numbered series = specific installment)
   
   ❌ BAD topic_keys (too narrow):
   - "kangaroos-in-sydney" → should be "life-in-australia"
   - "call-with-tom" → this should be a MEETING, not a reflection

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

10. **🚀 PROACTIVE OUTREACH (RESPOND TO DIRECT REQUESTS!):**
    You can proactively message Aaron via Telegram. Use this for DIRECT REQUESTS.
    
    **ALWAYS REACH OUT IF:**
    - Aaron ASKS Jarvis to DO something: "send me a workout", "give me a list", "help me with X"
    - Aaron explicitly asked for research/information: "look up X", "find out about Y"
    - There's a clear question he wants answered: "I should look into X"
    - He requests suggestions, recommendations, or help
    
    **DO NOT REACH OUT FOR:**
    - Routine meeting notes, task reminders, logistics (unless asked)
    - Emotional content that doesn't need commentary
    - Generic "I noticed you mentioned X" without a concrete offer
    - Things Aaron is just documenting, not asking about
    
    **MESSAGE STYLE:**
    - If asked for something (workout, list, suggestion) → PROVIDE IT directly
    - Be specific and actionable
    - Skip warm filler words - get to the point
    - If it's a request for content, include the actual content!
    
    **EXAMPLES:**
    ✅ "You asked for a leg workout. Here's a quick one: 1) Squats 3x12, 2) Lunges 3x10 each, 3) Romanian deadlifts 3x10, 4) Calf raises 3x15"
    ✅ "You asked about relationship frameworks - want me to research attachment styles, hygiene factors, etc.?"
    ✅ "Re: the running pain - I can look up common causes of abdominal discomfort during exercise if helpful."
    ❌ "I heard you describe that experience at the fish market. It's understandable..." (adds no value)
    ❌ "Hey, just checking in about..." (unnecessary warm opening)

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


def _build_rich_context_section(rich_context: Dict[str, Any]) -> str:
    """
    Build the rich context section from Stage 1 gathered data.
    
    This gives Stage 2 (Sonnet) comprehensive context to make smart decisions:
    - Who is this person? What's their history?
    - What related tasks/reflections exist?
    - What happened in recent journals?
    - What's on the calendar?
    """
    sections = []
    
    # 1. Extracted entities (what Stage 1 detected)
    entities = rich_context.get("extracted_entities", {})
    if entities:
        entity_summary = []
        if entities.get("primary_person"):
            entity_summary.append(f"**Primary person:** {entities['primary_person']}")
        if entities.get("person_names"):
            entity_summary.append(f"**People mentioned:** {', '.join(entities['person_names'][:8])}")
        if entities.get("companies"):
            entity_summary.append(f"**Companies:** {', '.join(entities['companies'][:5])}")
        if entities.get("topics"):
            entity_summary.append(f"**Topics detected:** {', '.join(entities['topics'][:5])}")
        if entities.get("content_type"):
            entity_summary.append(f"**Detected type:** {entities['content_type']}")
        if entities.get("action_intent"):
            entity_summary.append(f"**Detected intent:** {', '.join(entities['action_intent'])}")
        
        if entity_summary:
            sections.append(f"""**🔍 DETECTED ENTITIES (from pre-analysis):**
{chr(10).join(entity_summary)}""")
    
    # 2. Matched contacts with full details
    contacts = rich_context.get("contacts", [])
    if contacts:
        contact_lines = []
        for c in contacts[:10]:
            name = c.get("name", "Unknown")
            details = []
            if c.get("company"):
                details.append(c["company"])
            if c.get("job_title"):
                details.append(c["job_title"])
            if c.get("location"):
                details.append(c["location"])
            
            marker = "⭐" if c.get("is_primary_match") else ("?" if c.get("is_suggestion") else "")
            detail_str = f" ({', '.join(details)})" if details else ""
            
            line = f"  - {marker} **{name}**{detail_str}"
            if c.get("notes"):
                line += f"\n    Notes: {c['notes'][:100]}..."
            contact_lines.append(line)
        
        sections.append(f"""**👥 MATCHED CONTACTS IN DATABASE:**
Use these correct spellings. ⭐ = primary match, ? = suggestion
{chr(10).join(contact_lines)}""")
    
    # 3. Recent meetings with these contacts
    meetings = rich_context.get("recent_meetings", [])
    if meetings:
        meeting_lines = []
        for m in meetings[:7]:
            title = m.get("title", "Untitled")
            date = m.get("date", "")
            contact = m.get("contact_name", "")
            summary = m.get("summary", "")[:100]
            
            line = f"  - [{date}] {title}"
            if contact:
                line += f" (with {contact})"
            if summary:
                line += f"\n    {summary}..."
            meeting_lines.append(line)
        
        sections.append(f"""**📅 RECENT MEETINGS (for context):**
{chr(10).join(meeting_lines)}""")
    
    # 4. Open tasks (to avoid duplicates, understand current workload)
    tasks = rich_context.get("open_tasks", [])
    if tasks:
        task_lines = []
        for t in tasks[:12]:
            title = t.get("title", "Untitled")
            due = f" (due: {t['due_date']})" if t.get("due_date") else ""
            priority = f" [{t['priority']}]" if t.get("priority") else ""
            project = f" #{t['project']}" if t.get("project") else ""
            task_lines.append(f"  - {title}{due}{priority}{project}")
        
        sections.append(f"""**✅ OPEN TASKS (don't create duplicates!):**
{chr(10).join(task_lines)}
**IMPORTANT:** Check this list before creating tasks. If a similar task exists, don't duplicate it.""")
    
    # 5. Recent journals (for continuity)
    journals = rich_context.get("recent_journals", [])
    if journals:
        journal_lines = []
        for j in journals[:3]:
            date = j.get("date", "")
            mood = j.get("mood", "")
            focus = ", ".join(j.get("tomorrow_focus", [])[:3]) if j.get("tomorrow_focus") else ""
            summary = j.get("summary", "")[:80]
            
            line = f"  - **{date}**"
            if mood:
                line += f" (mood: {mood})"
            if focus:
                line += f"\n    Tomorrow's focus was: {focus}"
            if summary:
                line += f"\n    Summary: {summary}..."
            journal_lines.append(line)
        
        sections.append(f"""**📓 RECENT JOURNALS (for continuity):**
{chr(10).join(journal_lines)}
If this is a journal, consider referencing/following up on items from recent days.""")
    
    # 6. Related reflections (for smart routing)
    related_reflections = rich_context.get("related_reflections", [])
    if related_reflections:
        ref_lines = []
        for r in related_reflections[:5]:
            title = r.get("title", "Untitled")
            topic = r.get("topic_key", "")
            tags = ", ".join(r.get("tags", [])[:3]) if r.get("tags") else ""
            preview = r.get("content_preview", "")[:80]
            
            line = f"  - **{title}** (topic: {topic})"
            if tags:
                line += f" [tags: {tags}]"
            if preview:
                line += f"\n    {preview}..."
            ref_lines.append(line)
        
        sections.append(f"""**💭 RELATED REFLECTIONS (consider appending?):**
{chr(10).join(ref_lines)}
If this content continues one of these themes, consider appending instead of creating new.""")
    
    # 7. Calendar events (broader context than just name correction)
    calendar = rich_context.get("calendar_events", [])
    if calendar:
        event_lines = []
        for e in calendar[:6]:
            summary = e.get("summary", "Event")
            start = e.get("start_time", "")[:16] if e.get("start_time") else ""
            attendees = ", ".join(e.get("attendees", [])[:3])
            
            line = f"  - [{start}] {summary}"
            if attendees:
                line += f" (with {attendees})"
            event_lines.append(line)
        
        sections.append(f"""**📆 CALENDAR CONTEXT:**
{chr(10).join(event_lines)}""")
    
    # 8. Relevant emails
    emails = rich_context.get("relevant_emails", [])
    if emails:
        email_lines = []
        for e in emails[:5]:
            subject = e.get("subject", "No subject")[:40]
            sender = e.get("sender", "Unknown")
            date = e.get("date", "")[:10] if e.get("date") else ""
            snippet = e.get("snippet", "")[:60]
            
            line = f"  - [{date}] From {sender}: {subject}"
            if snippet:
                line += f"\n    {snippet}..."
            email_lines.append(line)
        
        sections.append(f"""**📧 RELEVANT EMAILS:**
{chr(10).join(email_lines)}""")
    
    # 9. Job applications (if relevant)
    applications = rich_context.get("applications", [])
    if applications:
        app_lines = []
        for a in applications[:8]:
            name = a.get("name", "Application")
            company = a.get("company", "")
            status = a.get("status", "")
            stage = a.get("stage", "")
            
            line = f"  - {name}"
            if company:
                line += f" @ {company}"
            if status:
                line += f" [{status}]"
            if stage:
                line += f" ({stage})"
            app_lines.append(line)
        
        sections.append(f"""**💼 ACTIVE JOB APPLICATIONS:**
{chr(10).join(app_lines)}
Cross-reference if the transcript mentions job search, interviews, or specific companies.""")
    
    # 10. RAG / Knowledge Base results (semantic search across all indexed content)
    knowledge = rich_context.get("knowledge_base", [])
    if knowledge:
        knowledge_lines = []
        for k in knowledge[:10]:
            source_type = k.get("source_type", "unknown")
            similarity = k.get("similarity", 0)
            content = k.get("content", "")[:200]
            metadata = k.get("metadata", {})
            
            # Format by type
            if source_type == "transcript":
                line = f"  - 🎤 [Transcript] (sim: {similarity:.2f}): {content}..."
            elif source_type == "meeting":
                line = f"  - 📅 [Meeting] (sim: {similarity:.2f}): {content}..."
            elif source_type == "journal":
                line = f"  - 📓 [Journal] (sim: {similarity:.2f}): {content}..."
            elif source_type == "reflection":
                line = f"  - 💭 [Reflection] (sim: {similarity:.2f}): {content}..."
            elif source_type == "message":
                line = f"  - 💬 [Message] (sim: {similarity:.2f}): {content}..."
            else:
                line = f"  - 📄 [{source_type}] (sim: {similarity:.2f}): {content}..."
            
            knowledge_lines.append(line)
        
        sections.append(f"""**🔮 KNOWLEDGE BASE (Semantic Search):**
{chr(10).join(knowledge_lines)}""")
    
    # 11. Memories (Mem0 - semantic long-term memory)
    memories = rich_context.get("memories", [])
    if memories:
        memory_lines = []
        for m in memories[:8]:
            content = m.get("content", "")[:150]
            category = m.get("category", "")
            
            if category:
                line = f"  - [{category}] {content}..."
            else:
                line = f"  - {content}..."
            memory_lines.append(line)
        
        sections.append(f"""**🧠 MEMORIES (Long-term knowledge about Aaron):**
{chr(10).join(memory_lines)}""")
    
    # Combine all sections
    if sections:
        return f"""
**🧠 RICH CONTEXT (Pre-gathered from database):**
Use this to:
1. Correct names (use exact spellings from contacts)
2. Understand relationships (previous meetings, email history)
3. Avoid duplicate tasks (check existing tasks)
4. Route reflections properly (append to existing if related)
5. Connect dots (calendar, memories, knowledge base)

{chr(10).join(sections)}

---
"""
    return ""
