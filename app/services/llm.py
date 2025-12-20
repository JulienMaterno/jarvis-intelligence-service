"""
Enhanced Claude Analyzer with Multi-Database Support.
Analyzes transcripts and routes to: Meetings, Reflections, Tasks, and CRM.
"""

import logging
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
from anthropic import Anthropic
import re
from app.core.config import settings

logger = logging.getLogger('Jarvis.Intelligence.LLM')


class ClaudeMultiAnalyzer:
    """Analyze transcripts for multi-database routing and extraction."""
    
    def __init__(self, api_key: str = None, model: str = None):
        self.client = Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.CLAUDE_MODEL
        logger.info(f"Claude Multi-Database analyzer initialized with model: {self.model}")
    
    def analyze_transcript(
        self, 
        transcript: str, 
        filename: str, 
        recording_date: Optional[str] = None,
        existing_topics: list = None
    ) -> Dict:
        """
        Analyze transcript and extract structured information for multiple databases.
        
        Args:
            transcript: Full transcript text
            filename: Original audio filename
            recording_date: ISO date string of recording (defaults to today)
            existing_topics: List of existing reflection topics from DB for smart routing
        
        Returns:
            Dict with structure:
            {
                "primary_category": "meeting|reflection|task_planning|other",
                "meetings": [...],  # Array of meeting objects
                "reflections": [...],  # Array of reflection objects
                "tasks": [...],
                "crm_updates": [...]
            }
        """
        try:
            logger.info("Analyzing transcript for multi-database routing")
            
            if not recording_date:
                recording_date = datetime.now().date().isoformat()
            
            prompt = self._build_multi_analysis_prompt(transcript, filename, recording_date, existing_topics)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,  # Increased for more complex output
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse JSON response
            result_text = response.content[0].text
            
            # Clean potential markdown code blocks
            result_text = result_text.strip()
            if result_text.startswith('```'):
                result_text = re.sub(r'^```(?:json)?\n?', '', result_text)
                result_text = re.sub(r'\n?```$', '', result_text)
            
            analysis = json.loads(result_text)
            
            # Post-process due dates
            analysis = self._process_due_dates(analysis, recording_date)
            
            primary = analysis.get('primary_category', 'other')
            task_count = len(analysis.get('tasks', []))
            crm_count = len(analysis.get('crm_updates', []))
            
            logger.info(f"Analysis complete: category={primary}, tasks={task_count}, crm_updates={crm_count}")
            return analysis
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Response text: {result_text[:500]}")
            return self._default_analysis(transcript, filename, recording_date)
        except Exception as e:
            logger.error(f"Error analyzing transcript: {e}")
            return self._default_analysis(transcript, filename, recording_date)
    
    def _build_multi_analysis_prompt(self, transcript: str, filename: str, recording_date: str, existing_topics: list = None) -> str:
        """Build comprehensive prompt for multi-database analysis."""
        
        # Build existing topics context
        topics_context = ""
        if existing_topics and len(existing_topics) > 0:
            topics_list = "\n".join([f"  • {t['topic_key']}: \"{t['title']}\"" for t in existing_topics[:20]])
            topics_context = f"""
**EXISTING REFLECTION TOPICS (from database):**
These are ongoing topics I've already been building. Consider whether this recording fits into one of them:
{topics_list}

**TOPIC ROUTING RULES:**
- If this recording clearly relates to an existing topic → use that topic_key (content will be APPENDED)
- If I explicitly say "new topic", "start fresh", "separate reflection" → create new topic_key
- If the content is genuinely different from all existing topics → create new topic_key  
- If unsure and content is substantial → prefer creating new topic (better to have too many than miss-merge)
"""
        else:
            topics_context = """
**NOTE:** No existing reflection topics in database yet. Create new topic_keys as needed.
"""
        
        return f"""You are analyzing an audio transcript recorded by Aaron. Extract information from Aaron's perspective (first person).

**ABOUT AARON (for context):**
Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup developing photobioreactor technology for algae and cyanobacteria cultivation. He holds two master's degrees from Germany and Tsinghua University in China, and previously worked in consulting before moving into the startup world.

His core interests span climate tech, biotech, agritech, foodtech, and longevity. He has a strong technical background bridging hardware and software—comfortable with embedded systems (Arduino, ESP32), automation tools like Python, and building custom infrastructure. He prefers self-hosted and open-source tools over subscription services.

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
      "topic_key": "project-jarvis|explore-out-loud|career-thoughts|etc (lowercase, hyphenated identifier for recurring topics, or null if one-off)",
      "tags": ["tag1", "tag2"],
      "sections": [
        {{
          "heading": "Main Insight or Theme",
          "content": "Detailed content for this section..."
        }},
        {{
          "heading": "Implications or Lessons",
          "content": "What this means going forward..."
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
   - Keywords that indicate journal: "today", "this morning", "tonight", "this evening", "tomorrow", "woke up"
   - Extract mood/effort/sports ONLY if explicitly mentioned, otherwise null/empty
   - Structure into sections: Morning, Main Activities, Evening Thoughts, etc.
   - Extract tasks mentioned for tomorrow into "tomorrow_focus"
   - One journal entry per recording (tied to the date)

4. **Reflections Array (SMART TOPIC ROUTING):**
   - Only 1-2 tags per reflection (keep it focused)
   - "sections": Structure the reflection with clear headings and content. Use 2-4 sections like "Key Insight", "Context", "Implications", "Next Steps"
   - Make it scannable and well-organized
   - Use for TOPIC-BASED reflections, NOT daily journals
   
   **"topic_key" DECISION LOGIC (CRITICAL):**
   - Look at the EXISTING TOPICS list above first!
   - If recording content fits an existing topic → USE THAT EXACT topic_key (will append)
   - If I say "for the newsletter", "about project X", "continuing my thoughts on Y" → match to existing or create consistent key
   - If I say "new topic", "fresh reflection", "separate thought" → create NEW topic_key
   - If content is genuinely unrelated to all existing topics → create NEW topic_key
   - Format: lowercase, hyphenated (e.g., "project-jarvis", "career-transition", "startup-ideas")
   - When in doubt about merging: prefer creating new topic (can be merged later, but splitting is harder)

5. **Tasks Array - BE SELECTIVE:**
   - ONLY extract TRUE tasks that require active effort from me
   - ✅ GOOD tasks: "Need to call the bank", "Should email John the proposal", "Have to renew passport", "Follow up with Sarah"
   - ❌ NOT tasks: "Flying to Bali next month", "Meeting with John on Tuesday", "Birthday party on Saturday" (these are events/plans, not action items)
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
   - Return ONLY the JSON object

Now analyze the transcript and return the JSON:"""
    
    def _process_due_dates(self, analysis: Dict, recording_date: str) -> Dict:
        """
        Post-process tasks to convert natural language due dates to ISO dates.
        """
        base_date = datetime.fromisoformat(recording_date)
        
        tasks = analysis.get('tasks', [])
        for task in tasks:
            due_context = task.get('due_context', '').lower() if task.get('due_context') else ''
            
            if not due_context or task.get('due_date'):
                continue  # Already has a date or no context
            
            # Parse natural language dates
            due_date = None
            
            if 'tomorrow' in due_context:
                due_date = base_date + timedelta(days=1)
            elif 'today' in due_context:
                due_date = base_date
            elif 'next week' in due_context or 'in a week' in due_context:
                due_date = base_date + timedelta(weeks=1)
            elif 'this week' in due_context:
                # Set to end of week (Sunday)
                days_until_sunday = (6 - base_date.weekday()) % 7
                due_date = base_date + timedelta(days=days_until_sunday if days_until_sunday > 0 else 7)
            elif 'next month' in due_context:
                due_date = base_date + timedelta(days=30)
            elif re.search(r'(\d+)\s*day', due_context):
                days = int(re.search(r'(\d+)\s*day', due_context).group(1))
                due_date = base_date + timedelta(days=days)
            
            if due_date:
                task['due_date'] = due_date.date().isoformat()
        
        return analysis
    
    def _default_analysis(self, transcript: str, filename: str, recording_date: str) -> Dict:
        """Return a safe default analysis if Claude fails."""
        logger.warning("Using fallback analysis due to Claude API failure")
        
        # Extract first meaningful sentence or paragraph for title
        title_text = transcript[:200].strip()
        if '.' in title_text:
            title_text = title_text.split('.')[0]
        title = title_text[:60] or filename.replace('.mp3', '').replace('.m4a', '').replace('_', ' ')[:60]
        
        # Create a summary note instead of raw transcript
        summary = f"⚠️ Automatic analysis failed. Please review and categorize this entry manually.\n\nAudio file: {filename}\nLength: {len(transcript)} characters"
        
        return {
            'primary_category': 'reflection',
            'meeting': None,
            'reflection': {
                'title': title,
                'date': recording_date,
                'location': None,
                'tags': ['failed-analysis'],
                'sections': [
                    {
                        'heading': 'Raw Transcript',
                        'content': transcript[:2000] + "..." if len(transcript) > 2000 else transcript
                    }
                ],
                'content': summary
            },
            'tasks': [],
            'crm_updates': []
        }
