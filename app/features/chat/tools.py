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
        payload = {
            "title": input.get("title"),
            "description": input.get("description", ""),
            "status": "pending",
            "priority": input.get("priority", "medium"),
            "origin_type": "chat"
        }
        
        if input.get("due_date"):
            payload["due_date"] = input["due_date"]
        
        result = supabase.table("tasks").insert(payload).execute()
        task_id = result.data[0]["id"]
        
        logger.info(f"Created task via chat: {input.get('title')}")
        return {"success": True, "task_id": task_id, "message": f"Task '{input.get('title')}' created"}
    except Exception as e:
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
