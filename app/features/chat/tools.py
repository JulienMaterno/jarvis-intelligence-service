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
# TOOL DEFINITIONS (for Claude)
# =============================================================================

TOOLS = [
    {
        "name": "query_database",
        "description": """Execute a read-only SQL query against the knowledge database.
Use this to answer questions about meetings, contacts, tasks, reflections, emails, calendar events, etc.

Available tables:
- contacts: People in CRM (first_name, last_name, email, company, position, notes, birthday)
- meetings: Meeting records (title, date, summary, contact_name, topics_discussed, people_mentioned)
- tasks: Action items (title, description, status, priority, due_date, completed_at)
- reflections: Personal reflections (title, content, topic_key, tags, date)
- journals: Daily journals (date, summary, mood, key_events, tomorrow_focus)
- calendar_events: Calendar (summary, start_time, end_time, location, attendees)
- emails: Email records (subject, sender, recipient, date, snippet)
- transcripts: Voice transcripts (full_text, source_file, created_at)
- books: Reading list (title, author, status, rating, current_page, total_pages, summary, notes)
- highlights: Book highlights (book_title, content, note, chapter, page_number, is_favorite)

IMPORTANT: Only SELECT queries allowed. Use ILIKE for case-insensitive text search.""",
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
        "description": "Get recent emails, optionally filtered by sender or subject.",
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
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": []
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

IMPORTANT: Always confirm the details with the user before creating.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Event title/summary"
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time in ISO 8601 format (e.g., '2025-01-20T14:00:00')"
                },
                "end_time": {
                    "type": "string",
                    "description": "End time in ISO 8601 format (e.g., '2025-01-20T15:00:00')"
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
    # EMAIL SENDING - Compose and send emails via Gmail
    # =========================================================================
    {
        "name": "draft_email",
        "description": """Prepare an email draft for user confirmation before sending.
ALWAYS use this before send_email to get user approval.

Use when user asks to:
- Send an email to someone
- Write an email
- Reply to an email
- Email [person]

This tool prepares the email and shows it to the user for confirmation.
The user must explicitly confirm before calling send_email.""",
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
                "context": {
                    "type": "string",
                    "description": "Context about why user wants to send this email (helps craft better content)"
                }
            },
            "required": ["subject", "body"]
        }
    },
    {
        "name": "send_email",
        "description": """Send an email that was previously drafted and confirmed by the user.
ONLY use this AFTER:
1. draft_email was called
2. User explicitly confirmed they want to send it

NEVER call this directly without user confirmation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
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
                    "description": "CC recipients (comma-separated)"
                },
                "reply_to_message_id": {
                    "type": "string",
                    "description": "Gmail message ID if replying to an email thread"
                }
            },
            "required": ["to", "subject", "body"]
        }
    }
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool and return the result."""
    try:
        if tool_name == "query_database":
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
        # Email sending
        elif tool_name == "draft_email":
            return _draft_email(tool_input)
        elif tool_name == "send_email":
            return _send_email(tool_input)
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.error(f"Tool execution error [{tool_name}]: {e}")
        return {"error": str(e)}


def _query_database(sql: str) -> Dict[str, Any]:
    """Execute a read-only SQL query."""
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
        result = supabase.rpc("execute_sql", {"query": sql}).execute()
        return {"data": result.data, "count": len(result.data) if result.data else 0}
    except Exception as e:
        # Fallback: Try direct table query if RPC doesn't exist
        # This is a simplified approach - the RPC would be more flexible
        logger.warning(f"RPC execute_sql failed, trying direct query: {e}")
        return {"error": f"Query execution failed: {str(e)[:200]}"}


def _search_contacts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search contacts by name, company, etc."""
    try:
        result = supabase.table("contacts").select(
            "id, first_name, last_name, email, company, position, phone, notes"
        ).or_(
            f"first_name.ilike.%{query}%,last_name.ilike.%{query}%,company.ilike.%{query}%,email.ilike.%{query}%"
        ).is_("deleted_at", "null").limit(limit).execute()
        
        contacts = []
        for c in result.data or []:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            contacts.append({
                "id": c.get("id"),
                "name": name,
                "email": c.get("email"),
                "company": c.get("company"),
                "position": c.get("position"),
                "phone": c.get("phone"),
                "notes": c.get("notes", "")[:200] if c.get("notes") else None
            })
        
        return {"contacts": contacts, "count": len(contacts)}
    except Exception as e:
        return {"error": str(e)}


def _get_contact_history(contact_name: str) -> Dict[str, Any]:
    """Get full interaction history with a contact."""
    try:
        # Find contact
        result = supabase.table("contacts").select("id, first_name, last_name, email, company").or_(
            f"first_name.ilike.%{contact_name}%,last_name.ilike.%{contact_name}%"
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
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Note: emails table has: subject, sender, recipient, date, snippet, body_text
        # No 'direction' column exists
        query = supabase.table("emails").select(
            "id, subject, sender, recipient, date, snippet"
        ).gte("date", cutoff)
        
        if input.get("from_email"):
            query = query.ilike("sender", f"%{input['from_email']}%")
        
        if input.get("subject_contains"):
            query = query.ilike("subject", f"%{input['subject_contains']}%")
        
        result = query.order("date", desc=True).limit(input.get("limit", 10)).execute()
        
        # Format emails for readability
        emails = []
        for e in result.data or []:
            email_info = {
                "subject": e.get("subject", "(no subject)"),
                "from": e.get("sender", "Unknown"),
                "to": e.get("recipient", "Unknown"),
                "date": e.get("date"),
                "preview": e.get("snippet", "")[:150] + "..." if e.get("snippet") and len(e.get("snippet", "")) > 150 else e.get("snippet")
            }
            emails.append(email_info)
        
        return {"emails": emails, "count": len(emails)}
    except Exception as e:
        logger.error(f"Error getting emails: {e}")
        return {"error": str(e), "emails": []}


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
        ).eq("source_transcript_id", transcript_id).execute()
        
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
        ).eq("source_transcript_id", transcript_id).execute()
        
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


def _draft_email(params: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare an email draft for user confirmation."""
    to = params.get("to")
    to_name = params.get("to_name")
    subject = params.get("subject", "")
    body = params.get("body", "")
    
    # If no email but name provided, try to look it up
    if not to and to_name:
        try:
            # Search contacts for email
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
                    # Multiple matches - return them for user to choose
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
    
    # Return the draft for user confirmation
    return {
        "draft_ready": True,
        "message": "📧 **Email Draft Ready for Review**",
        "email": {
            "to": to,
            "to_name": to_name,
            "subject": subject,
            "body": body
        },
        "instruction": "Please review and confirm to send, or ask for changes."
    }


def _send_email(params: Dict[str, Any]) -> Dict[str, Any]:
    """Send an email via the sync service Gmail API."""
    import httpx
    import os
    
    to = params.get("to")
    subject = params.get("subject")
    body = params.get("body")
    cc = params.get("cc")
    reply_to_message_id = params.get("reply_to_message_id")
    
    if not to or not subject or not body:
        return {"error": "Missing required fields: to, subject, body"}
    
    sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{sync_service_url}/gmail/send",
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
                    "message": f"✅ Email sent successfully to {to}!",
                    "details": {
                        "to": to,
                        "subject": subject,
                        "message_id": result.get("message_id"),
                        "thread_id": result.get("thread_id")
                    }
                }
            else:
                error_detail = response.text[:200]
                logger.error(f"Gmail send error: {response.status_code} - {error_detail}")
                return {"error": f"Failed to send email: {error_detail}"}
                
    except httpx.TimeoutException:
        logger.error("Timeout calling sync service for email send")
        return {"error": "Email service timeout - please try again"}
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return {"error": str(e)}