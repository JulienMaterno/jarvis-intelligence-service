"""
Miscellaneous Tools for Chat.

This module contains tools that don't fit neatly into other categories:
- Location and timezone tools
- Books and highlights tools
- Transcript tools
- Activity summary tools
- Voice memo context tools
- Application tools
- LinkedIn posts tools
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase
from .base import logger, _sanitize_ilike


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

MISC_TOOLS = [
    # Location & Timezone Tools
    {
        "name": "set_user_location",
        "description": """Set the user's current location and timezone.
Use when user tells you where they are or is traveling.""",
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
    # Books & Highlights Tools
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
    # Transcript Tools
    {
        "name": "search_transcripts",
        "description": "Search through voice memo transcripts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "days": {
                    "type": "integer",
                    "description": "Search within last N days",
                    "default": 30
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_full_transcript",
        "description": "Get the full text of a transcript by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transcript_id": {
                    "type": "string",
                    "description": "Transcript UUID"
                }
            },
            "required": ["transcript_id"]
        }
    },
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
    # Activity Summary
    {
        "name": "summarize_activity",
        "description": "Get a summary of activities for a time period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["today", "yesterday", "this_week", "last_week"],
                    "description": "Time period to summarize",
                    "default": "today"
                }
            },
            "required": []
        }
    },
    # Applications Tools
    {
        "name": "get_applications",
        "description": """Get a list of applications (grants, fellowships, programs).
Filter by status or type.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["Not Started", "Researching", "In Progress", "Applied", "Accepted", "Rejected"],
                    "description": "Filter by status"
                },
                "application_type": {
                    "type": "string",
                    "enum": ["Grant", "Fellowship", "Program", "Accelerator", "Residency"],
                    "description": "Filter by type"
                },
                "limit": {
                    "type": "integer",
                    "default": 200
                }
            },
            "required": []
        }
    },
    {
        "name": "search_applications",
        "description": "Search applications by name, institution, or content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_application_content",
        "description": "Get full content of a specific application.",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "Application UUID"
                },
                "application_name": {
                    "type": "string",
                    "description": "Or application name to search"
                }
            },
            "required": []
        }
    },
    {
        "name": "update_application",
        "description": """Update an application's fields. REQUIRES user_confirmed=true for actual update.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {"type": "string"},
                "application_name": {"type": "string"},
                "status": {"type": "string"},
                "content": {"type": "string"},
                "notes": {"type": "string"},
                "context": {"type": "string"},
                "deadline": {"type": "string"},
                "user_confirmed": {"type": "boolean"}
            },
            "required": []
        }
    },
    # LinkedIn Posts Tools
    {
        "name": "get_linkedin_posts",
        "description": "Get LinkedIn posts with optional filters.",
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
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "search_linkedin_posts",
        "description": "Search LinkedIn posts by title or content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_linkedin_post_content",
        "description": "Get full content of a specific LinkedIn post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "Post UUID"
                },
                "post_title": {
                    "type": "string",
                    "description": "Or post title to search"
                }
            },
            "required": []
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS - Location & Timezone
# =============================================================================

def _set_user_location(input: Dict) -> Dict[str, Any]:
    """Set the user's current location and timezone."""
    try:
        city = input.get("city", "").strip()
        country = input.get("country", "").strip()
        tz = input.get("timezone", "").strip()

        if not city:
            return {"error": "city is required"}

        # Infer timezone from city if not provided
        if not tz:
            city_tz_map = {
                "singapore": "Asia/Singapore",
                "jakarta": "Asia/Jakarta",
                "istanbul": "Europe/Istanbul",
                "new york": "America/New_York",
                "san francisco": "America/Los_Angeles",
                "los angeles": "America/Los_Angeles",
                "london": "Europe/London",
                "paris": "Europe/Paris",
                "tokyo": "Asia/Tokyo",
                "dubai": "Asia/Dubai",
                "sydney": "Australia/Sydney",
            }
            tz = city_tz_map.get(city.lower(), "UTC")

        # Store in sync_state or user settings
        location_data = {
            "key": "user_location",
            "value": {
                "city": city,
                "country": country or None,
                "timezone": tz,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }

        # Try to update existing, insert if not exists
        existing = supabase.table("sync_state").select("id").eq("key", "user_location").execute()

        if existing.data:
            supabase.table("sync_state").update({
                "value": location_data["value"]
            }).eq("key", "user_location").execute()
        else:
            supabase.table("sync_state").insert(location_data).execute()

        # Get current time in new timezone
        try:
            from zoneinfo import ZoneInfo
            local_time = datetime.now(ZoneInfo(tz))
            time_str = local_time.strftime("%I:%M %p on %A, %B %d")
        except Exception:
            time_str = "unknown"

        logger.info(f"User location set to: {city}, {country} ({tz})")

        return {
            "success": True,
            "location": {
                "city": city,
                "country": country,
                "timezone": tz
            },
            "local_time": time_str,
            "message": f"Location set to {city}" + (f", {country}" if country else "") + f" ({tz})"
        }
    except Exception as e:
        logger.error(f"Error setting location: {e}")
        return {"error": str(e)}


def _get_user_location() -> Dict[str, Any]:
    """Get the user's current location and timezone."""
    try:
        result = supabase.table("sync_state").select("value").eq("key", "user_location").execute()

        if result.data:
            location = result.data[0].get("value", {})

            # Get current time in user's timezone
            tz = location.get("timezone", "UTC")
            try:
                from zoneinfo import ZoneInfo
                local_time = datetime.now(ZoneInfo(tz))
                time_str = local_time.strftime("%I:%M %p on %A, %B %d, %Y")
                time_24h = local_time.strftime("%H:%M")
            except Exception:
                time_str = "unknown"
                time_24h = "unknown"

            return {
                "city": location.get("city"),
                "country": location.get("country"),
                "timezone": tz,
                "local_time": time_str,
                "local_time_24h": time_24h,
                "last_updated": location.get("updated_at")
            }
        else:
            sg_tz = timezone(timedelta(hours=8))
            return {
                "city": "Singapore",
                "country": "Singapore",
                "timezone": "Asia/Singapore",
                "local_time": datetime.now(sg_tz).strftime("%I:%M %p on %A, %B %d, %Y") + " (default)",
                "message": "No location set - using default Singapore timezone"
            }
    except Exception as e:
        logger.error(f"Error getting location: {e}")
        return {"error": str(e)}


def _get_current_time() -> Dict[str, Any]:
    """Get the current date and time in the user's timezone."""
    try:
        # Get user's timezone
        location = _get_user_location()
        tz_str = location.get("timezone", "Asia/Singapore")

        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_str)
            local_now = datetime.now(tz)
        except Exception:
            local_now = datetime.now(timezone.utc)
            tz_str = "UTC"

        return {
            "timezone": tz_str,
            "date": local_now.strftime("%Y-%m-%d"),
            "time": local_now.strftime("%H:%M:%S"),
            "time_12h": local_now.strftime("%I:%M %p"),
            "day_of_week": local_now.strftime("%A"),
            "iso": local_now.isoformat(),
            "formatted": local_now.strftime("%A, %B %d, %Y at %I:%M %p")
        }
    except Exception as e:
        logger.error(f"Error getting current time: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS - Books & Highlights
# =============================================================================

def _get_books(input: Dict) -> Dict[str, Any]:
    """Get books from the reading list."""
    try:
        status = input.get("status", "all")
        author = input.get("author")
        search = input.get("search")
        limit = input.get("limit", 10)

        query = supabase.table("books").select(
            "id, title, author, status, rating, current_page, total_pages, summary, notes"
        )

        if status != "all":
            query = query.eq("status", status)

        if author:
            query = query.ilike("author", f"%{author}%")

        if search:
            search = _sanitize_ilike(search)
            query = query.or_(
                f"title.ilike.%{search}%,author.ilike.%{search}%,notes.ilike.%{search}%"
            )

        result = query.order("created_at", desc=True).limit(limit).execute()

        books = []
        for b in result.data or []:
            books.append({
                "id": b.get("id"),
                "title": b.get("title"),
                "author": b.get("author"),
                "status": b.get("status"),
                "rating": b.get("rating"),
                "progress": f"{b.get('current_page', 0)}/{b.get('total_pages', '?')}",
                "summary": b.get("summary", "")[:200] if b.get("summary") else None,
                "notes": b.get("notes", "")[:200] if b.get("notes") else None
            })

        return {"books": books, "count": len(books)}
    except Exception as e:
        logger.error(f"Error getting books: {e}")
        return {"error": str(e)}


def _get_highlights(input: Dict) -> Dict[str, Any]:
    """Get book highlights and annotations."""
    try:
        book_title = input.get("book_title")
        search = input.get("search")
        favorites_only = input.get("favorites_only", False)
        days = input.get("days", 90)
        limit = input.get("limit", 20)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        query = supabase.table("highlights").select(
            "id, book_id, book_title, content, note, chapter, page_number, is_favorite, created_at"
        ).gte("created_at", cutoff)

        if book_title:
            query = query.ilike("book_title", f"%{book_title}%")

        if search:
            search = _sanitize_ilike(search)
            query = query.or_(
                f"content.ilike.%{search}%,note.ilike.%{search}%"
            )

        if favorites_only:
            query = query.eq("is_favorite", True)

        result = query.order("created_at", desc=True).limit(limit).execute()

        highlights = []
        for h in result.data or []:
            highlights.append({
                "id": h.get("id"),
                "book": h.get("book_title"),
                "content": h.get("content"),
                "note": h.get("note"),
                "chapter": h.get("chapter"),
                "page": h.get("page_number"),
                "favorite": h.get("is_favorite"),
                "date": h.get("created_at")
            })

        return {"highlights": highlights, "count": len(highlights)}
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return {"error": str(e)}


def _search_reading_notes(input: Dict) -> Dict[str, Any]:
    """Search across all books and highlights."""
    try:
        query_str = input.get("query", "")
        limit = input.get("limit", 15)

        if not query_str:
            return {"error": "query is required"}

        query_str = _sanitize_ilike(query_str)

        results = []

        # Search books
        books = supabase.table("books").select(
            "id, title, author, notes, summary"
        ).or_(
            f"title.ilike.%{query_str}%,author.ilike.%{query_str}%,notes.ilike.%{query_str}%,summary.ilike.%{query_str}%"
        ).limit(limit // 2).execute()

        for b in books.data or []:
            results.append({
                "type": "book",
                "title": b.get("title"),
                "author": b.get("author"),
                "content": b.get("notes") or b.get("summary") or ""
            })

        # Search highlights
        highlights = supabase.table("highlights").select(
            "id, book_title, content, note"
        ).or_(
            f"content.ilike.%{query_str}%,note.ilike.%{query_str}%"
        ).limit(limit // 2).execute()

        for h in highlights.data or []:
            results.append({
                "type": "highlight",
                "book": h.get("book_title"),
                "content": h.get("content"),
                "note": h.get("note")
            })

        return {"results": results, "count": len(results), "query": query_str}
    except Exception as e:
        logger.error(f"Error searching reading notes: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS - Transcripts
# =============================================================================

def _search_transcripts(input: Dict) -> Dict[str, Any]:
    """Search through voice memo transcripts."""
    try:
        query = input.get("query", "")
        days = input.get("days", 30)
        limit = input.get("limit", 10)

        if not query:
            return {"error": "Search query is required"}

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        result = supabase.table("transcripts").select(
            "id, full_text, source_file, audio_duration_seconds, created_at"
        ).ilike("full_text", f"%{query}%"
        ).gte("created_at", cutoff).order("created_at", desc=True).limit(limit).execute()

        transcripts = []
        for t in result.data or []:
            text = t.get("full_text", "")
            # Find context around the match
            idx = text.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(text), idx + len(query) + 100)
                snippet = "..." + text[start:end] + "..."
            else:
                snippet = text[:200] + "..."

            transcripts.append({
                "id": t.get("id"),
                "snippet": snippet,
                "duration": t.get("audio_duration_seconds"),
                "source": t.get("source_file"),
                "date": t.get("created_at")
            })

        return {"transcripts": transcripts, "count": len(transcripts)}
    except Exception as e:
        logger.error(f"Error searching transcripts: {e}")
        return {"error": str(e)}


def _get_full_transcript(input: Dict) -> Dict[str, Any]:
    """Get the full text of a transcript."""
    try:
        transcript_id = input.get("transcript_id")
        if not transcript_id:
            return {"error": "transcript_id is required"}

        result = supabase.table("transcripts").select("*").eq("id", transcript_id).execute()

        if not result.data:
            return {"error": "Transcript not found"}

        t = result.data[0]
        return {
            "transcript": {
                "id": t.get("id"),
                "full_text": t.get("full_text"),
                "duration_seconds": t.get("audio_duration_seconds"),
                "source_file": t.get("source_file"),
                "language": t.get("language"),
                "speakers": t.get("speakers"),
                "model_used": t.get("model_used"),
                "created_at": t.get("created_at")
            }
        }
    except Exception as e:
        logger.error(f"Error getting transcript: {e}")
        return {"error": str(e)}


def _get_recent_voice_memo(input: Dict) -> Dict[str, Any]:
    """Get the most recently processed voice memo."""
    try:
        include_transcript = input.get("include_transcript", True)

        # Get most recent transcript
        result = supabase.table("transcripts").select(
            "id, full_text, source_file, audio_duration_seconds, created_at"
        ).order("created_at", desc=True).limit(1).execute()

        if not result.data:
            return {"message": "No recent voice memos found"}

        transcript = result.data[0]
        transcript_id = transcript["id"]

        # Get related meetings
        meetings = supabase.table("meetings").select(
            "id, title, date, summary"
        ).eq("source_transcript_id", transcript_id).execute()

        # Get related reflections
        reflections = supabase.table("reflections").select(
            "id, title, topic_key"
        ).eq("source_transcript_id", transcript_id).execute()

        # Get related tasks
        meeting_ids = [m["id"] for m in (meetings.data or [])]
        if meeting_ids:
            related_tasks = supabase.table("tasks").select(
                "id, title, status"
            ).eq("origin_type", "meeting").in_("origin_id", meeting_ids).execute().data or []
        else:
            related_tasks = []

        response = {
            "transcript_id": transcript_id,
            "processed_at": transcript.get("created_at"),
            "duration_seconds": transcript.get("audio_duration_seconds"),
            "source_file": transcript.get("source_file"),
            "created_items": {
                "meetings": meetings.data or [],
                "reflections": reflections.data or [],
                "tasks": related_tasks
            }
        }

        if include_transcript:
            response["transcript_text"] = transcript.get("full_text", "")

        return response
    except Exception as e:
        logger.error(f"Error getting recent voice memo: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS - Activity Summary
# =============================================================================

def _summarize_activity(period: str = "today") -> Dict[str, Any]:
    """Get a summary of activities for a time period."""
    try:
        now = datetime.now(timezone.utc)

        if period == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif period == "this_week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif period == "last_week":
            start = now - timedelta(days=now.weekday() + 7)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7)
        else:
            return {"error": f"Invalid period: {period}"}

        # Get meetings
        meetings = supabase.table("meetings").select("title, date").gte(
            "date", start.isoformat()
        ).lte("date", end.isoformat()).is_("deleted_at", "null").execute()

        # Get tasks completed
        tasks_completed = supabase.table("tasks").select("title").eq(
            "status", "done"
        ).gte("completed_at", start.isoformat()).lte("completed_at", end.isoformat()).execute()

        # Get tasks created
        tasks_created = supabase.table("tasks").select("title").gte(
            "created_at", start.isoformat()
        ).lte("created_at", end.isoformat()).execute()

        # Get emails received
        emails = supabase.table("emails").select("subject").gte(
            "date", start.isoformat()
        ).lte("date", end.isoformat()).execute()

        return {
            "period": period,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "summary": {
                "meetings": len(meetings.data or []),
                "meeting_titles": [m["title"] for m in (meetings.data or [])[:5]],
                "tasks_completed": len(tasks_completed.data or []),
                "tasks_created": len(tasks_created.data or []),
                "emails_received": len(emails.data or [])
            }
        }
    except Exception as e:
        logger.error(f"Error summarizing activity: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS - Applications
# =============================================================================

def _get_applications(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get a list of applications with optional filters."""
    try:
        query = supabase.table("applications").select(
            "id, name, application_type, status, institution, website, grant_amount, deadline, context, notes, created_at"
        )

        if tool_input.get("status"):
            query = query.eq("status", tool_input["status"])

        if tool_input.get("application_type"):
            query = query.eq("application_type", tool_input["application_type"])

        limit = min(tool_input.get("limit", 200), 500)
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
        limit = min(tool_input.get("limit", 50), 200)

        if not query_str:
            return {"error": "query is required"}

        query_str = _sanitize_ilike(query_str)

        result = supabase.table("applications").select(
            "id, name, application_type, status, institution, website, grant_amount, deadline, context, notes, content"
        ).or_(
            f"name.ilike.%{query_str}%,institution.ilike.%{query_str}%,context.ilike.%{query_str}%,notes.ilike.%{query_str}%,content.ilike.%{query_str}%"
        ).order("deadline", desc=False, nullsfirst=False).limit(limit).execute()

        applications = []
        for app in result.data or []:
            content = app.get("content", "") or ""
            snippet = None
            if query_str.lower() in content.lower():
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
                "content": app.get("content"),
                "created_at": app.get("created_at")
            }
        }
    except Exception as e:
        logger.error(f"Failed to get application content: {e}")
        return {"error": str(e)}


def _update_application(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Update an application's fields with verification."""
    try:
        app_id = tool_input.get("application_id")
        app_name = tool_input.get("application_name")
        user_confirmed = tool_input.get("user_confirmed", False)

        if not app_id and not app_name:
            return {"error": "Either application_id or application_name is required"}

        if app_id:
            result = supabase.table("applications").select("id, name, status").eq("id", app_id).execute()
        else:
            result = supabase.table("applications").select("id, name, status").ilike("name", f"%{app_name}%").limit(1).execute()

        if not result.data:
            return {"error": f"Application not found: {app_name or app_id}"}

        app = result.data[0]
        app_id = app["id"]

        # Build update fields
        updatable_fields = ["status", "content", "notes", "context", "deadline", "grant_amount", "website", "application_type", "institution"]
        fields_to_update = {}

        for field in updatable_fields:
            if field in tool_input and tool_input[field] is not None:
                fields_to_update[field] = tool_input[field]

        if not fields_to_update:
            return {"error": "No fields to update. Provide at least one of: status, content, notes, context, deadline, grant_amount, website, application_type, institution"}

        if not user_confirmed:
            preview = {
                "application": app["name"],
                "current_status": app["status"],
                "fields_to_update": list(fields_to_update.keys()),
            }
            if "content" in fields_to_update:
                content = fields_to_update["content"]
                preview["content_preview"] = content[:300] + "..." if len(content) > 300 else content
                preview["content_length"] = len(content)

            return {
                "status": "confirmation_required",
                "preview": preview,
                "message": f"Ready to update '{app['name']}'. Please confirm.",
                "instructions": "Ask the user to confirm, then call update_application again with user_confirmed=true"
            }

        # Add metadata
        fields_to_update["updated_at"] = datetime.now(timezone.utc).isoformat()
        fields_to_update["last_sync_source"] = "supabase"

        logger.info(f"Updating application {app_id} with fields: {list(fields_to_update.keys())}")
        supabase.table("applications").update(fields_to_update).eq("id", app_id).execute()

        # Verify update
        verify = supabase.table("applications").select("id, name, status, content").eq("id", app_id).execute()
        if not verify.data:
            return {"error": "Verification failed - could not read updated record"}

        updated_app = verify.data[0]

        return {
            "status": "success",
            "application_id": app_id,
            "application_name": updated_app["name"],
            "fields_updated": list(fields_to_update.keys()),
            "new_status": updated_app.get("status"),
            "content_saved": bool(updated_app.get("content")),
            "content_length": len(updated_app.get("content") or ""),
            "message": f"Successfully updated '{updated_app['name']}'"
        }

    except Exception as e:
        logger.error(f"Failed to update application: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS - LinkedIn Posts
# =============================================================================

def _get_linkedin_posts(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Get a list of LinkedIn posts with optional filters."""
    try:
        query = supabase.table("linkedin_posts").select(
            "id, title, post_date, status, pillar, likes, created_at"
        )

        if tool_input.get("status"):
            query = query.eq("status", tool_input["status"])

        if tool_input.get("pillar"):
            query = query.eq("pillar", tool_input["pillar"])

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

        query_str = _sanitize_ilike(query_str)

        result = supabase.table("linkedin_posts").select(
            "id, title, post_date, status, pillar, likes, content"
        ).or_(
            f"title.ilike.%{query_str}%,content.ilike.%{query_str}%"
        ).order("post_date", desc=True).limit(limit).execute()

        posts = []
        for post in result.data or []:
            content = post.get("content", "") or ""
            snippet = None
            if content:
                if query_str.lower() in content.lower():
                    idx = content.lower().find(query_str.lower())
                    start = max(0, idx - 100)
                    end = min(len(content), idx + len(query_str) + 100)
                    snippet = "..." + content[start:end] + "..."
                else:
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
                "content": post.get("content"),
                "created_at": post.get("created_at")
            }
        }
    except Exception as e:
        logger.error(f"Failed to get LinkedIn post content: {e}")
        return {"error": str(e)}
