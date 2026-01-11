"""
Chat Tools for Conversational AI.

These tools are exposed to Claude for answering questions and taking actions.
Mirrors the MCP approach used in Claude Desktop.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase

logger = logging.getLogger("Jarvis.Chat.Tools")


# =============================================================================
# RESEARCH TOOLS (LinkedIn, Web Search)
# Lazy import to avoid circular dependencies
# =============================================================================

async def _handle_research_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Handle research tool calls (LinkedIn, Web Search)."""
    from app.features.research import handle_research_tool
    return await handle_research_tool(tool_name, tool_input)


# =============================================================================
# TOOL DEFINITIONS (for Claude)
# =============================================================================

TOOLS = [
    {
        "name": "execute_sql_write",
        "description": """Execute a write SQL statement (UPDATE, INSERT, DELETE) against the database.

⚠️ REQUIRES USER CONFIRMATION - Always set user_confirmed=false first to show what will change, then call again with user_confirmed=true after user confirms.

WHEN TO USE:
- User says "update X to Y", "change X", "set X to Y", "fix X"
- Modifying single fields that specific tools don't handle
- Bulk updates (with user confirmation)
- Any direct data manipulation request

HOW TO USE (2-step process):
1. FIRST CALL: Set user_confirmed=false to preview the change
2. SECOND CALL: After user confirms, call with user_confirmed=true

SQL FORMAT REQUIREMENTS:
- UPDATE: UPDATE table SET col1='val1', col2='val2' WHERE id='uuid'
- INSERT: INSERT INTO table (col1, col2) VALUES ('val1', 'val2')
- DELETE: DELETE FROM table WHERE id='uuid'
- MUST include WHERE id='uuid' for UPDATE/DELETE (safety requirement)

IMPORTANT BEHAVIORS:
- The tool automatically sets updated_at=now() on updates
- The tool automatically sets last_sync_source='supabase' for sync-managed tables (this triggers sync to Notion)
- Use .select() is handled internally - you'll get the updated record back

EXAMPLE - Update application status:
sql: "UPDATE applications SET status='Applied' WHERE id='550e8400-e29b-41d4-a716-446655440000'"
description: "Mark Cosmos application as Applied"
user_confirmed: false (first), then true (after confirmation)

WRITABLE TABLES:
- contacts, meetings, tasks, journals, reflections
- applications, linkedin_posts, books, highlights

READ-ONLY TABLES (managed by sync - cannot modify):
- calendar_events, emails, beeper_chats, beeper_messages, transcripts

For common operations, prefer specific tools when available:
- Tasks: create_task, complete_task, update_task
- Contacts: create_contact, update_contact
- Meetings/Reflections: create_meeting, create_reflection""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL statement. Format: UPDATE table SET col='val' WHERE id='uuid'"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Set false first to preview, then true after user confirms"
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this change does"
                }
            },
            "required": ["sql", "user_confirmed", "description"]
        }
    },
    {
        "name": "query_database",
        "description": """Execute a read-only SQL query against the knowledge database.
Use this for novel/complex queries that specific tools can't handle. For common operations, prefer specific tools like get_applications, search_contacts, get_tasks.

FULL DATABASE SCHEMA:
====================

CORE DATA:
----------
• contacts: CRM contacts
  - id (uuid), first_name, last_name, email, company, job_title, phone, birthday (date), 
  - linkedin_url, location, notes, dynamic_properties (jsonb)
  - deleted_at (null = active), created_at, updated_at

• meetings: Meeting records  
  - id (uuid), title, date (timestamptz), location, summary (text)
  - contact_id (fk→contacts), contact_name, topics_discussed (jsonb), people_mentioned (text[])
  - action_items (jsonb), source_file, source_transcript_id (fk→transcripts)

• tasks: Action items
  - id (uuid), title, description, status ('pending'|'in_progress'|'done'), priority ('high'|'medium'|'low')
  - due_date (date), completed_at (timestamptz), project, tags (text[])
  - origin_id, origin_type ('meeting'|'journal'|'reflection')

• reflections: Personal reflections/notes
  - id (uuid), title, topic_key (slug), content (text), tags (text[])
  - date, mood, energy_level, people_mentioned (text[])
  - source_file, source_transcript_id, deleted_at

• journals: Daily journal entries
  - id (uuid), date (unique), title, content, mood, energy
  - gratitude (text[]), wins (text[]), challenges (text[]), tomorrow_focus (text[])

CALENDAR & EMAIL:
-----------------
• calendar_events: Google Calendar
  - id (uuid), google_event_id (unique), calendar_id, summary, description
  - start_time (timestamptz), end_time (timestamptz), location
  - status ('confirmed'|'tentative'|'cancelled'), attendees (jsonb), contact_id (fk→contacts)

• emails: Gmail messages
  - id (uuid), google_message_id (unique), thread_id, subject, sender, recipient
  - date (timestamptz), snippet, body_text, body_html, labels (text[])
  - is_read (bool), contact_id (fk→contacts)

MEDIA & CONTENT:
----------------
• transcripts: Voice memo transcriptions
  - id (uuid), full_text (text), source_file, audio_duration (float)
  - language, segments (jsonb), speakers (text[]), model_used

• books: Reading list
  - id (uuid), title, author, status ('reading'|'completed'|'want-to-read'|'abandoned')
  - rating (1-5), current_page, total_pages, summary, notes

• highlights: Book highlights  
  - id (uuid), book_id (fk→books), book_title, content (text), note
  - chapter, page_number, is_favorite (bool)

APPLICATIONS & LINKEDIN:
------------------------
• applications: Grant/fellowship applications
  - id (uuid), name, application_type ('Grant'|'Fellowship'|'Program'|'Accelerator'|'Residency')
  - status ('Not Started'|'Researching'|'In Progress'|'Applied'|'Accepted')
  - institution, website (url), grant_amount, deadline (date)
  - context (text), notes (text), content (text - full application text)

• linkedin_posts: LinkedIn content
  - id (uuid), title, post_date (date)
  - status ('Idea'|'Posted'), pillar ('Personal'|'Longevity'|'Algenie')
  - likes, content (text - full post text)

MESSAGING (Beeper):
-------------------
• beeper_chats: Chat rooms/DMs
  - id (uuid), beeper_chat_id (unique), platform ('whatsapp'|'linkedin'|'slack'|etc.)
  - chat_type ('dm'|'group'), chat_name, contact_id (fk→contacts)
  - needs_response (bool), is_archived (bool)

• beeper_messages: Chat messages
  - id (uuid), beeper_event_id (unique), beeper_chat_id, content (text)
  - is_outgoing (bool), timestamp (timestamptz), contact_id (fk→contacts)

SQL TIPS:
---------
• Use ILIKE for case-insensitive search: WHERE title ILIKE '%keyword%'
• Filter active contacts: WHERE deleted_at IS NULL
• Join contacts: JOIN contacts c ON meetings.contact_id = c.id
• Date ranges: WHERE date >= '2025-01-01' AND date < '2025-02-01'
• JSON array search: WHERE 'tag' = ANY(tags)
• Limit results: LIMIT 20

IMPORTANT: Only SELECT queries allowed. Use specific tools when available.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SELECT SQL query to execute"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "search_contacts",
        "description": "Search for contacts by name, company, or any field. Returns matching contacts with their details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (name, company, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_contact_history",
        "description": "Get full interaction history with a contact: meetings, emails, calendar events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name of the contact"
                }
            },
            "required": ["contact_name"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task/to-do item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title"
                },
                "description": {
                    "type": "string",
                    "description": "Optional description"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "default": "medium"
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "create_reflection",
        "description": "Create or append to a reflection on a topic. If topic_key matches existing, content is appended.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Reflection title"
                },
                "content": {
                    "type": "string",
                    "description": "The reflection content (markdown supported)"
                },
                "topic_key": {
                    "type": "string",
                    "description": "Topic key for grouping (e.g., 'career-development', 'project-jarvis')"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization"
                }
            },
            "required": ["title", "content", "topic_key"]
        }
    },
    {
        "name": "get_upcoming_events",
        "description": "Get upcoming calendar events for the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead",
                    "default": 7
                }
            },
            "required": []
        }
    },
    {
        "name": "get_recent_emails",
        "description": """Get recent emails from the database, optionally filtered by sender or subject.
This returns emails that have been synced to the knowledge base.
Use include_body=true to get full email content (not just snippets).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look back N days",
                    "default": 7
                },
                "from_email": {
                    "type": "string",
                    "description": "Filter by sender email/name"
                },
                "subject_contains": {
                    "type": "string",
                    "description": "Filter by subject keyword"
                },
                "include_body": {
                    "type": "boolean",
                    "description": "Include full email body text (not just snippet)",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_email_by_id",
        "description": """Get full details of a specific email by its ID.
Returns the complete email including full body text.
Use this after get_recent_emails to read full content of a specific email.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The email ID (UUID from the database)"
                }
            },
            "required": ["email_id"]
        }
    },
    {
        "name": "search_emails_live",
        "description": """Search Gmail inbox in real-time using Gmail's search syntax.
Use this for:
- Finding very recent emails (last few hours)
- Complex searches that need Gmail's full search power
- When database search doesn't find what user is looking for

Gmail search supports: from:, to:, subject:, has:attachment, after:, before:, is:unread, etc.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (e.g., 'from:john subject:meeting after:2025/01/01')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum emails to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_tasks",
        "description": "Get tasks, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "all"],
                    "default": "pending"
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to complete"
                },
                "task_title": {
                    "type": "string",
                    "description": "Or search by task title (partial match)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_reflections",
        "description": "Get reflections, optionally filtered by topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic_key": {
                    "type": "string",
                    "description": "Filter by topic key"
                },
                "search": {
                    "type": "string",
                    "description": "Search in title/content"
                },
                "limit": {
                    "type": "integer",
                    "default": 5
                }
            },
            "required": []
        }
    },
    # =========================================================================
    # PHASE 1 ADDITIONS - More useful tools
    # =========================================================================
    {
        "name": "search_transcripts",
        "description": "Search through raw voice memo transcripts for specific content or keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to find in transcripts"
                },
                "days": {
                    "type": "integer",
                    "description": "Look back N days (default: 30)",
                    "default": 30
                },
                "limit": {
                    "type": "integer",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_journals",
        "description": "Get journal entries. Use this to see what happened on specific days, moods, accomplishments, tomorrow's focus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Get journals from last N days",
                    "default": 7
                },
                "date": {
                    "type": "string",
                    "description": "Specific date in YYYY-MM-DD format"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_meetings",
        "description": "Search meetings by topic, person, or content. Use this to find past discussions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (topic, person name, etc.)"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Filter by contact name"
                },
                "days": {
                    "type": "integer",
                    "description": "Look back N days",
                    "default": 90
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "update_task",
        "description": "Update a task's priority, due date, or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_title": {
                    "type": "string",
                    "description": "Task title to find (partial match)"
                },
                "task_id": {
                    "type": "string",
                    "description": "Or task ID directly"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "New priority"
                },
                "due_date": {
                    "type": "string",
                    "description": "New due date (YYYY-MM-DD)"
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "New status"
                }
            },
            "required": []
        }
    },
    {
        "name": "add_contact_note",
        "description": "Add a note to a contact's profile. Good for remembering personal details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Contact name to add note to"
                },
                "note": {
                    "type": "string",
                    "description": "Note to add (will be appended to existing notes)"
                }
            },
            "required": ["contact_name", "note"]
        }
    },
    {
        "name": "create_contact",
        "description": "Create a new contact in the CRM. Use this when the user mentions meeting someone new or wants to add a contact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {
                    "type": "string",
                    "description": "First name"
                },
                "last_name": {
                    "type": "string",
                    "description": "Last name"
                },
                "email": {
                    "type": "string",
                    "description": "Email address"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number"
                },
                "company": {
                    "type": "string",
                    "description": "Company name"
                },
                "job_title": {
                    "type": "string",
                    "description": "Job title"
                },
                "notes": {
                    "type": "string",
                    "description": "Initial notes about this contact"
                }
            },
            "required": ["first_name"]
        }
    },
    {
        "name": "update_contact",
        "description": "Update an existing contact's information (email, company, phone, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name of contact to update"
                },
                "contact_id": {
                    "type": "string",
                    "description": "Or contact ID directly"
                },
                "email": {
                    "type": "string",
                    "description": "New email"
                },
                "phone": {
                    "type": "string",
                    "description": "New phone"
                },
                "company": {
                    "type": "string",
                    "description": "New company"
                },
                "job_title": {
                    "type": "string",
                    "description": "New job title"
                },
                "birthday": {
                    "type": "string",
                    "description": "Birthday (YYYY-MM-DD)"
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "LinkedIn URL"
                },
                "location": {
                    "type": "string",
                    "description": "Location/city"
                }
            },
            "required": []
        }
    },
    {
        "name": "create_meeting",
        "description": "Log a meeting or conversation. Use this when the user says they met with someone or had a call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Meeting title (e.g., 'Coffee with John')"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Name of person met with (will auto-link to contact if found)"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of what was discussed"
                },
                "date": {
                    "type": "string",
                    "description": "Date of meeting (YYYY-MM-DD or 'today', 'yesterday')"
                },
                "location": {
                    "type": "string",
                    "description": "Where the meeting took place"
                },
                "topics_discussed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of topics discussed"
                },
                "follow_up_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Follow-up actions or tasks"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "delete_task",
        "description": """Delete a task. Use this when the user wants to remove a task that's no longer needed.

⚠️ REQUIRES USER CONFIRMATION before execution.
Always confirm with the user before deleting: "Are you sure you want to delete the task '[task title]'?"
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_title": {
                    "type": "string",
                    "description": "Task title to find (partial match)"
                },
                "task_id": {
                    "type": "string",
                    "description": "Or task ID directly"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "REQUIRED: Must be true to execute. Ask user to confirm first!"
                }
            },
            "required": ["user_confirmed"]
        }
    },
    {
        "name": "summarize_activity",
        "description": "Get a summary of recent activity: meetings, tasks completed, reflections, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "this_week", "last_week"],
                    "default": "today"
                }
            },
            "required": []
        }
    },
    {
        "name": "who_to_contact",
        "description": "Find contacts you haven't interacted with recently. Good for maintaining relationships.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_inactive": {
                    "type": "integer",
                    "description": "Days since last interaction",
                    "default": 30
                },
                "limit": {
                    "type": "integer",
                    "default": 5
                }
            },
            "required": []
        }
    },
    # Location & Timezone
    {
        "name": "set_user_location",
        "description": """Set the user's location and timezone. Use this when the user says things like:
- 'I'm in Jakarta' / 'I'm now in Singapore' / 'I moved to Berlin'
- 'My timezone is Europe/Istanbul' / 'Set my timezone to PST'
- 'I'm traveling to Tokyo'

This updates their stored location for all future time-related operations.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g., 'Jakarta', 'Istanbul', 'New York')"
                },
                "country": {
                    "type": "string",
                    "description": "Country name (optional)"
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone (e.g., 'Asia/Jakarta', 'Europe/Istanbul'). If not provided, will be inferred from city."
                }
            },
            "required": ["city"]
        }
    },
    {
        "name": "get_user_location",
        "description": "Get the user's current location and timezone. Use this when you need to know where the user is, their timezone, or local time for scheduling.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time in the user's timezone. Use this before any time-related questions or scheduling.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # =========================================================================
    # BOOKS & HIGHLIGHTS - Reading data access
    # =========================================================================
    {
        "name": "get_books",
        "description": """Get books from the reading list. Filter by status, author, or search.
Use this when user asks about:
- Books they're reading or have read
- Reading progress
- Book recommendations from their list
- What they finished recently""",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["Reading", "Finished", "To Read", "Abandoned", "all"],
                    "description": "Filter by reading status",
                    "default": "all"
                },
                "author": {
                    "type": "string",
                    "description": "Filter by author name (partial match)"
                },
                "search": {
                    "type": "string",
                    "description": "Search in title, author, notes"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_highlights",
        "description": """Get book highlights and annotations.
Use this when user asks about:
- Their book highlights or favorite quotes
- Notes from a specific book
- Ideas or insights they saved while reading
- What they underlined/marked in books""",
        "input_schema": {
            "type": "object",
            "properties": {
                "book_title": {
                    "type": "string",
                    "description": "Filter by book title (partial match)"
                },
                "search": {
                    "type": "string",
                    "description": "Search in highlight content or notes"
                },
                "favorites_only": {
                    "type": "boolean",
                    "description": "Only return favorite/starred highlights",
                    "default": False
                },
                "days": {
                    "type": "integer",
                    "description": "Get highlights from last N days",
                    "default": 90
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "search_reading_notes",
        "description": """Search across all books and highlights for ideas, quotes, or topics.
Great for finding insights across multiple books on a topic.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to find in books, highlights, and notes"
                },
                "limit": {
                    "type": "integer",
                    "default": 15
                }
            },
            "required": ["query"]
        }
    },
    # =========================================================================
    # RECENT VOICE MEMO CONTEXT - For follow-up questions
    # =========================================================================
    {
        "name": "get_recent_voice_memo",
        "description": """Get the most recently processed voice memo and what was created from it.
Use this when user asks things like:
- 'What did I just say?'
- 'Can you summarize what I just recorded?'
- 'What did you create from that?'
- 'Show me the meeting/journal/tasks you just made'
- Questions about their last recording""",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_transcript": {
                    "type": "boolean",
                    "description": "Include full transcript text",
                    "default": True
                }
            },
            "required": []
        }
    },
    # =========================================================================
    # CALENDAR CREATION - Create events in Google Calendar
    # =========================================================================
    {
        "name": "create_calendar_event",
        "description": """Create a new event in the user's Google Calendar.
Use this when user asks to:
- Schedule a meeting
- Create a calendar event
- Block time for something
- Set up a reminder event
- Add something to their calendar

TIME RULES (CRITICAL):
1. ALWAYS call get_current_time FIRST to get the user's current date/time and timezone
2. Use the USER'S TIMEZONE from get_current_time for all calculations (NOT UTC)
3. SNAP times to 30-minute intervals: :00 or :30 only
   - "in an hour" at 1:43pm → start at 2:30pm or 3:00pm (next half-hour after 2:43)
   - "at 3" → 3:00pm
   - "in 30 minutes" at 2:10pm → start at 2:30pm
4. DEFAULT DURATION: 30 minutes unless user specifies
   - "meeting at 3pm" → 3:00pm - 3:30pm
   - "1 hour meeting" → specified start - 1 hour later
   - "meeting from 2-4" → 2:00pm - 4:00pm

NOTE: The sync service will apply the user's timezone. Just provide clean ISO times.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/summary"
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format. MUST be snapped to :00 or :30 (e.g., '2025-01-20T14:00:00' or '2025-01-20T14:30:00')"
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format. Default 30min after start. MUST be snapped to :00 or :30"
                },
                "description": {
                    "type": "string",
                    "description": "Event description/notes (optional)"
                },
                "location": {
                    "type": "string",
                    "description": "Event location (optional)"
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses (optional)"
                }
            },
            "required": ["title", "start_time", "end_time"]
        }
    },
    # =========================================================================
    # CALENDAR UPDATES - Reschedule existing events
    # =========================================================================
    {
        "name": "update_calendar_event",
        "description": """Update/reschedule an existing calendar event.
Use this when user asks to:
- Reschedule a meeting
- Move a calendar event to a different time
- Change meeting details (location, description)
- Add a reason for rescheduling

First use query_database to find the event_id from calendar_events table using the event title or time.
Then update it with new details.

IMPORTANT: 
- This notifies all attendees by default
- Add reschedule reason to description field
- Only the event organizer can reschedule""",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event ID (query calendar_events.google_event_id to find this)"
                },
                "title": {
                    "type": "string",
                    "description": "New event title (optional)"
                },
                "start_time": {
                    "type": "string",
                    "description": "New start time in ISO 8601 format (optional)"
                },
                "end_time": {
                    "type": "string",
                    "description": "New end time in ISO 8601 format (optional)"
                },
                "description": {
                    "type": "string",
                    "description": "Updated description - use this to add reschedule reason like 'Rescheduled due to conflict' (optional)"
                },
                "location": {
                    "type": "string",
                    "description": "New location (optional)"
                },
                "send_updates": {
                    "type": "string",
                    "enum": ["all", "externalOnly", "none"],
                    "description": "Who to notify about the update (default: 'all')"
                }
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "decline_calendar_event",
        "description": """Decline a calendar invitation that someone else sent you.
Use this when user asks to:
- Decline a meeting invitation
- Say no to an event
- Suggest an alternative time for a meeting they were invited to

First use query_database to find the event_id from calendar_events table.
Optionally include a comment with the decline (e.g., alternative time suggestion).

NOTE: This is for events you're INVITED to, not events you organized.
To cancel your own event, use update_calendar_event to change the status.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Google Calendar event ID (query calendar_events.google_event_id to find this)"
                },
                "comment": {
                    "type": "string",
                    "description": "Optional message to send with decline (e.g., 'Can we do 3pm instead?')"
                }
            },
            "required": ["event_id"]
        }
    },
    # =========================================================================
    # EMAIL DRAFTS - Create drafts that sync with Gmail, send only on confirm
    # =========================================================================
    {
        "name": "create_email_draft",
        "description": """Create an email draft that saves to Gmail Drafts folder.
The draft will be visible in the user's Gmail immediately.

Use when user asks to:
- Write/compose an email
- Draft an email to someone
- Prepare an email for review
- Email [person] (always create draft first)

After creating, show the user the draft details and ask if they want to send it.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "to_name": {
                    "type": "string",
                    "description": "Recipient name (used to look up email if 'to' not provided)"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients (comma-separated emails)"
                },
                "reply_to_message_id": {
                    "type": "string",
                    "description": "Gmail message ID if replying to an existing thread"
                }
            },
            "required": ["subject", "body"]
        }
    },
    {
        "name": "list_email_drafts",
        "description": """List all email drafts from the user's Gmail Drafts folder.
Use this to see pending drafts that haven't been sent yet.
Works both for drafts created by Jarvis and drafts created manually in Gmail.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum drafts to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_email_draft",
        "description": """Get the full content of a specific email draft.
Use this to show the user what a draft contains before sending.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "The Gmail draft ID"
                }
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "send_email_draft",
        "description": """Send an existing draft from Gmail.
ONLY use this AFTER user explicitly confirms they want to send.
This removes the draft from Drafts folder and sends it.

CRITICAL: Never call without explicit user confirmation like 'yes send it' or 'send'.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "The Gmail draft ID to send"
                }
            },
            "required": ["draft_id"]
        }
    },
    {
        "name": "delete_email_draft",
        "description": """Delete a draft from Gmail permanently.
Use when user wants to discard a draft.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "The Gmail draft ID to delete"
                }
            },
            "required": ["draft_id"]
        }
    },
    # =========================================================================
    # BEEPER MESSAGING - WhatsApp, Telegram, LinkedIn, etc.
    # =========================================================================
    {
        "name": "get_beeper_inbox",
        "description": """Get the Beeper inbox - chats that need your attention across WhatsApp, LinkedIn, Telegram, etc.

Uses inbox-zero workflow:
- 'needs_response': DMs where the other person sent the last message (awaiting your reply)
- 'other_active': DMs where you sent the last message (ball in their court)

Use this when user asks about:
- 'Who do I need to reply to?'
- 'Any unread messages?'
- 'What messages need my attention?'
- 'Show my WhatsApp/LinkedIn/Telegram messages'""",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_groups": {
                    "type": "boolean",
                    "description": "Include group chats (usually lower priority)",
                    "default": False
                },
                "limit": {
                    "type": "integer",
                    "description": "Max chats per category",
                    "default": 10
                }
            },
            "required": []
        }
    },
    {
        "name": "get_beeper_chat_messages",
        "description": """Get messages from a specific Beeper chat.

Use this to read the conversation history with a specific person.
First use get_beeper_inbox or search_beeper_messages to find the beeper_chat_id.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID (e.g., '!abc123:beeper.local')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to retrieve",
                    "default": 20
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "search_beeper_messages",
        "description": """Search across all Beeper message history.

Use this to find specific conversations or information mentioned in messages.
Supports full-text search across WhatsApp, LinkedIn, Telegram, etc.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "platform": {
                    "type": "string",
                    "enum": ["whatsapp", "linkedin", "telegram"],
                    "description": "Filter by platform (optional)"
                },
                "contact_name": {
                    "type": "string",
                    "description": "Filter by contact name (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_beeper_contact_messages",
        "description": """Get all message history with a specific contact across all platforms.

Use when user asks:
- 'What did John send me?'
- 'Show messages with Sarah'
- 'When did I last talk to [name]?'

First searches contacts to find the contact_id, then gets all messages.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name of the contact to get messages with"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max messages to return",
                    "default": 30
                }
            },
            "required": ["contact_name"]
        }
    },
    {
        "name": "archive_beeper_chat",
        "description": """Archive a Beeper chat (mark as handled in inbox-zero workflow).

Use when user says they've dealt with a message or want to dismiss it from inbox view.
Does NOT delete the chat - just marks it as archived.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to archive"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "send_beeper_message",
        "description": """Send a message to a Beeper chat (WhatsApp, Telegram, LinkedIn, etc.).

⚠️ CRITICAL TWO-STEP PROCESS:
STEP 1 - Draft and confirm: Show user the message and ask "Shall I send it?"
STEP 2 - After user confirms: CALL THIS TOOL with user_confirmed=true

When user says "yes", "send it", "go ahead" → YOU MUST CALL THIS TOOL NOW

DO NOT just say "message sent" - you MUST actually call this tool to send the message.
Without calling this tool, the message will NOT be sent.

Use when user wants to:
- Reply to a message they received
- Send a new message to a contact
- Respond to someone in their inbox

NEVER send without user explicitly confirming the message content and recipient.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to send to (get from get_beeper_inbox or get_beeper_chat_messages)"
                },
                "content": {
                    "type": "string",
                    "description": "The message text to send"
                },
                "reply_to_event_id": {
                    "type": "string",
                    "description": "Optional: Message ID to reply to (for threaded replies)"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "REQUIRED: Must be true - indicates user has explicitly confirmed sending this message"
                }
            },
            "required": ["beeper_chat_id", "content", "user_confirmed"]
        }
    },
    {
        "name": "mark_beeper_read",
        "description": """Mark all messages in a Beeper chat as read.

Use when:
- User has seen/acknowledged a conversation
- User wants to clear unread indicators
- After reading a chat and user doesn't need to respond""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to mark as read"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "unarchive_beeper_chat",
        "description": """Unarchive a Beeper chat (bring it back to inbox).

Use when user wants to revisit an archived conversation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "beeper_chat_id": {
                    "type": "string",
                    "description": "The chat ID to unarchive"
                }
            },
            "required": ["beeper_chat_id"]
        }
    },
    {
        "name": "get_beeper_status",
        "description": """Check Beeper connectivity status.

Use when:
- User asks if Beeper is connected/working
- Need to verify messaging is available
- Troubleshooting message delivery""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # =========================================================================
    # MEMORY MANAGEMENT TOOLS
    # =========================================================================
    {
        "name": "remember_fact",
        "description": """Store a fact about the user in long-term memory.

Use when user says things like:
- "Remember that I'm vegetarian"
- "My GitHub is github.com/username"
- "I was employee #1 at Algenie"
- "Remember my favorite coffee is flat white"

This stores the information for future conversations.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The fact to remember (e.g., 'User is vegetarian', 'User's GitHub is github.com/x')"
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "preference", "relationship"],
                    "description": "Type of memory: fact (general info), preference (likes/dislikes), relationship (about people)",
                    "default": "fact"
                }
            },
            "required": ["fact"]
        }
    },
    {
        "name": "correct_memory",
        "description": """Correct something Jarvis remembers incorrectly.

Use when user says things like:
- "That's wrong, I was actually employee #1"
- "No, my title is CEO not CTO"
- "Actually I prefer mornings not evenings"

First search for the incorrect memory, then correct it.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "incorrect_info": {
                    "type": "string",
                    "description": "What Jarvis got wrong (for finding the memory)"
                },
                "correct_info": {
                    "type": "string",
                    "description": "The corrected fact"
                }
            },
            "required": ["incorrect_info", "correct_info"]
        }
    },
    {
        "name": "search_memories",
        "description": """Search what Jarvis remembers about a topic.

Use when user asks:
- "What do you know about me?"
- "What do you remember about Algenie?"
- "Do you know my preferences?"
- "List all fact/preference/insight memories"

Returns memories with metadata including:
- id: Unique memory ID (for deletion)
- content: The actual memory text
- type: fact, preference, insight, relationship, interaction
- source: Origin (voice memo filename, chat, api, beeper, etc.)
- created_at: When the memory was created

You can filter by type using the 'type' parameter.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in memories"
                },
                "type": {
                    "type": "string",
                    "enum": ["fact", "preference", "insight", "relationship", "interaction"],
                    "description": "Filter by memory type"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum memories to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "forget_memory",
        "description": """Delete a specific memory by ID or search query.

PREFERRED: Use memory_id when you have it (from search_memories results).
ALTERNATIVE: Use query to search and delete matching memories.

Use when user explicitly asks to forget something:
- "Forget that I like coffee"
- "Remove that memory about my old job"
- "Delete memory ID xyz"

IMPORTANT: After calling this, VERIFY the deletion worked by checking the returned status.
Do NOT tell the user you deleted something unless status is "deleted".""",
        "input_schema": {
            "type": "object",
            "properties": {
                "memory_id": {
                    "type": "string",
                    "description": "Specific memory ID to delete (preferred)"
                },
                "query": {
                    "type": "string",
                    "description": "Search query to find and delete matching memories"
                }
            }
        }
    },
    {
        "name": "search_conversations",
        "description": """Search through past conversation history with Aaron.

Use when user asks:
- "What did we talk about last week?"
- "Did I mention anything about X?"
- "When did I tell you about Y?"
- "What did I say about my trip?"
- Any question about past conversations

Returns relevant conversation excerpts from Letta's archival memory.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in past conversations"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_documents",
        "description": """Search Aaron's personal documents (CV, profiles, applications, notes).

Use when user asks:
- "What's in my CV?"
- "What does my profile say about my experience?"
- "What's my work history?"
- "Find my application to X"
- Any question about stored personal documents

Returns relevant content from stored documents.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in documents"
                },
                "document_type": {
                    "type": "string",
                    "description": "Filter by type: cv, profile, application, notes, other",
                    "enum": ["cv", "profile", "application", "notes", "other"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum documents to return",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_document_content",
        "description": """Get the full content of a specific document type.

Use when user asks for complete document content:
- "Show me my full CV"
- "What's in my LinkedIn profile?"
- "Read my professional bio"

Returns the full text content.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "description": "Type of document to retrieve",
                    "enum": ["cv", "profile", "application", "notes"]
                },
                "title": {
                    "type": "string",
                    "description": "Optional: specific document title"
                }
            },
            "required": ["document_type"]
        }
    },
    # =========================================================================
    # APPLICATIONS - Track grants, fellowships, programs
    # =========================================================================
    {
        "name": "get_applications",
        "description": """Get a list of grant/fellowship/program applications.

Use when user asks:
- "What applications do I have?"
- "Show my pending applications"
- "What's the deadline for my grants?"
- "List my fellowship applications"

Returns applications with status, deadline, and details.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["Not Started", "Researching", "In Progress", "Applied", "Accepted"],
                    "description": "Filter by status"
                },
                "application_type": {
                    "type": "string",
                    "enum": ["Grant", "Fellowship", "Program", "Accelerator", "Residency"],
                    "description": "Filter by type"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum applications to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "search_applications",
        "description": """Search applications by name, institution, or content.

Use when user asks:
- "Find applications about longevity"
- "What grants from EIC?"
- "Search for fellowship with deadline in March"

Returns matching applications with full details.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to match in name, institution, context, or content"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_application_content",
        "description": """Get the full content of a specific application (answers, essays, etc.).

Use when user asks:
- "Show me my EIC application"
- "What did I write for the Y Combinator application?"
- "Read my grant proposal for X"

Returns the complete application text.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "The application UUID"
                },
                "application_name": {
                    "type": "string",
                    "description": "Application name (if ID not known)"
                }
            },
            "required": []
        }
    },
    # =========================================================================
    # LINKEDIN POSTS - Content planning and tracking
    # =========================================================================
    {
        "name": "get_linkedin_posts",
        "description": """Get LinkedIn posts and content ideas.

Use when user asks:
- "What LinkedIn posts do I have?"
- "Show my posted content"
- "What post ideas do I have?"
- "What did I post about longevity?"

Returns posts with status, pillar, and engagement.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["Idea", "Posted"],
                    "description": "Filter by status"
                },
                "pillar": {
                    "type": "string",
                    "enum": ["Personal", "Longevity", "Algenie"],
                    "description": "Filter by content pillar"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum posts to return",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "search_linkedin_posts",
        "description": """Search LinkedIn posts by title or content.

Use when user asks:
- "Find my posts about AI"
- "What did I write about longevity?"
- "Search my LinkedIn for meditation content"

Returns matching posts with full content.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term to match in title or content"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_linkedin_post_content",
        "description": """Get the full content of a specific LinkedIn post.

Use when user asks to:
- Read a specific post fully
- Get the complete text of a post idea

Returns the full post text.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "The post UUID"
                },
                "post_title": {
                    "type": "string",
                    "description": "Post title (if ID not known)"
                }
            },
            "required": []
        }
    },
    # =========================================================================
    # DATABASE SCHEMA TOOLS - For creating/modifying database structure
    # =========================================================================
    {
        "name": "list_database_tables",
        "description": """List all tables in the database with their column information.

Use when:
- User asks what data is available
- Need to understand database structure
- Planning new table creation
- Checking if a table exists

Returns list of tables with columns and types.""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_database_table",
        "description": """Create a new table in the database.

⚠️ REQUIRES USER CONFIRMATION before execution.

Use when user wants to:
- Store new types of data (e.g., research results, new entity types)
- Create a table for a specific project
- Set up storage for imported data

Guidelines:
- Table names should be lowercase with underscores (e.g., linkedin_research_results)
- Always include: id (uuid primary key), created_at (timestamptz)
- Use appropriate column types: text, integer, jsonb, boolean, date, timestamptz, text[]

ALWAYS confirm the table structure with user before creating.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (lowercase, underscores)"
                },
                "columns": {
                    "type": "array",
                    "description": "List of column definitions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Column name"},
                            "type": {"type": "string", "description": "PostgreSQL type: text, integer, bigint, boolean, date, timestamptz, uuid, jsonb, text[]"},
                            "nullable": {"type": "boolean", "description": "Allow NULL values (default: true)"},
                            "default": {"type": "string", "description": "Default value (optional)"},
                            "unique": {"type": "boolean", "description": "Unique constraint (default: false)"}
                        },
                        "required": ["name", "type"]
                    }
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "REQUIRED: Must be true to execute. Ask user to confirm first!"
                }
            },
            "required": ["table_name", "columns", "user_confirmed"]
        }
    },
    {
        "name": "add_column_to_table",
        "description": """Add a new column to an existing table.

⚠️ REQUIRES USER CONFIRMATION before execution.

Use when:
- Need to extend a table with new fields
- User wants to track additional data
- Adding metadata columns""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the existing table"
                },
                "column_name": {
                    "type": "string",
                    "description": "Name of the new column"
                },
                "column_type": {
                    "type": "string",
                    "description": "PostgreSQL type: text, integer, boolean, date, timestamptz, uuid, jsonb, text[]"
                },
                "nullable": {
                    "type": "boolean",
                    "description": "Allow NULL values (default: true)"
                },
                "default_value": {
                    "type": "string",
                    "description": "Default value for existing rows (optional)"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "REQUIRED: Must be true to execute. Ask user to confirm first!"
                }
            },
            "required": ["table_name", "column_name", "column_type", "user_confirmed"]
        }
    },
    {
        "name": "insert_data_batch",
        "description": """Insert multiple rows of data into a table.

Use when:
- Storing research results
- Importing data from external sources
- Batch-creating records

Returns count of inserted rows.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Target table name"
                },
                "rows": {
                    "type": "array",
                    "description": "Array of objects to insert (each object is a row)",
                    "items": {
                        "type": "object"
                    }
                }
            },
            "required": ["table_name", "rows"]
        }
    },
    {
        "name": "get_database_backup_status",
        "description": """Check the database backup status and recent backups.

Use when:
- User asks about data safety
- Before making significant changes
- Checking what can be restored""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "backup_table",
        "description": """Create a backup of a specific table to storage.

Use before making destructive changes or when user wants to snapshot data.
Backs up to Supabase Storage bucket.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table to backup"
                }
            },
            "required": ["table_name"]
        }
    }
]


# =============================================================================
# RESEARCH TOOLS (Added dynamically to avoid module-load circular imports)
# =============================================================================

def get_all_tools() -> List[Dict[str, Any]]:
    """Get all tools including dynamically loaded research tools."""
    from app.features.research import RESEARCH_TOOLS
    return TOOLS + RESEARCH_TOOLS


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any], last_user_message: str = "") -> Dict[str, Any]:
    """Execute a tool and return the result.
    
    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool parameters
        last_user_message: The most recent user message (for confirmation checks)
    """
    try:
        if tool_name == "execute_sql_write":
            return _execute_sql_write(tool_input)
        elif tool_name == "query_database":
            return _query_database(tool_input.get("sql", ""))
        elif tool_name == "search_contacts":
            return _search_contacts(tool_input.get("query", ""), tool_input.get("limit", 5))
        elif tool_name == "get_contact_history":
            return _get_contact_history(tool_input.get("contact_name", ""))
        elif tool_name == "create_task":
            return _create_task(tool_input)
        elif tool_name == "create_reflection":
            return _create_reflection(tool_input)
        elif tool_name == "get_upcoming_events":
            return _get_upcoming_events(tool_input.get("days", 7))
        elif tool_name == "get_recent_emails":
            return _get_recent_emails(tool_input)
        elif tool_name == "get_email_by_id":
            return _get_email_by_id(tool_input)
        elif tool_name == "search_emails_live":
            return _search_emails_live(tool_input)
        elif tool_name == "get_tasks":
            return _get_tasks(tool_input.get("status", "pending"), tool_input.get("limit", 10))
        elif tool_name == "complete_task":
            return _complete_task(tool_input)
        elif tool_name == "get_reflections":
            return _get_reflections(tool_input)
        # Phase 1 additions
        elif tool_name == "search_transcripts":
            return _search_transcripts(tool_input)
        elif tool_name == "get_journals":
            return _get_journals(tool_input)
        elif tool_name == "search_meetings":
            return _search_meetings(tool_input)
        elif tool_name == "update_task":
            return _update_task(tool_input)
        elif tool_name == "add_contact_note":
            return _add_contact_note(tool_input)
        # New tools for full CRUD
        elif tool_name == "create_contact":
            return _create_contact(tool_input)
        elif tool_name == "update_contact":
            return _update_contact(tool_input)
        elif tool_name == "create_meeting":
            return _create_meeting(tool_input)
        elif tool_name == "delete_task":
            return _delete_task(tool_input)
        elif tool_name == "summarize_activity":
            return _summarize_activity(tool_input.get("period", "today"))
        elif tool_name == "who_to_contact":
            return _who_to_contact(tool_input)
        # Location & Timezone
        elif tool_name == "set_user_location":
            return _set_user_location(tool_input)
        elif tool_name == "get_user_location":
            return _get_user_location()
        elif tool_name == "get_current_time":
            return _get_current_time()
        # Books & Highlights
        elif tool_name == "get_books":
            return _get_books(tool_input)
        elif tool_name == "get_highlights":
            return _get_highlights(tool_input)
        elif tool_name == "search_reading_notes":
            return _search_reading_notes(tool_input)
        # Recent voice memo context
        elif tool_name == "get_recent_voice_memo":
            return _get_recent_voice_memo(tool_input)
        # Calendar creation
        elif tool_name == "create_calendar_event":
            return _create_calendar_event(tool_input)
        elif tool_name == "update_calendar_event":
            return _update_calendar_event(tool_input)
        elif tool_name == "decline_calendar_event":
            return _decline_calendar_event(tool_input)
        # Email drafts
        elif tool_name == "create_email_draft":
            return _create_email_draft(tool_input)
        elif tool_name == "list_email_drafts":
            return _list_email_drafts(tool_input)
        elif tool_name == "get_email_draft":
            return _get_email_draft(tool_input)
        elif tool_name == "send_email_draft":
            return _send_email_draft(tool_input)
        elif tool_name == "delete_email_draft":
            return _delete_email_draft(tool_input)
        # Beeper messaging
        elif tool_name == "get_beeper_inbox":
            return _get_beeper_inbox(tool_input)
        elif tool_name == "get_beeper_chat_messages":
            return _get_beeper_chat_messages(tool_input)
        elif tool_name == "search_beeper_messages":
            return _search_beeper_messages(tool_input)
        elif tool_name == "get_beeper_contact_messages":
            return _get_beeper_contact_messages(tool_input)
        elif tool_name == "archive_beeper_chat":
            return _archive_beeper_chat(tool_input)
        elif tool_name == "send_beeper_message":
            logger.info(f"📤 SEND_BEEPER_MESSAGE called with: {tool_input}")
            # CRITICAL: Verify actual user confirmation from their message
            tool_input["_last_user_message"] = last_user_message
            result = _send_beeper_message(tool_input)
            logger.info(f"📤 SEND_BEEPER_MESSAGE result: {result}")
            return result
        elif tool_name == "mark_beeper_read":
            return _mark_beeper_read(tool_input)
        elif tool_name == "unarchive_beeper_chat":
            return _unarchive_beeper_chat(tool_input)
        elif tool_name == "get_beeper_status":
            return _get_beeper_status(tool_input)
        # Memory management tools
        elif tool_name == "remember_fact":
            return _remember_fact(tool_input)
        elif tool_name == "correct_memory":
            return _correct_memory(tool_input)
        elif tool_name == "search_memories":
            return _search_memories(tool_input)
        elif tool_name == "forget_memory":
            return _forget_memory(tool_input)
        elif tool_name == "search_conversations":
            return _run_async(_search_conversations(tool_input))
        # Document tools
        elif tool_name == "search_documents":
            return _run_async(_search_documents(tool_input))
        elif tool_name == "get_document_content":
            return _run_async(_get_document_content(tool_input))
        # Applications tools
        elif tool_name == "get_applications":
            return _get_applications(tool_input)
        elif tool_name == "search_applications":
            return _search_applications(tool_input)
        elif tool_name == "get_application_content":
            return _get_application_content(tool_input)
        # LinkedIn Posts tools
        elif tool_name == "get_linkedin_posts":
            return _get_linkedin_posts(tool_input)
        elif tool_name == "search_linkedin_posts":
            return _search_linkedin_posts(tool_input)
        elif tool_name == "get_linkedin_post_content":
            return _get_linkedin_post_content(tool_input)
        # Database schema tools
        elif tool_name == "list_database_tables":
            return _list_database_tables(tool_input)
        elif tool_name == "create_database_table":
            return _create_database_table(tool_input)
        elif tool_name == "add_column_to_table":
            return _add_column_to_table(tool_input)
        elif tool_name == "insert_data_batch":
            return _insert_data_batch(tool_input)
        elif tool_name == "get_database_backup_status":
            return _get_database_backup_status(tool_input)
        elif tool_name == "backup_table":
            return _backup_table(tool_input)
        # Research tools (LinkedIn via Bright Data, Web Search via Brave)
        elif tool_name in ("linkedin_get_profiles", "linkedin_search_people", 
                          "linkedin_get_company", "linkedin_get_company_employees",
                          "linkedin_get_company_jobs", "web_search", "web_search_news",
                          "get_research_status"):
            return _run_async(_handle_research_tool(tool_name, tool_input))
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.error(f"Tool execution error [{tool_name}]: {e}")
        return {"error": str(e)}


def _execute_sql_write(input: Dict) -> Dict[str, Any]:
    """Execute a write SQL statement with confirmation requirement.
    
    This allows UPDATE, INSERT, DELETE operations but REQUIRES user confirmation.
    """
    sql = input.get("sql", "").strip()
    user_confirmed = input.get("user_confirmed", False)
    description = input.get("description", "")
    
    if not sql:
        return {"error": "SQL statement is required"}
    
    sql_upper = sql.upper()
    
    # Determine operation type
    if sql_upper.startswith("UPDATE"):
        operation = "UPDATE"
    elif sql_upper.startswith("INSERT"):
        operation = "INSERT"
    elif sql_upper.startswith("DELETE"):
        operation = "DELETE"
    else:
        return {"error": "Only UPDATE, INSERT, or DELETE statements are allowed. For SELECT, use query_database."}
    
    # Block extremely dangerous SQL commands (using word boundaries to avoid false positives)
    # e.g., "GRANT" in "application_type='Grant'" should NOT be blocked
    import re
    dangerous_patterns = [
        r'\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)',
        r'\bTRUNCATE\s+',
        r'\bALTER\s+(TABLE|DATABASE)',
        r'^\s*GRANT\s+',  # Only block GRANT at start of statement
        r'^\s*REVOKE\s+',  # Only block REVOKE at start of statement
        r'\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW|USER)',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_upper):
            return {"error": f"Query contains forbidden SQL command pattern: {pattern}"}
    
    # Extract table name
    import re
    if operation == "UPDATE":
        table_match = re.search(r'UPDATE\s+(\w+)', sql, re.IGNORECASE)
    elif operation == "INSERT":
        table_match = re.search(r'INTO\s+(\w+)', sql, re.IGNORECASE)
    else:  # DELETE
        table_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
    
    if not table_match:
        return {"error": "Could not parse table name from query"}
    
    table_name = table_match.group(1).lower()
    
    # Tables that can be modified
    writable_tables = [
        "contacts", "meetings", "tasks", "journals", "reflections",
        "applications", "linkedin_posts", "books", "highlights"
    ]
    
    # Tables that should NOT be modified (sync-managed)
    readonly_tables = [
        "calendar_events", "emails", "beeper_chats", "beeper_messages",
        "transcripts", "sync_logs", "sync_state", "pipeline_logs"
    ]
    
    if table_name in readonly_tables:
        return {
            "error": f"Table '{table_name}' is read-only (managed by sync services)",
            "hint": "This data is synced from external sources and should not be modified directly."
        }
    
    if table_name not in writable_tables:
        return {
            "error": f"Table '{table_name}' is not in the allowed write list",
            "allowed_tables": writable_tables
        }
    
    # REQUIRE CONFIRMATION
    if not user_confirmed:
        return {
            "status": "confirmation_required",
            "operation": operation,
            "table": table_name,
            "sql": sql,
            "description": description,
            "message": f"⚠️ This will {operation} data in the '{table_name}' table. Please confirm you want to proceed.",
            "instructions": "Ask the user to confirm, then call execute_sql_write again with user_confirmed=true"
        }
    
    # Execute the write operation
    try:
        # For actual SQL execution, we need to use the RPC function
        # First, let's try using the Supabase Python client methods
        
        if operation == "UPDATE":
            # Parse simple UPDATE statements
            # UPDATE table SET col1=val1, col2=val2 WHERE condition
            set_match = re.search(r'SET\s+(.+?)\s+WHERE', sql, re.IGNORECASE)
            where_match = re.search(r'WHERE\s+(.+?)(?:;|$)', sql, re.IGNORECASE)
            
            if not set_match or not where_match:
                return {"error": "UPDATE must have SET and WHERE clauses. Format: UPDATE table SET col=val WHERE id='xxx'"}
            
            # For safety, require WHERE clause with id
            where_clause = where_match.group(1).strip()
            if 'id' not in where_clause.lower():
                return {"error": "UPDATE must include id in WHERE clause for safety"}
            
            # Parse the id value
            id_match = re.search(r"id\s*=\s*'([^']+)'", where_clause, re.IGNORECASE)
            if not id_match:
                return {"error": "Could not parse id from WHERE clause. Format: WHERE id='uuid'"}
            
            record_id = id_match.group(1)
            
            # Parse SET clause into dict
            set_clause = set_match.group(1).strip()
            update_data = {}
            for part in set_clause.split(','):
                if '=' in part:
                    key, value = part.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    update_data[key] = value
            
            # Always update the updated_at timestamp
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # For sync-managed tables, mark as local change to prevent overwrite
            # This tells the sync service "this was updated locally, push to Notion"
            sync_managed_tables = ["applications", "meetings", "tasks", "journals", 
                                   "reflections", "contacts", "linkedin_posts"]
            if table_name in sync_managed_tables:
                update_data["last_sync_source"] = "supabase"
            
            # Use .select() to get the updated row back (Supabase quirk)
            result = supabase.table(table_name).update(update_data).eq("id", record_id).select().execute()
            
            if result.data and len(result.data) > 0:
                return {
                    "status": "success",
                    "operation": operation,
                    "table": table_name,
                    "updated_id": record_id,
                    "fields_updated": list(update_data.keys()),
                    "rows_affected": len(result.data),
                    "updated_record": result.data[0],  # Return the actual updated data for verification
                    "sync_note": "Set last_sync_source='supabase' to preserve changes during next sync" if table_name in sync_managed_tables else None
                }
            else:
                # No rows matched - likely wrong ID
                return {
                    "status": "warning",
                    "operation": operation,
                    "table": table_name,
                    "message": f"No rows matched id='{record_id}'. Check the UUID is correct.",
                    "rows_affected": 0
                }
            
        elif operation == "DELETE":
            # Parse DELETE FROM table WHERE id='xxx'
            where_match = re.search(r'WHERE\s+(.+?)(?:;|$)', sql, re.IGNORECASE)
            
            if not where_match:
                return {"error": "DELETE must have WHERE clause. Format: DELETE FROM table WHERE id='xxx'"}
            
            where_clause = where_match.group(1).strip()
            if 'id' not in where_clause.lower():
                return {"error": "DELETE must include id in WHERE clause for safety"}
            
            id_match = re.search(r"id\s*=\s*'([^']+)'", where_clause, re.IGNORECASE)
            if not id_match:
                return {"error": "Could not parse id from WHERE clause. Format: WHERE id='uuid'"}
            
            record_id = id_match.group(1)
            
            # For contacts, use soft delete
            if table_name == "contacts":
                from datetime import datetime, timezone
                result = supabase.table(table_name).update({
                    "deleted_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", record_id).execute()
                return {
                    "status": "success",
                    "operation": "soft_delete",
                    "table": table_name,
                    "deleted_id": record_id,
                    "note": "Contact was soft-deleted (can be restored)"
                }
            else:
                result = supabase.table(table_name).delete().eq("id", record_id).execute()
                return {
                    "status": "success",
                    "operation": operation,
                    "table": table_name,
                    "deleted_id": record_id
                }
                
        elif operation == "INSERT":
            # Parse INSERT INTO table (cols) VALUES (vals)
            cols_match = re.search(r'\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)', sql, re.IGNORECASE)
            
            if not cols_match:
                return {"error": "INSERT format: INSERT INTO table (col1, col2) VALUES ('val1', 'val2')"}
            
            columns = [c.strip() for c in cols_match.group(1).split(',')]
            values = [v.strip().strip("'\"") for v in cols_match.group(2).split(',')]
            
            if len(columns) != len(values):
                return {"error": "Number of columns must match number of values"}
            
            insert_data = dict(zip(columns, values))
            
            result = supabase.table(table_name).insert(insert_data).execute()
            
            return {
                "status": "success",
                "operation": operation,
                "table": table_name,
                "inserted_id": result.data[0].get("id") if result.data else None,
                "data": result.data[0] if result.data else None
            }
        
    except Exception as e:
        logger.error(f"SQL write execution error: {e}")
        return {
            "status": "error",
            "error": str(e)[:300],
            "hint": "Check SQL syntax. For complex operations, break into simpler queries."
        }


def _query_database(sql: str) -> Dict[str, Any]:
    """Execute a read-only SQL query using direct table access.
    
    Note: Full SQL execution is not available. This tool parses simple SELECT queries
    and converts them to Supabase table queries. For complex queries, use the
    specific tools like search_contacts, get_tasks, search_meetings, etc.
    """
    import re
    
    # Security: Only allow SELECT statements
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed"}
    
    # Block dangerous keywords
    dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    for keyword in dangerous:
        if keyword in sql_upper:
            return {"error": f"Query contains forbidden keyword: {keyword}"}
    
    try:
        # Parse simple queries like: SELECT * FROM table_name LIMIT n
        # or: SELECT columns FROM table_name WHERE condition LIMIT n
        
        # Extract table name
        from_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        if not from_match:
            return {"error": "Could not parse table name from query. Use specific tools like search_contacts, get_tasks, etc."}
        
        table_name = from_match.group(1)
        
        # Allowed tables for security
        allowed_tables = [
            "contacts", "meetings", "tasks", "journals", "reflections",
            "calendar_events", "emails", "transcripts", "beeper_chats",
            "beeper_messages", "books", "highlights", "sync_logs",
            "applications", "linkedin_posts", "linkedin_connections",
            "mem0_memories", "messages", "chat_messages", "agents", "users",
            "sync_state", "pipeline_logs"
        ]
        
        if table_name.lower() not in allowed_tables:
            return {"error": f"Table '{table_name}' is not accessible. Allowed: {', '.join(allowed_tables)}"}
        
        # Extract columns (simplified - just use *)
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE)
        columns = "*"
        if select_match:
            cols = select_match.group(1).strip()
            if cols != "*":
                columns = cols
        
        # Extract LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', sql, re.IGNORECASE)
        limit = int(limit_match.group(1)) if limit_match else 20
        limit = min(limit, 100)  # Cap at 100
        
        # Execute query
        query = supabase.table(table_name).select(columns).limit(limit)
        
        # Try to parse simple WHERE clauses
        where_match = re.search(r'WHERE\s+(.+?)(?:ORDER|LIMIT|$)', sql, re.IGNORECASE)
        if where_match:
            # For now, just note that WHERE was requested but not fully supported
            logger.info(f"WHERE clause detected but not fully parsed: {where_match.group(1)}")
        
        # Order by created_at desc by default for most tables
        if table_name.lower() in ["meetings", "tasks", "journals", "reflections", "emails", "beeper_messages"]:
            query = query.order("created_at", desc=True)
        
        result = query.execute()
        
        return {
            "data": result.data[:limit] if result.data else [],
            "count": len(result.data) if result.data else 0,
            "table": table_name,
            "note": "For complex queries, use specific tools like search_contacts, get_tasks, search_meetings, etc."
        }
        
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return {
            "error": f"Query failed: {str(e)[:200]}",
            "hint": "Try using specific tools: search_contacts, get_tasks, search_meetings, get_journals, get_beeper_inbox, etc."
        }


def _search_contacts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search contacts by name, company, etc."""
    try:
        # Escape special characters for ILIKE to prevent SQL injection
        safe_query = query.replace("%", "\\%").replace("_", "\\_")
        
        result = supabase.table("contacts").select(
            "id, first_name, last_name, email, company, job_title, phone, notes"
        ).or_(
            f"first_name.ilike.%{safe_query}%,last_name.ilike.%{safe_query}%,company.ilike.%{safe_query}%,email.ilike.%{safe_query}%"
        ).is_("deleted_at", "null").limit(limit).execute()
        
        contacts = []
        for c in result.data or []:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            contacts.append({
                "id": c.get("id"),
                "name": name,
                "email": c.get("email"),
                "company": c.get("company"),
                "job_title": c.get("job_title"),
                "phone": c.get("phone"),
                "notes": c.get("notes", "")[:200] if c.get("notes") else None
            })
        
        return {"contacts": contacts, "count": len(contacts)}
    except Exception as e:
        return {"error": str(e)}


def _get_contact_history(contact_name: str) -> Dict[str, Any]:
    """Get full interaction history with a contact."""
    try:
        # Escape special characters for ILIKE
        safe_name = contact_name.replace("%", "\\%").replace("_", "\\_")
        
        # Find contact
        result = supabase.table("contacts").select("id, first_name, last_name, email, company").or_(
            f"first_name.ilike.%{safe_name}%,last_name.ilike.%{safe_name}%"
        ).is_("deleted_at", "null").limit(1).execute()
        
        if not result.data:
            return {"error": f"Contact '{contact_name}' not found"}
        
        contact = result.data[0]
        contact_id = contact["id"]
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        
        # Get meetings
        meetings = supabase.table("meetings").select(
            "title, date, summary"
        ).eq("contact_id", contact_id).order("date", desc=True).limit(10).execute()
        
        # Get emails
        emails = supabase.table("emails").select(
            "subject, date, direction, snippet"
        ).eq("contact_id", contact_id).order("date", desc=True).limit(10).execute()
        
        # Get calendar events
        events = supabase.table("calendar_events").select(
            "summary, start_time, location"
        ).eq("contact_id", contact_id).order("start_time", desc=True).limit(10).execute()
        
        return {
            "contact": {
                "name": name,
                "email": contact.get("email"),
                "company": contact.get("company")
            },
            "meetings": meetings.data or [],
            "emails": emails.data or [],
            "calendar_events": events.data or []
        }
    except Exception as e:
        return {"error": str(e)}


def _create_task(input: Dict) -> Dict[str, Any]:
    """Create a new task."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        
        payload = {
            "title": input.get("title"),
            "description": input.get("description", ""),
            "status": "pending",
            "priority": input.get("priority", "medium"),
            "created_at": now,
            "updated_at": now
        }
        
        if input.get("due_date"):
            payload["due_date"] = input["due_date"]
        
        logger.info(f"Creating task via chat: {payload}")
        result = supabase.table("tasks").insert(payload).execute()
        
        if not result.data:
            return {"error": "Insert returned no data"}
        
        task_id = result.data[0]["id"]
        
        logger.info(f"Created task via chat: {input.get('title')} -> {task_id}")
        return {"success": True, "task_id": task_id, "message": f"Task '{input.get('title')}' created"}
    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        return {"error": str(e)}


def _create_reflection(input: Dict) -> Dict[str, Any]:
    """Create or append to a reflection."""
    try:
        topic_key = input.get("topic_key", "").lower().replace(" ", "-")
        
        # Check for existing reflection with same topic_key
        existing = supabase.table("reflections").select("id, title, content").ilike(
            "topic_key", topic_key
        ).is_("deleted_at", "null").limit(1).execute()
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        if existing.data:
            # Append to existing
            existing_content = existing.data[0].get("content", "") or ""
            new_content = f"{existing_content}\n\n---\n\n### 📝 Update: {timestamp}\n\n{input.get('content')}"
            
            supabase.table("reflections").update({
                "content": new_content,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", existing.data[0]["id"]).execute()
            
            logger.info(f"Appended to reflection via chat: {topic_key}")
            return {"success": True, "action": "appended", "reflection_id": existing.data[0]["id"]}
        else:
            # Create new
            payload = {
                "title": input.get("title"),
                "content": f"### 📝 Entry: {timestamp}\n\n{input.get('content')}",
                "topic_key": topic_key,
                "tags": input.get("tags", []),
                "date": datetime.now(timezone.utc).date().isoformat()
            }
            
            result = supabase.table("reflections").insert(payload).execute()
            logger.info(f"Created reflection via chat: {input.get('title')}")
            return {"success": True, "action": "created", "reflection_id": result.data[0]["id"]}
    except Exception as e:
        return {"error": str(e)}


def _get_upcoming_events(days: int = 7) -> Dict[str, Any]:
    """Get upcoming calendar events."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        
        result = supabase.table("calendar_events").select(
            "summary, start_time, end_time, location, attendees"
        ).gte("start_time", now).lte("start_time", future).neq(
            "status", "cancelled"
        ).order("start_time", desc=False).limit(20).execute()
        
        events = []
        for e in result.data or []:
            events.append({
                "title": e.get("summary"),
                "start": e.get("start_time"),
                "end": e.get("end_time"),
                "location": e.get("location"),
                "attendees": [a.get("email") for a in (e.get("attendees") or [])[:3]]
            })
        
        return {"events": events, "count": len(events), "days_ahead": days}
    except Exception as e:
        return {"error": str(e)}


def _get_recent_emails(input: Dict) -> Dict[str, Any]:
    """Get recent emails with optional filters."""
    try:
        days = input.get("days", 7)
        include_body = input.get("include_body", False)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Select fields based on whether body is requested
        if include_body:
            fields = "id, subject, sender, recipient, date, snippet, body_text"
        else:
            fields = "id, subject, sender, recipient, date, snippet"
        
        query = supabase.table("emails").select(fields).gte("date", cutoff)
        
        if input.get("from_email"):
            query = query.ilike("sender", f"%{input['from_email']}%")
        
        if input.get("subject_contains"):
            query = query.ilike("subject", f"%{input['subject_contains']}%")
        
        result = query.order("date", desc=True).limit(input.get("limit", 10)).execute()
        
        # Format emails for readability
        emails = []
        for e in result.data or []:
            email_info = {
                "id": e.get("id"),
                "subject": e.get("subject", "(no subject)"),
                "from": e.get("sender", "Unknown"),
                "to": e.get("recipient", "Unknown"),
                "date": e.get("date"),
            }
            
            if include_body and e.get("body_text"):
                email_info["body"] = e.get("body_text")
            else:
                # Show preview/snippet
                snippet = e.get("snippet", "")
                email_info["preview"] = snippet[:200] + "..." if len(snippet) > 200 else snippet
            
            emails.append(email_info)
        
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        logger.error(f"Error getting emails: {e}")
        return {"error": str(e), "emails": []}


def _get_email_by_id(input: Dict) -> Dict[str, Any]:
    """Get full email details by ID."""
    try:
        email_id = input.get("email_id")
        if not email_id:
            return {"error": "email_id is required"}
        
        result = supabase.table("emails").select(
            "id, subject, sender, recipient, date, snippet, body_text, body_html, thread_id, label_ids"
        ).eq("id", email_id).execute()
        
        if not result.data:
            return {"error": f"Email not found with ID: {email_id}"}
        
        e = result.data[0]
        return {
            "id": e.get("id"),
            "subject": e.get("subject", "(no subject)"),
            "from": e.get("sender", "Unknown"),
            "to": e.get("recipient", "Unknown"),
            "date": e.get("date"),
            "body": e.get("body_text") or e.get("snippet", ""),
            "labels": e.get("label_ids", []),
            "thread_id": e.get("thread_id")
        }
    except Exception as e:
        logger.error(f"Error getting email by ID: {e}")
        return {"error": str(e)}


def _search_emails_live(input: Dict) -> Dict[str, Any]:
    """Search Gmail in real-time via the sync service."""
    import httpx
    import os
    
    query = input.get("query", "")
    max_results = input.get("max_results", 10)
    
    if not query:
        return {"error": "Search query is required"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{sync_service_url}/gmail/search",
                params={"q": query, "max_results": max_results}
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "emails": data.get("emails", []),
                    "count": len(data.get("emails", [])),
                    "query": query,
                    "source": "live_gmail"
                }
            else:
                logger.error(f"Gmail search failed: {response.status_code} - {response.text[:200]}")
                return {"error": f"Gmail search failed: {response.text[:200]}"}
                
    except httpx.TimeoutException:
        return {"error": "Gmail search timed out - please try again"}
    except Exception as e:
        logger.error(f"Error searching Gmail: {e}")
        return {"error": str(e)}


def _get_tasks(status: str = "pending", limit: int = 10) -> Dict[str, Any]:
    """Get tasks with optional status filter."""
    try:
        query = supabase.table("tasks").select(
            "id, title, description, status, priority, due_date, created_at"
        ).is_("deleted_at", "null")
        
        if status != "all":
            query = query.eq("status", status)
        
        result = query.order("created_at", desc=True).limit(limit).execute()
        
        return {"tasks": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        return {"error": str(e)}


def _complete_task(input: Dict) -> Dict[str, Any]:
    """Mark a task as completed."""
    try:
        task_id = input.get("task_id")
        task_title = input.get("task_title")
        
        if not task_id and not task_title:
            return {"error": "Provide either task_id or task_title"}
        
        if task_id:
            query = supabase.table("tasks").select("id, title").eq("id", task_id)
        else:
            query = supabase.table("tasks").select("id, title").ilike("title", f"%{task_title}%").eq("status", "pending")
        
        result = query.limit(1).execute()
        
        if not result.data:
            return {"error": "Task not found"}
        
        task = result.data[0]
        
        supabase.table("tasks").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", task["id"]).execute()
        
        logger.info(f"Completed task via chat: {task['title']}")
        return {"success": True, "message": f"Task '{task['title']}' marked as completed"}
    except Exception as e:
        return {"error": str(e)}


def _get_reflections(input: Dict) -> Dict[str, Any]:
    """Get reflections with optional filters."""
    try:
        query = supabase.table("reflections").select(
            "id, title, topic_key, tags, date, content"
        ).is_("deleted_at", "null")
        
        if input.get("topic_key"):
            query = query.ilike("topic_key", f"%{input['topic_key']}%")
        
        if input.get("search"):
            query = query.or_(
                f"title.ilike.%{input['search']}%,content.ilike.%{input['search']}%"
            )
        
        result = query.order("created_at", desc=True).limit(input.get("limit", 5)).execute()
        
        reflections = []
        for r in result.data or []:
            reflections.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "topic_key": r.get("topic_key"),
                "tags": r.get("tags"),
                "date": r.get("date"),
                "content_preview": (r.get("content") or "")[:300] + "..." if len(r.get("content") or "") > 300 else r.get("content")
            })
        
        return {"reflections": reflections, "count": len(reflections)}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# PHASE 1 TOOL IMPLEMENTATIONS
# =============================================================================

def _search_transcripts(input: Dict) -> Dict[str, Any]:
    """Search through voice memo transcripts."""
    try:
        query_text = input.get("query", "")
        days = input.get("days", 30)
        limit = input.get("limit", 5)
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        result = supabase.table("transcripts").select(
            "id, source_file, full_text, created_at, language"
        ).ilike(
            "full_text", f"%{query_text}%"
        ).gte("created_at", cutoff).order("created_at", desc=True).limit(limit).execute()
        
        transcripts = []
        for t in result.data or []:
            full_text = t.get("full_text", "")
            # Find the relevant snippet around the search term
            lower_text = full_text.lower()
            query_lower = query_text.lower()
            pos = lower_text.find(query_lower)
            
            if pos >= 0:
                start = max(0, pos - 100)
                end = min(len(full_text), pos + len(query_text) + 100)
                snippet = "..." + full_text[start:end] + "..."
            else:
                snippet = full_text[:200] + "..."
            
            transcripts.append({
                "id": t.get("id"),
                "source_file": t.get("source_file"),
                "date": t.get("created_at", "")[:10],
                "snippet": snippet,
                "language": t.get("language")
            })
        
        return {"transcripts": transcripts, "count": len(transcripts), "query": query_text}
    except Exception as e:
        return {"error": str(e)}


def _get_journals(input: Dict) -> Dict[str, Any]:
    """Get journal entries."""
    try:
        if input.get("date"):
            # Specific date
            result = supabase.table("journals").select(
                "id, date, title, summary, mood, key_events, accomplishments, challenges, tomorrow_focus"
            ).eq("date", input["date"]).limit(1).execute()
        else:
            # Last N days
            days = input.get("days", 7)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            
            result = supabase.table("journals").select(
                "id, date, title, summary, mood, key_events, accomplishments, challenges, tomorrow_focus"
            ).gte("date", cutoff).order("date", desc=True).execute()
        
        journals = []
        for j in result.data or []:
            journals.append({
                "date": j.get("date"),
                "summary": j.get("summary"),
                "mood": j.get("mood"),
                "key_events": j.get("key_events", []),
                "accomplishments": j.get("accomplishments", []),
                "challenges": j.get("challenges", []),
                "tomorrow_focus": j.get("tomorrow_focus", [])
            })
        
        return {"journals": journals, "count": len(journals)}
    except Exception as e:
        return {"error": str(e)}


def _search_meetings(input: Dict) -> Dict[str, Any]:
    """Search meetings by topic, person, or content."""
    try:
        days = input.get("days", 90)
        limit = input.get("limit", 10)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        query = supabase.table("meetings").select(
            "id, title, date, summary, contact_name, topics_discussed, people_mentioned"
        ).gte("date", cutoff)
        
        if input.get("query"):
            search = input["query"]
            query = query.or_(
                f"title.ilike.%{search}%,summary.ilike.%{search}%,contact_name.ilike.%{search}%"
            )
        
        if input.get("contact_name"):
            query = query.ilike("contact_name", f"%{input['contact_name']}%")
        
        result = query.order("date", desc=True).limit(limit).execute()
        
        meetings = []
        for m in result.data or []:
            meetings.append({
                "id": m.get("id"),
                "title": m.get("title"),
                "date": m.get("date"),
                "contact": m.get("contact_name"),
                "summary": (m.get("summary") or "")[:200],
                "topics": [t.get("topic") for t in (m.get("topics_discussed") or [])[:3]],
                "people_mentioned": m.get("people_mentioned", [])[:5]
            })
        
        return {"meetings": meetings, "count": len(meetings)}
    except Exception as e:
        return {"error": str(e)}


def _update_task(input: Dict) -> Dict[str, Any]:
    """Update a task's priority, due date, or status."""
    try:
        task_id = input.get("task_id")
        task_title = input.get("task_title")
        
        if not task_id and not task_title:
            return {"error": "Provide either task_id or task_title"}
        
        # Find the task
        if task_id:
            query = supabase.table("tasks").select("id, title").eq("id", task_id)
        else:
            query = supabase.table("tasks").select("id, title").ilike("title", f"%{task_title}%")
        
        result = query.is_("deleted_at", "null").limit(1).execute()
        
        if not result.data:
            return {"error": f"Task not found: {task_title or task_id}"}
        
        task = result.data[0]
        
        # Build update payload
        updates = {}
        if input.get("priority"):
            updates["priority"] = input["priority"]
        if input.get("due_date"):
            updates["due_date"] = input["due_date"]
        if input.get("status"):
            updates["status"] = input["status"]
            if input["status"] == "completed":
                updates["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if not updates:
            return {"error": "No updates provided. Specify priority, due_date, or status."}
        
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        supabase.table("tasks").update(updates).eq("id", task["id"]).execute()
        
        logger.info(f"Updated task via chat: {task['title']} -> {updates}")
        return {"success": True, "task": task["title"], "updates": updates}
    except Exception as e:
        return {"error": str(e)}


def _add_contact_note(input: Dict) -> Dict[str, Any]:
    """Add a note to a contact's profile."""
    try:
        contact_name = input.get("contact_name", "")
        note = input.get("note", "")
        
        if not note:
            return {"error": "Note content is required"}
        
        # Find contact
        result = supabase.table("contacts").select("id, first_name, last_name, notes").or_(
            f"first_name.ilike.%{contact_name}%,last_name.ilike.%{contact_name}%"
        ).is_("deleted_at", "null").limit(1).execute()
        
        if not result.data:
            return {"error": f"Contact '{contact_name}' not found"}
        
        contact = result.data[0]
        existing_notes = contact.get("notes") or ""
        
        # Append new note with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        new_notes = f"{existing_notes}\n\n[{timestamp}] {note}".strip()
        
        supabase.table("contacts").update({
            "notes": new_notes,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", contact["id"]).execute()
        
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        logger.info(f"Added note to contact via chat: {name}")
        return {"success": True, "contact": name, "note_added": note}
    except Exception as e:
        return {"error": str(e)}


def _create_contact(input: Dict) -> Dict[str, Any]:
    """Create a new contact in the CRM."""
    try:
        first_name = input.get("first_name", "").strip()
        if not first_name:
            return {"error": "First name is required"}
        
        last_name = input.get("last_name", "").strip()
        email = input.get("email", "").strip() or None
        phone = input.get("phone", "").strip() or None
        company = input.get("company", "").strip() or None
        job_title = input.get("job_title", "").strip() or None
        notes = input.get("notes", "").strip() or None
        
        # Check if contact already exists
        if email:
            existing = supabase.table("contacts").select("id, first_name, last_name").eq("email", email).execute()
            if existing.data:
                name = f"{existing.data[0].get('first_name', '')} {existing.data[0].get('last_name', '')}".strip()
                return {"error": f"Contact with email {email} already exists: {name}"}
        
        # Create the contact
        contact_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "company": company,
            "job_title": job_title,
            "notes": notes,
            "last_sync_source": "supabase"
        }
        
        result = supabase.table("contacts").insert(contact_data).execute()
        
        if result.data:
            contact = result.data[0]
            name = f"{first_name} {last_name}".strip()
            logger.info(f"Created contact via chat: {name}")
            return {
                "success": True,
                "contact_id": contact["id"],
                "name": name,
                "email": email,
                "company": company,
                "message": f"Created contact: {name}"
            }
        return {"error": "Failed to create contact"}
    except Exception as e:
        return {"error": str(e)}


def _update_contact(input: Dict) -> Dict[str, Any]:
    """Update an existing contact's information."""
    try:
        contact_name = input.get("contact_name", "").strip()
        contact_id = input.get("contact_id", "").strip()
        
        # Find the contact
        contact = None
        if contact_id:
            result = supabase.table("contacts").select("*").eq("id", contact_id).execute()
            if result.data:
                contact = result.data[0]
        elif contact_name:
            # Search by name
            parts = contact_name.lower().split()
            if len(parts) >= 2:
                result = supabase.table("contacts").select("*").ilike(
                    "first_name", f"%{parts[0]}%"
                ).ilike("last_name", f"%{parts[-1]}%").execute()
            else:
                result = supabase.table("contacts").select("*").or_(
                    f"first_name.ilike.%{parts[0]}%,last_name.ilike.%{parts[0]}%"
                ).execute()
            if result.data:
                contact = result.data[0]
        
        if not contact:
            return {"error": "Contact not found"}
        
        # Build update data
        update_data = {}
        if input.get("email"):
            update_data["email"] = input["email"].strip()
        if input.get("phone"):
            update_data["phone"] = input["phone"].strip()
        if input.get("company"):
            update_data["company"] = input["company"].strip()
        if input.get("job_title"):
            update_data["job_title"] = input["job_title"].strip()
        if input.get("birthday"):
            update_data["birthday"] = input["birthday"].strip()
        if input.get("linkedin_url"):
            update_data["linkedin_url"] = input["linkedin_url"].strip()
        if input.get("location"):
            update_data["location"] = input["location"].strip()
        
        if not update_data:
            return {"error": "No fields to update provided"}
        
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_data["last_sync_source"] = "supabase"
        
        supabase.table("contacts").update(update_data).eq("id", contact["id"]).execute()
        
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        logger.info(f"Updated contact via chat: {name}, fields: {list(update_data.keys())}")
        return {
            "success": True,
            "contact": name,
            "fields_updated": list(update_data.keys()),
            "message": f"Updated {name}: {', '.join(update_data.keys())}"
        }
    except Exception as e:
        return {"error": str(e)}


def _create_meeting(input: Dict) -> Dict[str, Any]:
    """Log a meeting or conversation."""
    try:
        title = input.get("title", "").strip()
        if not title:
            return {"error": "Meeting title is required"}
        
        contact_name = input.get("contact_name", "").strip()
        summary = input.get("summary", "").strip() or None
        location = input.get("location", "").strip() or None
        topics_discussed = input.get("topics_discussed", [])
        follow_up_items = input.get("follow_up_items", [])
        
        # Parse date
        date_str = input.get("date", "today").strip().lower()
        if date_str == "today":
            meeting_date = datetime.now(timezone.utc)
        elif date_str == "yesterday":
            meeting_date = datetime.now(timezone.utc) - timedelta(days=1)
        else:
            try:
                meeting_date = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                meeting_date = datetime.now(timezone.utc)
        
        # Find contact if name provided
        contact_id = None
        if contact_name:
            parts = contact_name.lower().split()
            if len(parts) >= 2:
                result = supabase.table("contacts").select("id").ilike(
                    "first_name", f"%{parts[0]}%"
                ).ilike("last_name", f"%{parts[-1]}%").execute()
            else:
                result = supabase.table("contacts").select("id").or_(
                    f"first_name.ilike.%{parts[0]}%,last_name.ilike.%{parts[0]}%"
                ).execute()
            if result.data:
                contact_id = result.data[0]["id"]
        
        # Create the meeting
        meeting_data = {
            "title": title,
            "date": meeting_date.isoformat(),
            "contact_id": contact_id,
            "contact_name": contact_name if contact_name else None,
            "summary": summary,
            "location": location,
            "topics_discussed": topics_discussed if topics_discussed else None,
            "follow_up_items": follow_up_items if follow_up_items else None,
            "last_sync_source": "supabase"
        }
        
        result = supabase.table("meetings").insert(meeting_data).execute()
        
        if result.data:
            meeting = result.data[0]
            logger.info(f"Created meeting via chat: {title}")
            
            # Create follow-up tasks if provided
            tasks_created = []
            for item in follow_up_items:
                task_result = supabase.table("tasks").insert({
                    "title": item,
                    "origin_id": meeting["id"],
                    "origin_type": "meeting",
                    "status": "pending",  # Use lowercase to match database.py
                    "last_sync_source": "supabase"
                }).execute()
                if task_result.data:
                    tasks_created.append(item)
            
            return {
                "success": True,
                "meeting_id": meeting["id"],
                "title": title,
                "contact_linked": contact_id is not None,
                "tasks_created": len(tasks_created),
                "message": f"Logged meeting: {title}" + (f" with {contact_name}" if contact_name else "")
            }
        return {"error": "Failed to create meeting"}
    except Exception as e:
        return {"error": str(e)}


def _delete_task(input: Dict) -> Dict[str, Any]:
    """Delete (soft-delete) a task."""
    try:
        task_title = input.get("task_title", "").strip()
        task_id = input.get("task_id", "").strip()
        user_confirmed = input.get("user_confirmed", False)
        
        # Find the task first
        task = None
        if task_id:
            result = supabase.table("tasks").select("*").eq("id", task_id).is_("deleted_at", "null").execute()
            if result.data:
                task = result.data[0]
        elif task_title:
            result = supabase.table("tasks").select("*").ilike(
                "title", f"%{task_title}%"
            ).is_("deleted_at", "null").limit(1).execute()
            if result.data:
                task = result.data[0]
        
        if not task:
            return {"error": "Task not found"}
        
        # Check confirmation BEFORE deleting
        if not user_confirmed:
            return {
                "needs_confirmation": True,
                "task_to_delete": {
                    "id": task["id"],
                    "title": task.get("title"),
                    "status": task.get("status"),
                    "due_date": task.get("due_date")
                },
                "message": f"⚠️ Please confirm deletion of task: '{task.get('title')}'",
                "instructions": "Ask user to confirm, then call delete_task again with user_confirmed=true"
            }
        
        # Soft delete the task
        supabase.table("tasks").update({
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", task["id"]).execute()
        
        logger.info(f"Deleted task via chat: {task.get('title')}")
        return {
            "success": True,
            "task_id": task["id"],
            "title": task.get("title"),
            "message": f"Deleted task: {task.get('title')}"
        }
    except Exception as e:
        return {"error": str(e)}


def _summarize_activity(period: str = "today") -> Dict[str, Any]:
    """Get a summary of recent activity."""
    try:
        now = datetime.now(timezone.utc)
        
        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "this_week":
            # Start of week (Monday)
            days_since_monday = now.weekday()
            start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "last_week":
            days_since_monday = now.weekday()
            end = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
            start = end - timedelta(days=7)
        else:
            return {"error": f"Unknown period: {period}"}
        
        start_iso = start.isoformat()
        end_iso = end.isoformat()
        
        # Get meetings
        meetings = supabase.table("meetings").select(
            "title, contact_name"
        ).gte("date", start_iso).lte("date", end_iso).execute()
        
        # Get tasks completed
        tasks_completed = supabase.table("tasks").select(
            "title"
        ).gte("completed_at", start_iso).lte("completed_at", end_iso).eq("status", "completed").execute()
        
        # Get tasks created
        tasks_created = supabase.table("tasks").select(
            "title"
        ).gte("created_at", start_iso).lte("created_at", end_iso).execute()
        
        # Get reflections
        reflections = supabase.table("reflections").select(
            "title, topic_key"
        ).gte("created_at", start_iso).lte("created_at", end_iso).is_("deleted_at", "null").execute()
        
        # Get emails
        emails_received = supabase.table("emails").select(
            "subject"
        ).gte("date", start_iso).lte("date", end_iso).eq("direction", "inbound").execute()
        
        return {
            "period": period,
            "start": start_iso[:10],
            "end": end_iso[:10],
            "summary": {
                "meetings": len(meetings.data or []),
                "meeting_contacts": list(set(m.get("contact_name") for m in (meetings.data or []) if m.get("contact_name"))),
                "tasks_completed": len(tasks_completed.data or []),
                "tasks_created": len(tasks_created.data or []),
                "reflections": len(reflections.data or []),
                "reflection_topics": list(set(r.get("topic_key") for r in (reflections.data or []) if r.get("topic_key"))),
                "emails_received": len(emails_received.data or [])
            }
        }
    except Exception as e:
        return {"error": str(e)}


def _who_to_contact(input: Dict) -> Dict[str, Any]:
    """Find contacts you haven't interacted with recently."""
    try:
        days_inactive = input.get("days_inactive", 30)
        limit = input.get("limit", 5)
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_inactive)).isoformat()
        
        # Get contacts with their last meeting date
        # This is a simplified approach - ideally we'd check meetings, emails, and events
        contacts = supabase.table("contacts").select(
            "id, first_name, last_name, company, email"
        ).is_("deleted_at", "null").execute()
        
        inactive_contacts = []
        
        for contact in (contacts.data or []):
            contact_id = contact["id"]
            
            # Check for recent meetings
            recent_meeting = supabase.table("meetings").select(
                "date"
            ).eq("contact_id", contact_id).gte("date", cutoff).limit(1).execute()
            
            if not recent_meeting.data:
                # Check for recent emails
                email = contact.get("email")
                recent_email = None
                if email:
                    recent_email = supabase.table("emails").select(
                        "date"
                    ).or_(
                        f"sender.ilike.%{email}%,recipient.ilike.%{email}%"
                    ).gte("date", cutoff).limit(1).execute()
                
                if not recent_email or not recent_email.data:
                    # This contact is inactive
                    name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                    inactive_contacts.append({
                        "name": name,
                        "company": contact.get("company"),
                        "email": contact.get("email")
                    })
                    
                    if len(inactive_contacts) >= limit:
                        break
        
        return {
            "inactive_contacts": inactive_contacts,
            "count": len(inactive_contacts),
            "days_threshold": days_inactive
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# LOCATION & TIMEZONE TOOLS
# =============================================================================

# Common city to timezone mapping
CITY_TIMEZONES = {
    # Europe
    "istanbul": "Europe/Istanbul",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam",
    "zurich": "Europe/Zurich",
    "vienna": "Europe/Vienna",
    "madrid": "Europe/Madrid",
    "rome": "Europe/Rome",
    "moscow": "Europe/Moscow",
    # Asia
    "jakarta": "Asia/Jakarta",
    "singapore": "Asia/Singapore",
    "tokyo": "Asia/Tokyo",
    "hong kong": "Asia/Hong_Kong",
    "shanghai": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "seoul": "Asia/Seoul",
    "dubai": "Asia/Dubai",
    "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata",
    "bangkok": "Asia/Bangkok",
    "kuala lumpur": "Asia/Kuala_Lumpur",
    "manila": "Asia/Manila",
    "taipei": "Asia/Taipei",
    # Americas
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "miami": "America/New_York",
    "toronto": "America/Toronto",
    "vancouver": "America/Vancouver",
    "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
    # Australia/Pacific
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "auckland": "Pacific/Auckland",
}


def _set_user_location(input: Dict) -> Dict[str, Any]:
    """Set user's location and timezone from text."""
    try:
        city = input.get("city", "").strip()
        country = input.get("country", "")
        timezone_input = input.get("timezone", "")
        
        if not city:
            return {"error": "City is required"}
        
        # Determine timezone
        if timezone_input:
            # User provided explicit timezone
            user_tz = timezone_input
        else:
            # Try to infer from city name
            city_lower = city.lower()
            user_tz = CITY_TIMEZONES.get(city_lower)
            
            if not user_tz:
                # Try partial match
                for city_key, tz in CITY_TIMEZONES.items():
                    if city_lower in city_key or city_key in city_lower:
                        user_tz = tz
                        break
            
            if not user_tz:
                return {
                    "error": f"Could not determine timezone for '{city}'. Please specify timezone explicitly.",
                    "hint": "Say something like 'My timezone is Asia/Jakarta' or 'Europe/Istanbul'"
                }
        
        # Validate timezone
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(user_tz)
        except Exception:
            return {"error": f"Invalid timezone: {user_tz}"}
        
        now = datetime.now(timezone.utc).isoformat()
        
        # Upsert to sync_state
        updates = [
            {"key": "user_timezone", "value": user_tz, "updated_at": now},
            {"key": "user_city", "value": city, "updated_at": now},
        ]
        
        if country:
            updates.append({"key": "user_country", "value": country, "updated_at": now})
        
        for update in updates:
            supabase.table("sync_state").upsert(update, on_conflict="key").execute()
        
        logger.info(f"User location set via chat: {city}, TZ: {user_tz}")
        
        return {
            "success": True,
            "city": city,
            "country": country or "Not specified",
            "timezone": user_tz,
            "message": f"Location updated to {city} ({user_tz})"
        }
    except Exception as e:
        logger.error(f"Failed to set location: {e}")
        return {"error": str(e)}


def _get_user_location() -> Dict[str, Any]:
    """Get user's stored location and timezone."""
    try:
        # Get location from sync_state (key-value store)
        result = supabase.table("sync_state").select("key, value, updated_at").in_(
            "key", ["user_timezone", "user_city", "user_country"]
        ).execute()
        
        location_data = {}
        for row in (result.data or []):
            location_data[row["key"]] = row["value"]
            if row["key"] == "user_city":
                location_data["updated_at"] = row["updated_at"]
        
        if not location_data.get("user_city") and not location_data.get("user_timezone"):
            return {
                "error": "Location not set. Ask user to say something like 'I'm in Istanbul' or 'My timezone is Europe/Istanbul'",
                "timezone": "UTC",
                "city": "Unknown"
            }
        
        return {
            "timezone": location_data.get("user_timezone", "UTC"),
            "city": location_data.get("user_city", "Unknown"),
            "country": location_data.get("user_country", "Unknown"),
            "updated_at": location_data.get("updated_at")
        }
    except Exception as e:
        return {"error": str(e), "timezone": "UTC"}


def _get_current_time() -> Dict[str, Any]:
    """Get current time in user's timezone."""
    try:
        from zoneinfo import ZoneInfo
        
        # Get user timezone
        result = supabase.table("sync_state").select("value").eq(
            "key", "user_timezone"
        ).limit(1).execute()
        
        user_tz = "UTC"
        if result.data:
            user_tz = result.data[0]["value"]
        
        try:
            tz = ZoneInfo(user_tz)
        except Exception:
            tz = ZoneInfo("UTC")
            user_tz = "UTC"
        
        now = datetime.now(tz)
        
        return {
            "timezone": user_tz,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "iso": now.isoformat(),
            "utc_offset": now.strftime("%z")
        }
    except Exception as e:
        # Fallback to UTC
        now = datetime.now(timezone.utc)
        return {
            "timezone": "UTC",
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "iso": now.isoformat(),
            "error": str(e)
        }


# =============================================================================
# BOOKS & HIGHLIGHTS TOOLS
# =============================================================================

def _get_books(input: Dict) -> Dict[str, Any]:
    """Get books from reading list."""
    try:
        status = input.get("status", "all")
        author = input.get("author", "")
        search = input.get("search", "")
        limit = input.get("limit", 10)
        
        query = supabase.table("books").select(
            "id, title, author, status, rating, current_page, total_pages, "
            "progress_percent, started_at, finished_at, summary, notes, tags"
        ).is_("deleted_at", "null")
        
        if status and status != "all":
            query = query.eq("status", status)
        
        if author:
            query = query.ilike("author", f"%{author}%")
        
        if search:
            # Search in title, author, notes
            query = query.or_(f"title.ilike.%{search}%,author.ilike.%{search}%,notes.ilike.%{search}%")
        
        result = query.order("updated_at", desc=True).limit(limit).execute()
        
        books = []
        for b in result.data or []:
            book_info = {
                "id": b["id"],
                "title": b["title"],
                "author": b.get("author", "Unknown"),
                "status": b.get("status", "Unknown"),
            }
            
            # Add progress for books being read
            if b.get("current_page") and b.get("total_pages"):
                book_info["progress"] = f"{b['current_page']}/{b['total_pages']} ({b.get('progress_percent', 0)}%)"
            
            if b.get("rating"):
                book_info["rating"] = f"{'⭐' * b['rating']}"
            
            if b.get("started_at"):
                book_info["started"] = b["started_at"]
            
            if b.get("finished_at"):
                book_info["finished"] = b["finished_at"]
            
            if b.get("summary"):
                book_info["summary"] = b["summary"][:200] + "..." if len(b.get("summary", "")) > 200 else b.get("summary")
            
            if b.get("tags"):
                book_info["tags"] = b["tags"]
            
            books.append(book_info)
        
        return {
            "books": books,
            "count": len(books),
            "filter": {"status": status, "author": author or None, "search": search or None}
        }
    except Exception as e:
        logger.error(f"Error getting books: {e}")
        return {"error": str(e), "books": []}


def _get_highlights(input: Dict) -> Dict[str, Any]:
    """Get book highlights and annotations."""
    try:
        book_title = input.get("book_title", "")
        search = input.get("search", "")
        favorites_only = input.get("favorites_only", False)
        days = input.get("days", 90)
        limit = input.get("limit", 20)
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        query = supabase.table("highlights").select(
            "id, book_title, content, note, page_number, chapter, "
            "highlight_type, tags, is_favorite, highlighted_at, created_at"
        ).is_("deleted_at", "null").gte("created_at", cutoff)
        
        if book_title:
            query = query.ilike("book_title", f"%{book_title}%")
        
        if search:
            query = query.or_(f"content.ilike.%{search}%,note.ilike.%{search}%")
        
        if favorites_only:
            query = query.eq("is_favorite", True)
        
        result = query.order("created_at", desc=True).limit(limit).execute()
        
        highlights = []
        for h in result.data or []:
            highlight_info = {
                "book": h.get("book_title", "Unknown"),
                "content": h["content"][:300] + "..." if len(h.get("content", "")) > 300 else h.get("content"),
            }
            
            if h.get("note"):
                highlight_info["my_note"] = h["note"]
            
            if h.get("chapter"):
                highlight_info["chapter"] = h["chapter"]
            elif h.get("page_number"):
                highlight_info["page"] = h["page_number"]
            
            if h.get("is_favorite"):
                highlight_info["favorite"] = True
            
            if h.get("tags"):
                highlight_info["tags"] = h["tags"]
            
            highlights.append(highlight_info)
        
        return {
            "highlights": highlights,
            "count": len(highlights),
            "filter": {"book": book_title or None, "search": search or None, "favorites_only": favorites_only}
        }
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return {"error": str(e), "highlights": []}


def _search_reading_notes(input: Dict) -> Dict[str, Any]:
    """Search across books and highlights."""
    try:
        query_text = input.get("query", "")
        limit = input.get("limit", 15)
        
        if not query_text:
            return {"error": "Query is required"}
        
        results = {"books": [], "highlights": []}
        
        # Search books
        books_result = supabase.table("books").select(
            "id, title, author, status, summary, notes"
        ).is_("deleted_at", "null").or_(
            f"title.ilike.%{query_text}%,author.ilike.%{query_text}%,"
            f"summary.ilike.%{query_text}%,notes.ilike.%{query_text}%"
        ).limit(5).execute()
        
        for b in books_result.data or []:
            results["books"].append({
                "title": b["title"],
                "author": b.get("author"),
                "status": b.get("status"),
                "summary_snippet": (b.get("summary") or "")[:150] + "..." if b.get("summary") else None
            })
        
        # Search highlights
        highlights_result = supabase.table("highlights").select(
            "id, book_title, content, note, chapter"
        ).is_("deleted_at", "null").or_(
            f"content.ilike.%{query_text}%,note.ilike.%{query_text}%"
        ).limit(limit - 5).execute()
        
        for h in highlights_result.data or []:
            results["highlights"].append({
                "book": h.get("book_title"),
                "content": h["content"][:200] + "..." if len(h.get("content", "")) > 200 else h.get("content"),
                "note": h.get("note"),
                "chapter": h.get("chapter")
            })
        
        return {
            "query": query_text,
            "results": results,
            "total_found": len(results["books"]) + len(results["highlights"])
        }
    except Exception as e:
        logger.error(f"Error searching reading notes: {e}")
        return {"error": str(e)}


# =============================================================================
# RECENT VOICE MEMO CONTEXT
# =============================================================================

def _get_recent_voice_memo(input: Dict) -> Dict[str, Any]:
    """Get the most recently processed voice memo and what was created from it."""
    try:
        include_transcript = input.get("include_transcript", True)
        
        # Get the most recent transcript
        transcript_result = supabase.table("transcripts").select(
            "id, full_text, source_file, created_at, language"
        ).order("created_at", desc=True).limit(1).execute()
        
        if not transcript_result.data:
            return {"error": "No voice memos found"}
        
        transcript = transcript_result.data[0]
        transcript_id = transcript["id"]
        
        result = {
            "transcript_id": transcript_id,
            "recorded_at": transcript["created_at"],
            "source_file": transcript.get("source_file"),
            "language": transcript.get("language"),
            "created_items": {}
        }
        
        if include_transcript:
            full_text = transcript.get("full_text", "")
            result["transcript"] = full_text[:2000] + "..." if len(full_text) > 2000 else full_text
            result["transcript_length"] = len(full_text)
        
        # Find meetings created from this transcript
        meetings = supabase.table("meetings").select(
            "id, title, summary, contact_name, date"
        ).eq("transcript_id", transcript_id).execute()
        
        if meetings.data:
            result["created_items"]["meetings"] = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "summary": m.get("summary", "")[:200] + "..." if m.get("summary") and len(m.get("summary", "")) > 200 else m.get("summary"),
                    "contact": m.get("contact_name"),
                    "date": m.get("date")
                }
                for m in meetings.data
            ]
        
        # Find journals (check by date - journals from same day)
        transcript_date = transcript["created_at"][:10]  # YYYY-MM-DD
        journals = supabase.table("journals").select(
            "id, date, title, content, mood"
        ).eq("date", transcript_date).limit(1).execute()
        
        if journals.data:
            j = journals.data[0]
            result["created_items"]["journal"] = {
                "id": j["id"],
                "date": j["date"],
                "title": j.get("title"),
                "content_preview": j.get("content", "")[:300] + "..." if j.get("content") and len(j.get("content", "")) > 300 else j.get("content"),
                "mood": j.get("mood")
            }
        
        # Find reflections created from this transcript
        reflections = supabase.table("reflections").select(
            "id, title, topic_key, content, tags"
        ).eq("transcript_id", transcript_id).execute()
        
        if reflections.data:
            result["created_items"]["reflections"] = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "topic": r.get("topic_key"),
                    "content_preview": r.get("content", "")[:200] + "..." if r.get("content") and len(r.get("content", "")) > 200 else r.get("content"),
                    "tags": r.get("tags")
                }
                for r in reflections.data
            ]
        
        # Find tasks linked to these items
        origin_ids = []
        if meetings.data:
            origin_ids.extend([m["id"] for m in meetings.data])
        if reflections.data:
            origin_ids.extend([r["id"] for r in reflections.data])
        if journals.data:
            origin_ids.extend([j["id"] for j in journals.data])
        
        if origin_ids:
            tasks = supabase.table("tasks").select(
                "id, title, status, priority, due_date, origin_type"
            ).in_("origin_id", origin_ids).execute()
            
            if tasks.data:
                result["created_items"]["tasks"] = [
                    {
                        "id": t["id"],
                        "title": t["title"],
                        "status": t.get("status"),
                        "priority": t.get("priority"),
                        "due_date": t.get("due_date"),
                        "from": t.get("origin_type")
                    }
                    for t in tasks.data
                ]
        
        # Summary
        item_counts = []
        if result["created_items"].get("meetings"):
            item_counts.append(f"{len(result['created_items']['meetings'])} meeting(s)")
        if result["created_items"].get("journal"):
            item_counts.append("1 journal entry")
        if result["created_items"].get("reflections"):
            item_counts.append(f"{len(result['created_items']['reflections'])} reflection(s)")
        if result["created_items"].get("tasks"):
            item_counts.append(f"{len(result['created_items']['tasks'])} task(s)")
        
        result["summary"] = f"From your last voice memo, I created: {', '.join(item_counts)}" if item_counts else "No structured items were created from this voice memo"
        
        return result
    except Exception as e:
        logger.error(f"Error getting recent voice memo: {e}")
        return {"error": str(e)}


def _create_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a calendar event via the sync service."""
    import httpx
    import os
    
    title = params.get("title")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    description = params.get("description")
    location = params.get("location")
    attendees = params.get("attendees", [])
    
    if not title or not start_time or not end_time:
        return {"error": "Missing required fields: title, start_time, end_time"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        # Call the sync service to create the event
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/create",
                json={
                    "summary": title,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description,
                    "location": location,
                    "attendees": attendees
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                event_link = result.get("html_link", "")
                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": f"✅ Calendar event '{title}' created successfully!",
                    "details": {
                        "title": title,
                        "start": start_time,
                        "end": end_time,
                        "location": location,
                        "attendees": attendees,
                        "link": event_link
                    }
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to create calendar event: {error_detail}"}
                
    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar creation")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        return {"error": str(e)}


def _update_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Update/reschedule an existing calendar event."""
    import httpx
    import os
    
    event_id = params.get("event_id")
    title = params.get("title")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    description = params.get("description")
    location = params.get("location")
    send_updates = params.get("send_updates", "all")
    
    if not event_id:
        return {"error": "Missing required field: event_id"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        payload = {"event_id": event_id, "send_updates": send_updates}
        if title:
            payload["summary"] = title
        if start_time:
            payload["start_time"] = start_time
        if end_time:
            payload["end_time"] = end_time
        if description:
            payload["description"] = description
        if location:
            payload["location"] = location
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/update",
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                event_link = result.get("html_link", "")
                
                changes = []
                if start_time or end_time:
                    changes.append("time")
                if description:
                    changes.append("details")
                if location:
                    changes.append("location")
                
                change_desc = " and ".join(changes) if changes else "meeting"
                
                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": f"✅ Calendar event rescheduled! Updated {change_desc}. All attendees have been notified.",
                    "details": {
                        "title": result.get("summary"),
                        "start": result.get("start"),
                        "end": result.get("end"),
                        "link": event_link
                    }
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to update calendar event: {error_detail}"}
                
    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar update")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error updating calendar event: {e}")
        return {"error": str(e)}


def _decline_calendar_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Decline a calendar invitation."""
    import httpx
    import os
    
    event_id = params.get("event_id")
    comment = params.get("comment")
    
    if not event_id:
        return {"error": "Missing required field: event_id"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        payload = {"event_id": event_id}
        if comment:
            payload["comment"] = comment
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/calendar/decline",
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                
                msg = f"✅ Declined the calendar invitation for '{result.get('summary', 'the meeting')}'"
                if comment:
                    msg += f" with message: '{comment}'"
                msg += ". The organizer has been notified."
                
                return {
                    "success": True,
                    "event_id": result.get("event_id"),
                    "message": msg,
                    "response_status": "declined"
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to decline calendar event: {error_detail}"}
                
    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for calendar decline")
        return {"error": "Calendar service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error declining calendar event: {e}")
        return {"error": str(e)}


def _create_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create an email draft in Gmail."""
    import httpx
    import os
    
    to = params.get("to")
    to_name = params.get("to_name")
    subject = params.get("subject", "")
    body = params.get("body", "")
    cc = params.get("cc")
    reply_to_message_id = params.get("reply_to_message_id")
    
    # If no email but name provided, try to look it up
    if not to and to_name:
        try:
            result = supabase.table("contacts").select(
                "id, first_name, last_name, email"
            ).or_(
                f"first_name.ilike.%{to_name}%,last_name.ilike.%{to_name}%"
            ).limit(5).execute()
            
            if result.data:
                contacts_with_email = [c for c in result.data if c.get("email")]
                if len(contacts_with_email) == 1:
                    contact = contacts_with_email[0]
                    to = contact["email"]
                    to_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                elif len(contacts_with_email) > 1:
                    return {
                        "needs_clarification": True,
                        "message": f"Found multiple contacts matching '{to_name}':",
                        "contacts": [
                            {
                                "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                                "email": c.get("email")
                            }
                            for c in contacts_with_email
                        ],
                        "instruction": "Please specify which email address to use."
                    }
                else:
                    return {
                        "needs_clarification": True,
                        "message": f"Could not find email for '{to_name}'.",
                        "instruction": "Please provide the email address directly."
                    }
        except Exception as e:
            logger.error(f"Error looking up contact email: {e}")
            return {"error": f"Could not look up contact: {str(e)}"}
    
    if not to:
        return {
            "needs_clarification": True,
            "message": "No recipient email address provided.",
            "instruction": "Please specify who to send this email to."
        }
    
    if not subject or not body:
        return {"error": "Missing required fields: subject, body"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/gmail/drafts",
                json={
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "cc": cc,
                    "reply_to_message_id": reply_to_message_id,
                    "is_html": False
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "draft_id": result.get("draft_id"),
                    "message": "📧 **Draft created and saved to Gmail!**",
                    "draft": {
                        "to": to,
                        "to_name": to_name,
                        "subject": subject,
                        "body": body[:200] + "..." if len(body) > 200 else body
                    },
                    "instruction": "The draft is now in your Gmail Drafts folder. Say 'send it' to send, or 'delete it' to discard."
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Draft creation error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to create draft: {error_detail}"}
                
    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for draft creation")
        return {"error": "Email service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error creating draft: {e}")
        return {"error": str(e)}


def _list_email_drafts(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all email drafts from Gmail."""
    import httpx
    import os
    
    limit = params.get("limit", 10)
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{sync_service_url}/gmail/drafts",
                params={"limit": limit}
            )
            
            if response.status_code == 200:
                result = response.json()
                drafts = result.get("drafts", [])
                
                if not drafts:
                    return {"message": "No drafts found in your Gmail."}
                
                formatted_drafts = []
                for d in drafts:
                    formatted_drafts.append({
                        "draft_id": d.get("draft_id"),
                        "to": d.get("to", "No recipient"),
                        "subject": d.get("subject", "(No subject)"),
                        "preview": d.get("snippet", "")[:80]
                    })
                
                return {
                    "count": len(formatted_drafts),
                    "drafts": formatted_drafts,
                    "message": f"Found {len(formatted_drafts)} draft(s) in Gmail"
                }
            else:
                return {"error": f"Failed to list drafts: {response.text[:200]}"}
                
    except Exception as e:
        logger.error(f"Error listing drafts: {e}")
        return {"error": str(e)}


def _get_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get full content of a specific draft."""
    import httpx
    import os
    
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "Missing draft_id"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{sync_service_url}/gmail/drafts/{draft_id}")
            
            if response.status_code == 200:
                result = response.json()
                draft = result.get("draft", {})
                
                return {
                    "draft_id": draft.get("draft_id"),
                    "to": draft.get("to"),
                    "cc": draft.get("cc"),
                    "subject": draft.get("subject"),
                    "body": draft.get("body_text") or draft.get("body_html", ""),
                    "message": "📧 Draft details retrieved"
                }
            else:
                return {"error": f"Failed to get draft: {response.text[:200]}"}
                
    except Exception as e:
        logger.error(f"Error getting draft: {e}")
        return {"error": str(e)}


def _send_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Send an existing draft from Gmail."""
    import httpx
    import os
    
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "Missing draft_id"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{sync_service_url}/gmail/drafts/{draft_id}/send")
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "message": "✅ Email sent successfully!",
                    "message_id": result.get("message_id"),
                    "thread_id": result.get("thread_id")
                }
            else:
                return {"error": f"Failed to send draft: {response.text[:200]}"}
                
    except Exception as e:
        logger.error(f"Error sending draft: {e}")
        return {"error": str(e)}


def _delete_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a draft from Gmail."""
    import httpx
    import os
    
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "Missing draft_id"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(f"{sync_service_url}/gmail/drafts/{draft_id}")
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "message": "🗑️ Draft deleted successfully"
                }
            else:
                return {"error": f"Failed to delete draft: {response.text[:200]}"}
                
    except Exception as e:
        logger.error(f"Error deleting draft: {e}")
        return {"error": str(e)}


# =============================================================================
# BEEPER MESSAGING TOOLS
# =============================================================================

import os

# Beeper Bridge configuration
BEEPER_BRIDGE_URL = os.getenv("BEEPER_BRIDGE_URL", "https://beeper.new-world-project.com")
BEEPER_BRIDGE_API_KEY = os.getenv("BEEPER_BRIDGE_API_KEY", "")  # API key for secure bridge access


def _get_beeper_http_headers() -> Dict[str, str]:
    """Get HTTP headers for Beeper bridge requests (includes API key if configured)."""
    headers = {}
    if BEEPER_BRIDGE_API_KEY:
        headers["X-API-Key"] = BEEPER_BRIDGE_API_KEY
    return headers


def _get_beeper_inbox(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get Beeper inbox chats that need attention."""
    include_groups = params.get("include_groups", False)
    limit = params.get("limit", 10)
    
    try:
        # Get chats that need response (last message from other person)
        needs_response_query = supabase.table("beeper_chats") \
            .select("beeper_chat_id, platform, chat_type, chat_name, last_message_at, last_message_preview, unread_count, contact_id, needs_response, contact:contacts(id, first_name, last_name, company)") \
            .eq("chat_type", "dm") \
            .eq("is_archived", False) \
            .eq("needs_response", True) \
            .order("last_message_at", desc=True) \
            .limit(limit) \
            .execute()
        
        # Get other active DMs (last message from you)
        other_active_query = supabase.table("beeper_chats") \
            .select("beeper_chat_id, platform, chat_type, chat_name, last_message_at, last_message_preview, unread_count, contact_id, needs_response, contact:contacts(id, first_name, last_name, company)") \
            .eq("chat_type", "dm") \
            .eq("is_archived", False) \
            .eq("needs_response", False) \
            .order("last_message_at", desc=True) \
            .limit(limit) \
            .execute()
        
        def format_chat(chat):
            contact = chat.get("contact")
            contact_name = None
            if contact:
                contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            return {
                "beeper_chat_id": chat.get("beeper_chat_id"),
                "platform": chat.get("platform"),
                "chat_name": chat.get("chat_name"),
                "contact_name": contact_name,
                "contact_company": contact.get("company") if contact else None,
                "last_message_at": chat.get("last_message_at"),
                "last_message_preview": chat.get("last_message_preview"),
                "unread_count": chat.get("unread_count", 0)
            }
        
        needs_response = [format_chat(c) for c in needs_response_query.data]
        other_active = [format_chat(c) for c in other_active_query.data]
        
        result = {
            "needs_response": {
                "count": len(needs_response),
                "description": "These people are waiting for your reply",
                "chats": needs_response
            },
            "other_active": {
                "count": len(other_active),
                "description": "Ball is in their court - you sent the last message",
                "chats": other_active
            }
        }
        
        if include_groups:
            groups_query = supabase.table("beeper_chats") \
                .select("beeper_chat_id, platform, chat_type, chat_name, last_message_at, last_message_preview, unread_count") \
                .in_("chat_type", ["group", "channel"]) \
                .eq("is_archived", False) \
                .order("last_message_at", desc=True) \
                .limit(limit) \
                .execute()
            result["groups"] = {
                "count": len(groups_query.data),
                "chats": groups_query.data
            }
        
        # Summary message
        total_needs_response = len(needs_response)
        platforms = set(c["platform"] for c in needs_response + other_active)
        
        if total_needs_response > 0:
            result["summary"] = f"📬 {total_needs_response} chat(s) need your reply across {', '.join(platforms)}"
        else:
            result["summary"] = "✅ Inbox zero! No chats waiting for your reply."
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting Beeper inbox: {e}")
        return {"error": str(e)}


def _get_beeper_chat_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get messages from a specific Beeper chat."""
    beeper_chat_id = params.get("beeper_chat_id")
    limit = params.get("limit", 20)
    
    if not beeper_chat_id:
        return {"error": "Missing beeper_chat_id"}
    
    try:
        # Get chat info
        chat_result = supabase.table("beeper_chats") \
            .select("beeper_chat_id, platform, chat_name, contact:contacts(id, first_name, last_name, company)") \
            .eq("beeper_chat_id", beeper_chat_id) \
            .single() \
            .execute()
        
        chat = chat_result.data
        
        # Get messages
        messages_result = supabase.table("beeper_messages") \
            .select("beeper_event_id, content, content_description, sender_name, is_outgoing, timestamp, message_type, has_media") \
            .eq("beeper_chat_id", beeper_chat_id) \
            .order("timestamp", desc=True) \
            .limit(limit) \
            .execute()
        
        messages = []
        for m in messages_result.data:
            content = m.get("content")
            if not content and m.get("content_description"):
                content = f"[{m.get('content_description')}]"
            
            messages.append({
                "content": content,
                "sender": "You" if m.get("is_outgoing") else m.get("sender_name", "Them"),
                "timestamp": m.get("timestamp"),
                "type": m.get("message_type", "text"),
                "has_media": m.get("has_media", False)
            })
        
        # Reverse to show oldest first (chronological)
        messages.reverse()
        
        contact = chat.get("contact") if chat else None
        contact_name = None
        if contact:
            contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        
        return {
            "chat": {
                "platform": chat.get("platform") if chat else "unknown",
                "chat_name": chat.get("chat_name") if chat else beeper_chat_id,
                "contact_name": contact_name,
                "contact_company": contact.get("company") if contact else None
            },
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error getting chat messages: {e}")
        return {"error": str(e)}


def _search_beeper_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search across all Beeper messages."""
    query = params.get("query", "")
    platform = params.get("platform")
    contact_name = params.get("contact_name")
    limit = params.get("limit", 20)
    
    if not query:
        return {"error": "Missing search query"}
    
    try:
        # Build the query
        search_query = supabase.table("beeper_messages") \
            .select("beeper_event_id, beeper_chat_id, content, sender_name, is_outgoing, timestamp, platform, contact_id") \
            .ilike("content", f"%{query}%") \
            .order("timestamp", desc=True) \
            .limit(limit)
        
        if platform:
            search_query = search_query.eq("platform", platform)
        
        result = search_query.execute()
        
        # Get unique chat IDs to fetch chat info
        chat_ids = list(set(m.get("beeper_chat_id") for m in result.data))
        
        # Fetch chat info for context
        if chat_ids:
            chats_result = supabase.table("beeper_chats") \
                .select("beeper_chat_id, chat_name, platform, contact:contacts(first_name, last_name)") \
                .in_("beeper_chat_id", chat_ids) \
                .execute()
            
            chat_map = {c["beeper_chat_id"]: c for c in chats_result.data}
        else:
            chat_map = {}
        
        # Format messages with chat context
        messages = []
        for m in result.data:
            chat = chat_map.get(m.get("beeper_chat_id"), {})
            contact = chat.get("contact")
            contact_name_str = None
            if contact:
                contact_name_str = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            
            messages.append({
                "content": m.get("content"),
                "sender": "You" if m.get("is_outgoing") else m.get("sender_name", "Them"),
                "timestamp": m.get("timestamp"),
                "platform": m.get("platform"),
                "chat_name": chat.get("chat_name"),
                "contact_name": contact_name_str,
                "beeper_chat_id": m.get("beeper_chat_id")
            })
        
        return {
            "query": query,
            "count": len(messages),
            "messages": messages
        }
        
    except Exception as e:
        logger.error(f"Error searching messages: {e}")
        return {"error": str(e)}


def _get_beeper_contact_messages(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get all messages with a specific contact across all platforms."""
    contact_name = params.get("contact_name", "")
    limit = params.get("limit", 30)
    
    if not contact_name:
        return {"error": "Missing contact_name"}
    
    try:
        # First find the contact
        contact_result = supabase.table("contacts") \
            .select("id, first_name, last_name, company") \
            .or_(f"first_name.ilike.%{contact_name}%,last_name.ilike.%{contact_name}%") \
            .limit(1) \
            .execute()
        
        if not contact_result.data:
            # Try searching by chat name if no contact found
            chat_result = supabase.table("beeper_chats") \
                .select("beeper_chat_id, chat_name, platform") \
                .ilike("chat_name", f"%{contact_name}%") \
                .limit(5) \
                .execute()
            
            if not chat_result.data:
                return {"error": f"No contact or chat found matching '{contact_name}'"}
            
            # Get messages from these chats
            chat_ids = [c["beeper_chat_id"] for c in chat_result.data]
            messages_result = supabase.table("beeper_messages") \
                .select("content, content_description, sender_name, is_outgoing, timestamp, platform, beeper_chat_id") \
                .in_("beeper_chat_id", chat_ids) \
                .order("timestamp", desc=True) \
                .limit(limit) \
                .execute()
            
            messages = []
            for m in messages_result.data:
                content = m.get("content")
                if not content and m.get("content_description"):
                    content = f"[{m.get('content_description')}]"
                messages.append({
                    "content": content,
                    "sender": "You" if m.get("is_outgoing") else m.get("sender_name", contact_name),
                    "timestamp": m.get("timestamp"),
                    "platform": m.get("platform")
                })
            
            messages.reverse()
            
            return {
                "contact_name": contact_name,
                "found_via": "chat_name",
                "chats": [c["chat_name"] for c in chat_result.data],
                "messages": messages,
                "count": len(messages)
            }
        
        contact = contact_result.data[0]
        contact_id = contact["id"]
        contact_full_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        
        # Get messages where contact_id matches
        messages_result = supabase.table("beeper_messages") \
            .select("content, content_description, sender_name, is_outgoing, timestamp, platform, beeper_chat_id") \
            .eq("contact_id", contact_id) \
            .order("timestamp", desc=True) \
            .limit(limit) \
            .execute()
        
        messages = []
        for m in messages_result.data:
            content = m.get("content")
            if not content and m.get("content_description"):
                content = f"[{m.get('content_description')}]"
            messages.append({
                "content": content,
                "sender": "You" if m.get("is_outgoing") else contact_full_name,
                "timestamp": m.get("timestamp"),
                "platform": m.get("platform")
            })
        
        messages.reverse()
        
        return {
            "contact_name": contact_full_name,
            "company": contact.get("company"),
            "found_via": "contact_id",
            "messages": messages,
            "count": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error getting contact messages: {e}")
        return {"error": str(e)}


def _archive_beeper_chat(params: Dict[str, Any]) -> Dict[str, Any]:
    """Archive a Beeper chat."""
    beeper_chat_id = params.get("beeper_chat_id")
    
    if not beeper_chat_id:
        return {"error": "Missing beeper_chat_id"}
    
    try:
        result = supabase.table("beeper_chats") \
            .update({
                "is_archived": True,
                "needs_response": False,
                "archived_at": datetime.now(timezone.utc).isoformat()
            }) \
            .eq("beeper_chat_id", beeper_chat_id) \
            .execute()
        
        if result.data:
            return {
                "success": True,
                "message": "✅ Chat archived! It won't appear in your inbox until there's a new message."
            }
        else:
            return {"error": "Chat not found"}
        
    except Exception as e:
        logger.error(f"Error archiving chat: {e}")
        return {"error": str(e)}


def _send_beeper_message(params: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message to a Beeper chat."""
    import httpx
    import os
    import urllib.parse
    import re
    
    beeper_chat_id = params.get("beeper_chat_id")
    content = params.get("content")
    reply_to_event_id = params.get("reply_to_event_id")
    user_confirmed = params.get("user_confirmed", False)
    last_user_message = params.get("_last_user_message", "")
    
    logger.info(f"_send_beeper_message: chat_id={beeper_chat_id}, confirmed={user_confirmed}, content_len={len(content) if content else 0}")
    logger.info(f"_send_beeper_message: last_user_message='{last_user_message[:100]}'")
    
    if not beeper_chat_id:
        logger.warning("❌ Send failed: Missing beeper_chat_id")
        return {"error": "Missing beeper_chat_id"}
    if not content:
        logger.warning("❌ Send failed: Missing message content")
        return {"error": "Missing message content"}
    
    # CRITICAL: Verify ACTUAL user confirmation from their last message
    # The user_confirmed flag from Claude is NOT trustworthy - Claude lies about this
    confirmation_patterns = [
        r'^yes\b', r'^yeah\b', r'^yep\b', r'^ja\b', r'^yup\b',
        r'^ok\b', r'^okay\b', r'^sure\b', r'^go\b', r'^send\b',
        r'\bsend it\b', r'\bgo ahead\b', r'\bdo it\b', r'\bconfirm\b',
        r'^y$', r'^👍', r'^✅'
    ]
    
    user_msg_lower = last_user_message.lower().strip()
    is_actually_confirmed = any(re.search(pattern, user_msg_lower) for pattern in confirmation_patterns)
    
    logger.info(f"_send_beeper_message: actual_confirmation_check={is_actually_confirmed}")
    
    if not is_actually_confirmed:
        logger.warning(f"❌ BLOCKED: User message '{last_user_message[:50]}' is NOT a confirmation!")
        return {
            "error": "⚠️ I need your explicit confirmation before sending. Please reply with 'yes' or 'send it' to confirm.",
            "draft_ready": True,
            "recipient": beeper_chat_id,
            "message_preview": content[:100]
        }
    
    BEEPER_BRIDGE_URL = os.getenv("BEEPER_BRIDGE_URL", "https://beeper.new-world-project.com")
    logger.info(f"Using bridge URL: {BEEPER_BRIDGE_URL}")
    beeper_headers = _get_beeper_http_headers()
    
    try:
        # Get chat info for context
        chat_result = supabase.table("beeper_chats") \
            .select("chat_name, platform, contact:contacts(first_name, last_name)") \
            .eq("beeper_chat_id", beeper_chat_id) \
            .single() \
            .execute()
        
        chat = chat_result.data if chat_result.data else {}
        contact = chat.get("contact")
        recipient_name = chat.get("chat_name")
        if contact:
            recipient_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or recipient_name
        
        platform = chat.get("platform", "unknown")
        
        # URL encode the chat ID
        encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
        
        # Send via bridge
        payload = {"text": content}
        if reply_to_event_id:
            payload["reply_to"] = reply_to_event_id
        
        with httpx.Client(timeout=30.0, headers=beeper_headers) as client:
            response = client.post(
                f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/messages",
                json=payload
            )
            response.raise_for_status()
            result_data = response.json()
        
        # Update needs_response flag (you sent last message)
        supabase.table("beeper_chats") \
            .update({
                "needs_response": False,
                "last_message_preview": content[:100],
                "last_message_at": datetime.now(timezone.utc).isoformat()
            }) \
            .eq("beeper_chat_id", beeper_chat_id) \
            .execute()
        
        logger.info(f"Sent message to {recipient_name} on {platform}")
        
        return {
            "success": True,
            "message": f"✅ Message sent to {recipient_name} ({platform})",
            "event_id": result_data.get("event_id"),
            "recipient": recipient_name,
            "platform": platform
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error sending message: {e}")
        return {"error": f"Failed to send: {str(e)}"}
    except httpx.ConnectError:
        return {"error": "❌ Cannot connect to Beeper bridge. Is your laptop online with Beeper running?"}
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {"error": str(e)}


def _mark_beeper_read(params: Dict[str, Any]) -> Dict[str, Any]:
    """Mark all messages in a Beeper chat as read."""
    import httpx
    import os
    import urllib.parse
    
    beeper_chat_id = params.get("beeper_chat_id")
    
    if not beeper_chat_id:
        return {"error": "Missing beeper_chat_id"}
    
    beeper_headers = _get_beeper_http_headers()
    
    try:
        # URL encode the chat ID
        encoded_id = urllib.parse.quote(beeper_chat_id, safe='')
        
        with httpx.Client(timeout=30.0, headers=beeper_headers) as client:
            response = client.post(f"{BEEPER_BRIDGE_URL}/chats/{encoded_id}/read")
            response.raise_for_status()
        
        # Update unread count in database
        supabase.table("beeper_chats") \
            .update({"unread_count": 0}) \
            .eq("beeper_chat_id", beeper_chat_id) \
            .execute()
        
        return {
            "success": True,
            "message": "✅ Chat marked as read"
        }
        
    except httpx.ConnectError:
        return {"error": "❌ Cannot connect to Beeper bridge. Is your laptop online with Beeper running?"}
    except Exception as e:
        logger.error(f"Error marking chat as read: {e}")
        return {"error": str(e)}


def _unarchive_beeper_chat(params: Dict[str, Any]) -> Dict[str, Any]:
    """Unarchive a Beeper chat."""
    beeper_chat_id = params.get("beeper_chat_id")
    
    if not beeper_chat_id:
        return {"error": "Missing beeper_chat_id"}
    
    try:
        result = supabase.table("beeper_chats") \
            .update({
                "is_archived": False,
                "archived_at": None
            }) \
            .eq("beeper_chat_id", beeper_chat_id) \
            .execute()
        
        if result.data:
            return {
                "success": True,
                "message": "✅ Chat unarchived and back in your inbox"
            }
        else:
            return {"error": "Chat not found"}
        
    except Exception as e:
        logger.error(f"Error unarchiving chat: {e}")
        return {"error": str(e)}


def _get_beeper_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Get Beeper connectivity status."""
    import httpx
    import os
    
    BEEPER_BRIDGE_URL = os.getenv("BEEPER_BRIDGE_URL", "https://beeper.new-world-project.com")
    
    result = {
        "status": "unknown",
        "bridge_url": BEEPER_BRIDGE_URL,
        "db_stats": {},
        "platforms": []
    }
    
    # Get database stats
    try:
        chats_count = supabase.table("beeper_chats") \
            .select("id", count="exact") \
            .execute()
        messages_count = supabase.table("beeper_messages") \
            .select("id", count="exact") \
            .execute()
        needs_response = supabase.table("beeper_chats") \
            .select("id", count="exact") \
            .eq("needs_response", True) \
            .eq("is_archived", False) \
            .execute()
        
        result["db_stats"] = {
            "total_chats": chats_count.count or 0,
            "total_messages": messages_count.count or 0,
            "needs_response": needs_response.count or 0
        }
    except Exception as e:
        logger.warning(f"Failed to get DB stats: {e}")
    
    # Check bridge connectivity
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{BEEPER_BRIDGE_URL}/health")
            if resp.status_code == 200:
                bridge_data = resp.json()
                result["status"] = "connected" if bridge_data.get("beeper_connected") else "bridge_only"
                result["bridge_status"] = bridge_data.get("status")
                
                # Get accounts/platforms
                accounts = bridge_data.get("accounts")
                if accounts:
                    result["platforms"] = [a.get("platform") for a in accounts if a.get("platform")]
            else:
                result["status"] = "error"
    except httpx.ConnectError:
        result["status"] = "offline"
        result["message"] = "❌ Bridge not reachable. Is your laptop online with the bridge running?"
    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["message"] = "⏱️ Bridge connection timed out"
    except Exception as e:
        logger.warning(f"Failed to check bridge: {e}")
        result["status"] = "error"
    
    # Summary message
    if result["status"] == "connected":
        result["message"] = f"✅ Beeper connected! {result['db_stats'].get('needs_response', 0)} chats need your response."
    elif result["status"] == "bridge_only":
        result["message"] = "⚠️ Bridge running but Beeper Desktop not connected"
    
    return result


# =============================================================================
# MEMORY MANAGEMENT IMPLEMENTATIONS
# =============================================================================

def _run_async(coro):
    """Safely run async code from sync context."""
    import asyncio
    try:
        # Try to get the running loop (if in async context)
        loop = asyncio.get_running_loop()
        # We're in an async context - use nest_asyncio or create task
        # For simplicity, create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=30)
    except RuntimeError:
        # No running loop - safe to use asyncio.run
        return asyncio.run(coro)


def _remember_fact(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Store a fact in long-term memory."""
    from app.features.memory import get_memory_service, MemoryType
    
    fact = tool_input.get("fact", "").strip()
    memory_type_str = tool_input.get("memory_type", "fact").lower()
    
    if not fact:
        return {"error": "No fact provided to remember"}
    
    # Map string to MemoryType enum
    type_mapping = {
        "fact": MemoryType.FACT,
        "preference": MemoryType.PREFERENCE,
        "relationship": MemoryType.RELATIONSHIP,
        "interaction": MemoryType.INTERACTION,
        "insight": MemoryType.INSIGHT,
    }
    memory_type = type_mapping.get(memory_type_str, MemoryType.FACT)
    
    try:
        memory_service = get_memory_service()
        
        # Add memory with metadata
        result = _run_async(
            memory_service.add(
                content=fact,
                memory_type=memory_type,
                metadata={
                    "source": "chat",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            )
        )
        
        # Handle different result types (dict with status or legacy string/None)
        if isinstance(result, dict):
            status = result.get("status", "unknown")
            event = result.get("event", "UNKNOWN")
            memory_id = result.get("id")
            
            if status == "success":
                return {
                    "status": "remembered",
                    "memory_id": memory_id,
                    "event": event,
                    "fact": fact,
                    "type": memory_type_str,
                    "message": f"✅ Memory saved successfully: '{fact}'"
                }
            elif status == "deduplicated":
                return {
                    "status": "deduplicated",
                    "fact": fact,
                    "type": memory_type_str,
                    "message": f"ℹ️ Similar memory already exists. Mem0 merged or skipped: '{fact}'"
                }
            else:
                return {
                    "status": "failed",
                    "error": f"Memory operation failed with status: {status}",
                    "fact": fact
                }
        elif result:  # Legacy: string memory_id returned
            return {
                "status": "remembered",
                "memory_id": result,
                "fact": fact,
                "type": memory_type_str,
                "message": f"✅ Memory saved: '{fact}'"
            }
        else:
            return {
                "status": "failed",
                "error": "Failed to store memory - no result returned",
                "fact": fact
            }
            
    except Exception as e:
        logger.error(f"Failed to remember fact: {e}")
        return {
            "status": "error",
            "error": f"Failed to remember: {str(e)}",
            "fact": fact
        }


def _correct_memory(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Correct an existing memory by deleting old and adding new."""
    from app.features.memory import get_memory_service, MemoryType
    
    incorrect_info = tool_input.get("incorrect_info", "").strip()
    correct_info = tool_input.get("correct_info", "").strip()
    
    if not incorrect_info or not correct_info:
        return {"error": "Need both incorrect_info and correct_info"}
    
    try:
        memory_service = get_memory_service()
        
        # Search for memories matching the incorrect info
        memories = _run_async(memory_service.search(incorrect_info, limit=5))
        
        if not memories:
            # No existing memory found, just add the correct one
            memory_id = _run_async(
                memory_service.add(
                    content=correct_info,
                    memory_type=MemoryType.FACT,
                    metadata={"source": "chat_correction", "corrected_from": incorrect_info}
                )
            )
            return {
                "status": "added_new",
                "message": f"No existing memory found with '{incorrect_info}'. Created new memory: '{correct_info}'",
                "new_memory_id": memory_id
            }
        
        # Delete old memories matching the incorrect info
        deleted_count = 0
        deleted_items = []
        for mem in memories:
            mem_id = mem.get("id")
            mem_text = mem.get("memory", "") or mem.get("data", "")
            if mem_id and incorrect_info.lower() in mem_text.lower():
                success = _run_async(memory_service.delete(mem_id))
                if success:
                    deleted_count += 1
                    deleted_items.append({"id": mem_id, "content": mem_text[:80]})
        
        # Add the correct memory
        new_id = _run_async(
            memory_service.add(
                content=correct_info,
                memory_type=MemoryType.FACT,
                metadata={"source": "chat_correction", "corrected_from": incorrect_info}
            )
        )
        
        return {
            "status": "corrected",
            "deleted_count": deleted_count,
            "deleted_items": deleted_items,
            "new_memory_id": new_id,
            "new_content": correct_info,
            "message": f"✅ Corrected! Deleted {deleted_count} old memory/memories and added: '{correct_info}'"
        }
        
    except Exception as e:
        logger.error(f"Failed to correct memory: {e}")
        return {"error": f"Failed to correct: {str(e)}"}


def _search_memories(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search stored memories."""
    from app.features.memory import get_memory_service
    
    query = tool_input.get("query", "").strip()
    limit = tool_input.get("limit", 10)
    memory_type = tool_input.get("type")  # Optional type filter
    
    if not query:
        return {"error": "No search query provided"}
    
    try:
        memory_service = get_memory_service()
        
        memories = _run_async(memory_service.search(query, limit=limit))
        
        if not memories:
            return {
                "status": "no_results",
                "message": f"I don't have any memories about '{query}'",
                "memories": []
            }
        
        # Format memories with FULL metadata for display
        formatted = []
        for mem in memories:
            # Safely get metadata and payload with fallback to empty dict
            metadata = mem.get("metadata") or {}
            payload = mem.get("payload") or {}
            
            # Handle case where metadata/payload might still be None
            if not isinstance(metadata, dict):
                metadata = {}
            if not isinstance(payload, dict):
                payload = {}
            
            mem_type = metadata.get("type") or payload.get("type") or "fact"
            source = metadata.get("source") or payload.get("source") or "unknown"
            created_at = metadata.get("created_at") or payload.get("created_at") or metadata.get("added_at") or payload.get("added_at")
            
            formatted.append({
                "id": mem.get("id", ""),
                "content": mem.get("memory", "") or mem.get("data", "") or payload.get("data", ""),
                "type": mem_type,
                "source": source,
                "created_at": created_at,
            })
        
        # Optionally filter by type if specified
        if memory_type:
            formatted = [m for m in formatted if m["type"] == memory_type]
        
        return {
            "status": "found",
            "count": len(formatted),
            "memories": formatted,
            "message": f"Found {len(formatted)} memories about '{query}'"
        }
        
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        return {"error": f"Failed to search: {str(e)}"}


def _forget_memory(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a memory by ID or search query."""
    from app.features.memory import get_memory_service
    
    memory_id = tool_input.get("memory_id", "").strip()
    query = tool_input.get("query", "").strip()
    
    if not memory_id and not query:
        return {"error": "Provide either memory_id or query to specify what to forget"}
    
    try:
        memory_service = get_memory_service()
        
        # If specific ID provided, delete directly
        if memory_id:
            success = _run_async(memory_service.delete(memory_id))
            if success:
                return {
                    "status": "deleted",
                    "deleted_id": memory_id,
                    "message": f"✅ Deleted memory with ID: {memory_id}"
                }
            else:
                return {
                    "status": "FAILED",
                    "error": f"❌ DELETION FAILED for memory {memory_id} - may not exist or deletion error",
                    "message": f"❌ FAILED to delete memory {memory_id}"
                }
        
        # Otherwise search and delete matching memories
        memories = _run_async(memory_service.search(query, limit=10))
        
        if not memories:
            return {
                "status": "FAILED",
                "error": f"❌ NO MEMORIES FOUND matching '{query}' - nothing was deleted!",
                "message": f"❌ FAILED: No memories found matching '{query}'"
            }
        
        # Show what was found and delete matches
        deleted_items = []
        failed_items = []
        
        for mem in memories:
            mem_id = mem.get("id")
            mem_text = mem.get("memory", "") or mem.get("data", "")
            
            # Only delete if query appears in the memory text (case-insensitive)
            if mem_id and query.lower() in mem_text.lower():
                success = _run_async(memory_service.delete(mem_id))
                if success:
                    deleted_items.append({
                        "id": mem_id,
                        "content": mem_text[:100]
                    })
                else:
                    failed_items.append(mem_id)
        
        if not deleted_items and not failed_items:
            # THIS IS THE KEY FIX: This was returning a "helpful" message that the AI
            # didn't recognize as a failure. Now we return a clear ERROR status.
            found_previews = [f"- {m.get('memory', m.get('data', ''))[:60]}..." for m in memories[:5]]
            return {
                "status": "FAILED",
                "error": f"❌ DELETION FAILED: Found {len(memories)} memories but query '{query}' didn't match any exactly.",
                "found_count": len(memories),
                "found_previews": found_previews,
                "message": f"❌ FAILED to delete! Query '{query}' found {len(memories)} memories but none contained that exact text. You MUST use the exact memory ID to delete. Here are the memories found:\n" + "\n".join(found_previews)
            }
        
        return {
            "status": "deleted" if deleted_items else "FAILED",
            "deleted_count": len(deleted_items),
            "deleted_items": deleted_items,
            "failed_count": len(failed_items),
            "message": f"✅ Deleted {len(deleted_items)} memory/memories" if deleted_items else "❌ FAILED to delete any memories"
        }
        
    except Exception as e:
        logger.error(f"Failed to forget memory: {e}")
        return {"error": f"Failed to forget: {str(e)}"}


# =============================================================================
# CONVERSATION HISTORY TOOLS (LETTA)
# =============================================================================

async def _search_conversations(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search through past conversation history using Letta's archival memory."""
    try:
        from app.features.letta import get_letta_service
        
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 10)
        
        if not query:
            return {"error": "Query is required"}
        
        letta = get_letta_service()
        results = await letta.search_archival(query, limit=limit)
        
        if not results:
            # Fall back to raw message search in Supabase
            from app.features.chat.storage import get_chat_storage
            storage = get_chat_storage()
            raw_results = await storage.search_messages(query, limit=limit)
            
            if not raw_results:
                return {
                    "status": "no_results",
                    "message": f"No conversations found about '{query}'"
                }
            
            formatted = []
            for msg in raw_results:
                formatted.append({
                    "role": msg.get("role"),
                    "content": msg.get("content", "")[:500],
                    "timestamp": msg.get("created_at"),
                })
            
            return {
                "status": "found",
                "count": len(formatted),
                "source": "raw_history",
                "conversations": formatted,
                "message": f"Found {len(formatted)} messages about '{query}'"
            }
        
        return {
            "status": "found",
            "count": len(results),
            "source": "letta",
            "conversations": results,
            "message": f"Found {len(results)} conversation excerpts about '{query}'"
        }
        
    except Exception as e:
        logger.error(f"Failed to search conversations: {e}")
        return {"error": f"Failed to search conversations: {str(e)}"}


# =============================================================================
# DOCUMENT TOOLS
# =============================================================================

async def _search_documents(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search personal documents (CV, profiles, applications, notes)."""
    try:
        from app.features.documents import get_document_service
        
        query = tool_input.get("query", "")
        doc_type = tool_input.get("document_type")
        limit = tool_input.get("limit", 3)
        
        if not query:
            return {"error": "Query is required"}
        
        doc_service = get_document_service()
        docs = await doc_service.search_documents(
            query=query,
            document_type=doc_type,
            limit=limit
        )
        
        if not docs:
            return {
                "status": "no_results",
                "message": f"No documents found matching '{query}'"
            }
        
        results = []
        for doc in docs:
            content = doc.get("content", "")
            # Truncate content for response
            snippet = content[:1000] + "..." if len(content) > 1000 else content
            results.append({
                "id": doc.get("id"),
                "title": doc.get("title"),
                "type": doc.get("type"),
                "content_snippet": snippet,
                "tags": doc.get("tags", [])
            })
        
        return {
            "status": "found",
            "count": len(results),
            "documents": results
        }
        
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        return {"error": f"Document search failed: {str(e)}"}


async def _get_document_content(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get full content of a document by type."""
    try:
        from app.features.documents import get_document_service
        
        doc_type = tool_input.get("document_type")
        title = tool_input.get("title")
        
        if not doc_type:
            return {"error": "document_type is required"}
        
        doc_service = get_document_service()
        docs = await doc_service.list_documents(document_type=doc_type, limit=10)
        
        if not docs:
            return {
                "status": "not_found",
                "message": f"No {doc_type} documents found"
            }
        
        # If title specified, find exact match
        if title:
            matching = [d for d in docs if title.lower() in d.get("title", "").lower()]
            if not matching:
                return {
                    "status": "not_found",
                    "message": f"No {doc_type} document with title '{title}' found"
                }
            doc_id = matching[0]["id"]
        else:
            # Get the most recent document of that type
            doc_id = docs[0]["id"]
        
        # Get full document
        doc = await doc_service.get_document(doc_id)
        
        if not doc:
            return {"error": "Document not found"}
        
        return {
            "status": "found",
            "document": {
                "id": doc.get("id"),
                "title": doc.get("title"),
                "type": doc.get("type"),
                "content": doc.get("content", ""),
                "tags": doc.get("tags", []),
                "word_count": doc.get("word_count", 0),
                "created_at": doc.get("created_at")
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get document content: {e}")
        return {"error": f"Failed to get document: {str(e)}"}


# =============================================================================
# APPLICATIONS TOOLS IMPLEMENTATION
# =============================================================================

def _get_applications(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get a list of applications with optional filters."""
    try:
        query = supabase.table("applications").select(
            "id, name, application_type, status, institution, website, grant_amount, deadline, context, notes, created_at"
        )
        
        # Apply filters
        if tool_input.get("status"):
            query = query.eq("status", tool_input["status"])
        
        if tool_input.get("application_type"):
            query = query.eq("application_type", tool_input["application_type"])
        
        # Limit
        limit = min(tool_input.get("limit", 20), 50)
        query = query.order("deadline", desc=False, nullsfirst=False).limit(limit)
        
        result = query.execute()
        
        applications = []
        for app in result.data or []:
            applications.append({
                "id": app.get("id"),
                "name": app.get("name"),
                "type": app.get("application_type"),
                "status": app.get("status"),
                "institution": app.get("institution"),
                "website": app.get("website"),
                "grant_amount": app.get("grant_amount"),
                "deadline": app.get("deadline"),
                "context": app.get("context", "")[:200] if app.get("context") else None,
                "notes": app.get("notes", "")[:200] if app.get("notes") else None
            })
        
        return {"applications": applications, "count": len(applications)}
    except Exception as e:
        logger.error(f"Failed to get applications: {e}")
        return {"error": str(e)}


def _search_applications(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search applications by name, institution, or content."""
    try:
        query_str = tool_input.get("query", "")
        limit = min(tool_input.get("limit", 10), 50)
        
        if not query_str:
            return {"error": "query is required"}
        
        # Escape special characters for ILIKE
        query_str = query_str.replace("%", "\\%").replace("_", "\\_")
        
        # Search across name, institution, context, notes, and content
        # Note: Fetching content for snippet generation
        result = supabase.table("applications").select(
            "id, name, application_type, status, institution, website, grant_amount, deadline, context, notes, content"
        ).or_(
            f"name.ilike.%{query_str}%,institution.ilike.%{query_str}%,context.ilike.%{query_str}%,notes.ilike.%{query_str}%,content.ilike.%{query_str}%"
        ).order("deadline", desc=False, nullsfirst=False).limit(limit).execute()
        
        applications = []
        for app in result.data or []:
            # Create snippet from content if available
            content = app.get("content", "") or ""
            snippet = None
            if query_str.lower() in content.lower():
                # Find context around the match
                idx = content.lower().find(query_str.lower())
                start = max(0, idx - 100)
                end = min(len(content), idx + len(query_str) + 100)
                snippet = "..." + content[start:end] + "..."
            
            applications.append({
                "id": app.get("id"),
                "name": app.get("name"),
                "type": app.get("application_type"),
                "status": app.get("status"),
                "institution": app.get("institution"),
                "deadline": app.get("deadline"),
                "grant_amount": app.get("grant_amount"),
                "context": app.get("context"),
                "content_snippet": snippet
            })
        
        return {"applications": applications, "count": len(applications)}
    except Exception as e:
        logger.error(f"Failed to search applications: {e}")
        return {"error": str(e)}


def _get_application_content(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get full content of a specific application."""
    try:
        app_id = tool_input.get("application_id")
        app_name = tool_input.get("application_name")
        
        if not app_id and not app_name:
            return {"error": "Either application_id or application_name is required"}
        
        if app_id:
            result = supabase.table("applications").select("*").eq("id", app_id).execute()
        else:
            result = supabase.table("applications").select("*").ilike("name", f"%{app_name}%").limit(1).execute()
        
        if not result.data:
            return {"error": "Application not found"}
        
        app = result.data[0]
        return {
            "application": {
                "id": app.get("id"),
                "name": app.get("name"),
                "type": app.get("application_type"),
                "status": app.get("status"),
                "institution": app.get("institution"),
                "website": app.get("website"),
                "grant_amount": app.get("grant_amount"),
                "deadline": app.get("deadline"),
                "context": app.get("context"),
                "notes": app.get("notes"),
                "content": app.get("content"),  # Full content
                "created_at": app.get("created_at")
            }
        }
    except Exception as e:
        logger.error(f"Failed to get application content: {e}")
        return {"error": str(e)}


# =============================================================================
# LINKEDIN POSTS TOOLS IMPLEMENTATION
# =============================================================================

def _get_linkedin_posts(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get a list of LinkedIn posts with optional filters."""
    try:
        query = supabase.table("linkedin_posts").select(
            "id, title, post_date, status, pillar, likes, created_at"
        )
        
        # Apply filters
        if tool_input.get("status"):
            query = query.eq("status", tool_input["status"])
        
        if tool_input.get("pillar"):
            query = query.eq("pillar", tool_input["pillar"])
        
        # Limit and order
        limit = min(tool_input.get("limit", 20), 50)
        query = query.order("post_date", desc=True, nullsfirst=False).limit(limit)
        
        result = query.execute()
        
        posts = []
        for post in result.data or []:
            posts.append({
                "id": post.get("id"),
                "title": post.get("title"),
                "post_date": post.get("post_date"),
                "status": post.get("status"),
                "pillar": post.get("pillar"),
                "likes": post.get("likes")
            })
        
        return {"posts": posts, "count": len(posts)}
    except Exception as e:
        logger.error(f"Failed to get LinkedIn posts: {e}")
        return {"error": str(e)}


def _search_linkedin_posts(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search LinkedIn posts by title or content."""
    try:
        query_str = tool_input.get("query", "")
        limit = min(tool_input.get("limit", 10), 50)
        
        if not query_str:
            return {"error": "query is required"}
        
        # Escape special characters for ILIKE
        query_str = query_str.replace("%", "\\%").replace("_", "\\_")
        
        # Search across title and content
        result = supabase.table("linkedin_posts").select(
            "id, title, post_date, status, pillar, likes, content"
        ).or_(
            f"title.ilike.%{query_str}%,content.ilike.%{query_str}%"
        ).order("post_date", desc=True).limit(limit).execute()
        
        posts = []
        for post in result.data or []:
            # Create snippet from content if available
            content = post.get("content", "") or ""
            snippet = None
            if content:
                # If search term is in content, show context
                if query_str.lower() in content.lower():
                    idx = content.lower().find(query_str.lower())
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(query_str) + 100)
                    snippet = "..." + content[start:end] + "..."
                else:
                    # Just show first 200 chars
                    snippet = content[:200] + "..." if len(content) > 200 else content
            
            posts.append({
                "id": post.get("id"),
                "title": post.get("title"),
                "post_date": post.get("post_date"),
                "status": post.get("status"),
                "pillar": post.get("pillar"),
                "likes": post.get("likes"),
                "content_snippet": snippet
            })
        
        return {"posts": posts, "count": len(posts)}
    except Exception as e:
        logger.error(f"Failed to search LinkedIn posts: {e}")
        return {"error": str(e)}


def _get_linkedin_post_content(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get full content of a specific LinkedIn post."""
    try:
        post_id = tool_input.get("post_id")
        post_title = tool_input.get("post_title")
        
        if not post_id and not post_title:
            return {"error": "Either post_id or post_title is required"}
        
        if post_id:
            result = supabase.table("linkedin_posts").select("*").eq("id", post_id).execute()
        else:
            result = supabase.table("linkedin_posts").select("*").ilike("title", f"%{post_title}%").limit(1).execute()
        
        if not result.data:
            return {"error": "LinkedIn post not found"}
        
        post = result.data[0]
        return {
            "post": {
                "id": post.get("id"),
                "title": post.get("title"),
                "post_date": post.get("post_date"),
                "status": post.get("status"),
                "pillar": post.get("pillar"),
                "likes": post.get("likes"),
                "content": post.get("content"),  # Full content
                "created_at": post.get("created_at")
            }
        }
    except Exception as e:
        logger.error(f"Failed to get LinkedIn post content: {e}")
        return {"error": str(e)}


# =============================================================================
# DATABASE SCHEMA TOOLS - For creating/modifying database structure
# =============================================================================

def _list_database_tables(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """List all tables and their columns in the database."""
    try:
        # Query PostgreSQL information schema
        # Using RPC call since Supabase doesn't expose information_schema directly
        # We'll use a workaround by checking known tables
        
        known_tables = [
            "contacts", "meetings", "tasks", "journals", "reflections",
            "calendar_events", "emails", "transcripts", "books", "highlights",
            "applications", "linkedin_posts", "beeper_chats", "beeper_messages",
            "sync_logs", "sync_state", "chat_messages", "scheduled_briefings"
        ]
        
        tables_info = []
        for table_name in known_tables:
            try:
                # Try to select from table to get column info
                result = supabase.table(table_name).select("*").limit(1).execute()
                if result.data:
                    columns = list(result.data[0].keys())
                else:
                    # Table exists but empty - try to get schema another way
                    columns = ["(table exists, no sample data)"]
                tables_info.append({
                    "table": table_name,
                    "columns": columns,
                    "status": "accessible"
                })
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    tables_info.append({
                        "table": table_name,
                        "columns": [],
                        "status": f"error: {str(e)[:50]}"
                    })
        
        return {
            "status": "success",
            "tables": tables_info,
            "total_tables": len(tables_info),
            "note": "Use query_database for detailed column types"
        }
    except Exception as e:
        logger.error(f"Failed to list tables: {e}")
        return {"error": str(e)}


def _create_database_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new table in the database.
    
    IMPORTANT: Requires user_confirmed=true to execute.
    """
    try:
        table_name = tool_input.get("table_name", "").lower().strip()
        columns = tool_input.get("columns", [])
        user_confirmed = tool_input.get("user_confirmed", False)
        
        if not table_name:
            return {"error": "table_name is required"}
        
        if not columns:
            return {"error": "columns list is required"}
        
        # Validate table name
        import re
        if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
            return {"error": "Table name must start with letter, contain only lowercase letters, numbers, underscores"}
        
        # Don't allow overwriting system tables
        protected_tables = [
            "contacts", "meetings", "tasks", "journals", "reflections",
            "calendar_events", "emails", "transcripts", "sync_logs"
        ]
        if table_name in protected_tables:
            return {"error": f"Cannot create table '{table_name}' - it's a protected system table"}
        
        if not user_confirmed:
            # Generate preview SQL
            column_defs = []
            for col in columns:
                col_def = f"  {col['name']} {col['type'].upper()}"
                if not col.get("nullable", True):
                    col_def += " NOT NULL"
                if col.get("default"):
                    col_def += f" DEFAULT {col['default']}"
                if col.get("unique"):
                    col_def += " UNIQUE"
                column_defs.append(col_def)
            
            preview_sql = f"""CREATE TABLE {table_name} (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
{chr(10).join(column_defs)},
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);"""
            return {
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Ready to create table '{table_name}'. Please confirm.",
                "preview_sql": preview_sql,
                "columns": columns,
                "instructions": "Call this tool again with user_confirmed=true to create the table"
            }
        
        # Build and execute CREATE TABLE
        column_defs = ["id UUID PRIMARY KEY DEFAULT gen_random_uuid()"]
        for col in columns:
            col_def = f"{col['name']} {col['type'].upper()}"
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("default"):
                col_def += f" DEFAULT {col['default']}"
            if col.get("unique"):
                col_def += " UNIQUE"
            column_defs.append(col_def)
        column_defs.append("created_at TIMESTAMPTZ DEFAULT NOW()")
        column_defs.append("updated_at TIMESTAMPTZ DEFAULT NOW()")
        
        create_sql = f"CREATE TABLE {table_name} ({', '.join(column_defs)})"
        
        # Execute via Supabase RPC or direct SQL
        # Note: This requires the service role key with DDL permissions
        result = supabase.rpc("exec_sql", {"query": create_sql}).execute()
        
        logger.info(f"Created table: {table_name}")
        return {
            "status": "success",
            "message": f"Table '{table_name}' created successfully",
            "table_name": table_name,
            "columns_created": len(columns) + 3  # +3 for id, created_at, updated_at
        }
    except Exception as e:
        error_msg = str(e)
        if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
            return {
                "error": "Database does not support direct DDL. Table creation requires manual setup or admin access.",
                "workaround": "Ask the user to create the table manually in Supabase dashboard"
            }
        logger.error(f"Failed to create table: {e}")
        return {"error": str(e)}


def _add_column_to_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Add a column to an existing table."""
    try:
        table_name = tool_input.get("table_name", "").lower().strip()
        column_name = tool_input.get("column_name", "").lower().strip()
        column_type = tool_input.get("column_type", "").upper()
        nullable = tool_input.get("nullable", True)
        default_value = tool_input.get("default_value")
        user_confirmed = tool_input.get("user_confirmed", False)
        
        if not all([table_name, column_name, column_type]):
            return {"error": "table_name, column_name, and column_type are required"}
        
        if not user_confirmed:
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            if not nullable:
                alter_sql += " NOT NULL"
            if default_value:
                alter_sql += f" DEFAULT {default_value}"
            
            return {
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Ready to add column '{column_name}' to table '{table_name}'",
                "preview_sql": alter_sql,
                "instructions": "Call this tool again with user_confirmed=true to add the column"
            }
        
        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        if not nullable:
            alter_sql += " NOT NULL"
        if default_value:
            alter_sql += f" DEFAULT {default_value}"
        
        result = supabase.rpc("exec_sql", {"query": alter_sql}).execute()
        
        logger.info(f"Added column {column_name} to {table_name}")
        return {
            "status": "success",
            "message": f"Column '{column_name}' added to table '{table_name}'",
            "column_type": column_type
        }
    except Exception as e:
        error_msg = str(e)
        if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
            return {
                "error": "Database does not support direct DDL via API",
                "workaround": "Add the column manually in Supabase dashboard: Table Editor → Select table → Add Column"
            }
        logger.error(f"Failed to add column: {e}")
        return {"error": str(e)}


def _insert_data_batch(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Insert multiple rows into a table."""
    try:
        table_name = tool_input.get("table_name", "").strip()
        rows = tool_input.get("rows", [])
        
        if not table_name:
            return {"error": "table_name is required"}
        
        if not rows:
            return {"error": "rows array is required and must not be empty"}
        
        if len(rows) > 100:
            return {"error": f"Maximum 100 rows per batch (got {len(rows)}). Split into multiple calls."}
        
        # Insert data
        result = supabase.table(table_name).insert(rows).execute()
        
        inserted_count = len(result.data) if result.data else 0
        
        return {
            "status": "success",
            "message": f"Inserted {inserted_count} rows into '{table_name}'",
            "inserted_count": inserted_count,
            "sample_ids": [r.get("id") for r in (result.data or [])[:5]]
        }
    except Exception as e:
        logger.error(f"Failed to insert data: {e}")
        return {"error": str(e)}


def _get_database_backup_status(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Check backup status and recent backups."""
    try:
        from datetime import datetime
        
        # Check Supabase Storage for backups
        try:
            backups = supabase.storage.from_("backups").list()
            backup_files = [
                {
                    "name": f.get("name"),
                    "size": f.get("metadata", {}).get("size", "unknown"),
                    "created": f.get("created_at")
                }
                for f in (backups or [])
            ]
        except:
            backup_files = []
        
        # Check sync_logs for backup events
        try:
            logs = supabase.table("sync_logs").select("*").eq("event_type", "backup").order("created_at", desc=True).limit(10).execute()
            recent_backup_logs = logs.data or []
        except:
            recent_backup_logs = []
        
        return {
            "status": "success",
            "supabase_plan_info": "⚠️ FREE TIER - No automatic backups! Only Pro plan ($25/month) includes daily backups.",
            "backup_storage_files": backup_files[:10],
            "recent_backup_logs": recent_backup_logs,
            "manual_backup_available": True,
            "warning": "YOU ARE ON FREE TIER - Use backup_table tool regularly to create manual backups!",
            "recommendation": "Consider upgrading to Supabase Pro for automatic daily backups with 7-day retention"
        }
    except Exception as e:
        logger.error(f"Failed to get backup status: {e}")
        return {"error": str(e)}


def _backup_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Create a backup of a specific table."""
    import json
    from datetime import datetime
    
    try:
        table_name = tool_input.get("table_name", "").strip()
        
        if not table_name:
            return {"error": "table_name is required"}
        
        # Fetch all data from table (with pagination for large tables)
        all_rows = []
        page_size = 1000
        start = 0
        
        while True:
            result = supabase.table(table_name).select("*").range(start, start + page_size - 1).execute()
            batch = result.data or []
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
            if start > 10000:  # Safety limit
                break
        
        if not all_rows:
            return {
                "status": "warning",
                "message": f"Table '{table_name}' is empty - nothing to backup"
            }
        
        # Create backup JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_backup_{timestamp}.json"
        json_content = json.dumps(all_rows, indent=2, default=str)
        
        # Upload to Supabase Storage
        try:
            supabase.storage.from_("backups").upload(
                path=filename,
                file=json_content.encode('utf-8'),
                file_options={"content-type": "application/json", "upsert": "true"}
            )
            storage_status = "uploaded"
        except Exception as e:
            storage_status = f"upload failed: {str(e)[:50]}"
        
        # Log the backup
        try:
            supabase.table("sync_logs").insert({
                "event_type": "backup",
                "status": "success",
                "message": f"Backed up {len(all_rows)} rows from {table_name}",
                "details": {"table": table_name, "rows": len(all_rows), "filename": filename}
            }).execute()
        except:
            pass
        
        return {
            "status": "success",
            "message": f"Backed up {len(all_rows)} rows from '{table_name}'",
            "filename": filename,
            "rows_backed_up": len(all_rows),
            "storage_status": storage_status
        }
    except Exception as e:
        logger.error(f"Failed to backup table: {e}")
        return {"error": str(e)}


