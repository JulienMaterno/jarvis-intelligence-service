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
        elif tool_name == "get_user_location":
            return _get_user_location()
        elif tool_name == "get_current_time":
            return _get_current_time()
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
        
        query = supabase.table("emails").select(
            "subject, sender, recipient, date, snippet, direction"
        ).gte("date", cutoff)
        
        if input.get("from_email"):
            query = query.ilike("sender", f"%{input['from_email']}%")
        
        if input.get("subject_contains"):
            query = query.ilike("subject", f"%{input['subject_contains']}%")
        
        result = query.order("date", desc=True).limit(input.get("limit", 10)).execute()
        
        return {"emails": result.data or [], "count": len(result.data or [])}
    except Exception as e:
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

def _get_user_location() -> Dict[str, Any]:
    """Get user's stored location and timezone."""
    try:
        # Get location from sync_state (key-value store)
        result = supabase.table("sync_state").select("key, value, updated_at").in_(
            "key", ["user_location", "user_timezone", "user_city", "user_country"]
        ).execute()
        
        location_data = {}
        for row in (result.data or []):
            location_data[row["key"]] = row["value"]
            if row["key"] == "user_location":
                location_data["location_updated_at"] = row["updated_at"]
        
        if not location_data:
            return {
                "error": "Location not set. User needs to share location via Telegram or iOS Shortcut.",
                "timezone": "UTC",
                "city": "Unknown",
                "how_to_set": "Send a location message in Telegram, or set up an iOS Shortcut automation"
            }
        
        return {
            "latitude": location_data.get("user_location", "").split(",")[0] if "," in location_data.get("user_location", "") else None,
            "longitude": location_data.get("user_location", "").split(",")[1] if "," in location_data.get("user_location", "") else None,
            "timezone": location_data.get("user_timezone", "UTC"),
            "city": location_data.get("user_city", "Unknown"),
            "country": location_data.get("user_country", "Unknown"),
            "updated_at": location_data.get("location_updated_at")
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
