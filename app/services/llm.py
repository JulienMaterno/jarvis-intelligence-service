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
    
    def analyze_transcript(self, transcript: str, filename: str, recording_date: Optional[str] = None) -> Dict:
        """
        Analyze transcript and extract structured information for multiple databases.
        
        Args:
            transcript: Full transcript text
            filename: Original audio filename
            recording_date: ISO date string of recording (defaults to today)
        
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
            
            prompt = self._build_multi_analysis_prompt(transcript, filename, recording_date)
            
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
    
    def _build_multi_analysis_prompt(self, transcript: str, filename: str, recording_date: str) -> str:
        """Build comprehensive prompt for multi-database analysis."""
        return f"""You are analyzing an audio transcript recorded by Aaron. Extract information from Aaron's perspective (first person).

**ABOUT AARON (for context):**
Aaron is a German engineer based in Sydney, currently in transition after being the first employee at Algenie, an Australian biotech startup developing photobioreactor technology for algae and cyanobacteria cultivation. He holds two master's degrees from Germany and Tsinghua University in China, and previously worked in consulting before moving into the startup world.

His core interests span climate tech, biotech, agritech, foodtech, and longevity. He has a strong technical background bridging hardware and software—comfortable with embedded systems (Arduino, ESP32), automation tools like Python, and building custom infrastructure. He prefers self-hosted and open-source tools over subscription services.

Aaron is systematic about relationship management, maintaining a comprehensive Notion CRM for professional and personal contacts. He's currently preparing to relocate to Singapore and Southeast Asia to explore new opportunities in the startup ecosystem there.

**TRANSCRIPT CONTEXT:**
- Filename: {filename}
- Recording Date: {recording_date}
- Speaker: Aaron (the transcript is from Aaron's perspective)

**TRANSCRIPT:**
{transcript}

---

**YOUR TASK:**
Analyze this transcript from Aaron's perspective and extract structured information for routing to 4 different databases:
1. **Meetings Database** - For conversations with other people
2. **Reflections Database** - For personal thoughts, ideas, evening reflections, learnings
3. **Tasks Database** - For TRUE action items that require active effort
4. **CRM Database** - For updating contact information ONLY about the person I met with (not everyone mentioned!)

**IMPORTANT DISTINCTIONS:**
- TASKS vs NON-TASKS: "Fly to Bali" is NOT a task (it's a plan that happens anyway). "Need to change my Medicare" IS a task (requires active effort). Only extract things that require me to take action.
- CRM: Only create CRM update for the PRIMARY person I'm meeting/talking with, NOT every person mentioned in conversation.

**OUTPUT FORMAT:**
Return ONLY valid JSON (no markdown, no code blocks) with this exact structure:

{{
  "primary_category": "meeting|reflection|task_planning|other",
  
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
  
  "reflections": [
    {{
      "title": "Brief reflection title (max 60 chars)",
      "date": "{recording_date}",
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
   - "reflection" if personal thoughts, evening reflections, learnings, ideas
   - "task_planning" if primarily about organizing tasks
   - "other" if none of above

2. **Meetings Array:**
   - Create SEPARATE meeting objects for each distinct conversation
   - "topics_discussed": Break down ALL topics into separate objects with topic name and specific bullet points. Each topic should have 2-5 detail bullets capturing what was said.
   - "people_mentioned": List everyone mentioned in the conversation (for reference, NOT for CRM)
   - "follow_up_conversation": Things I should bring up next time I see this person - their upcoming vacation, stressful exam, new job, etc. Include dates when known. This helps me show I remember and care.
   - "summary": Write a thorough 4-6 sentence summary

3. **Reflections Array:**
   - Only 1-2 tags per reflection (keep it focused)
   - "sections": Structure the reflection with clear headings and content. Use 2-4 sections like "Key Insight", "Context", "Implications", "Next Steps"
   - Make it scannable and well-organized

4. **Tasks Array - BE SELECTIVE:**
   - ONLY extract TRUE tasks that require active effort from me
   - ✅ GOOD tasks: "Need to call the bank", "Should email John the proposal", "Have to renew passport", "Follow up with Sarah"
   - ❌ NOT tasks: "Flying to Bali next month", "Meeting with John on Tuesday", "Birthday party on Saturday" (these are events/plans, not action items)
   - Ask yourself: "Does this require me to actively DO something, or will it just happen?"

5. **CRM Updates - ONE PERSON ONLY:**
   - ONLY create CRM entry for the person I'm MEETING WITH
   - Do NOT create entries for people merely mentioned in conversation
   - If I meet with John and we discuss Sarah and Mike, only John gets a CRM update
   - "personal_notes": Things to remember - their family situation, hobbies, upcoming travel, stressful situations, preferences
   - Skip CRM entirely if it's a reflection or no clear meeting person

6. **Follow-up Conversation Section (IMPORTANT):**
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
