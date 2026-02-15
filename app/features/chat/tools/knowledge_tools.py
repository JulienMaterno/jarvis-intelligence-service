"""
Knowledge Tools for Chat.

This module contains tools for knowledge base operations including semantic
search, document retrieval, and RAG (Retrieval Augmented Generation) queries.
"""

import logging
from typing import Dict, List, Any, Optional

from app.core.database import supabase
from .base import _run_async, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

KNOWLEDGE_TOOLS = [
    {
        "name": "query_knowledge",
        "description": """PREFERRED SEARCH TOOL - Search the knowledge base using semantic (AI-powered) search.

This tool searches across ALL of Aaron's data using vector embeddings:
- Emails (1000+ indexed - use this for email searches!)
- LinkedIn posts (content)
- Beeper messages (WhatsApp, LinkedIn, etc.)
- Transcripts (meeting notes, voice memos)
- Applications (grants, fellowships)
- Meetings, Journals, Reflections
- And more...

USE THIS FIRST WHEN:
- User asks "find that email about X"
- User asks "what do I know about X"
- Looking for information across multiple sources
- Finding past conversations, emails, or notes about a topic
- Semantic/meaning-based search (not just keyword matching)

COMPARED TO other tools:
- query_knowledge = PRIMARY search for any content by meaning
- query_database = SQL for structured queries (exact filters, counts, dates)
- search_emails_live = FALLBACK when query_knowledge doesn't find emails

RETURNS: Top matching content chunks with source type, text, and relevance score.

EXAMPLE QUERIES:
- "Network School signup" -> finds emails from Network School
- "conversations about funding" -> finds emails, messages, meeting notes about funding
- "what did I discuss with John" -> finds all content mentioning John""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query"
                },
                "content_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by type: email, linkedin_post, beeper_message, transcript, application, document, contact, meeting, journal, reflection, calendar, task, book, highlight"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_documents",
        "description": """Search personal documents (CV, profiles, applications, notes).
Use when user asks about their documents, CV, or written content.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "document_type": {
                    "type": "string",
                    "enum": ["cv", "profile", "notes", "application"],
                    "description": "Filter by document type"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_document_content",
        "description": """Get full content of a document by type.
Use to retrieve the full text of a specific document.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_type": {
                    "type": "string",
                    "enum": ["cv", "profile", "notes", "application"],
                    "description": "Type of document to retrieve"
                },
                "title": {
                    "type": "string",
                    "description": "Optional: specific document title to match"
                }
            },
            "required": ["document_type"]
        }
    },
    {
        "name": "search_conversations",
        "description": """Search through past conversation history.
Use when user asks about previous conversations or what they discussed before.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
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
        "name": "get_reflections",
        "description": "Get personal reflections/notes, optionally filtered by topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Filter by topic key (e.g., 'career-development')"
                },
                "search": {
                    "type": "string",
                    "description": "Search in content"
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
            "required": ["title", "content"]
        }
    },
    {
        "name": "get_journals",
        "description": "Get journal entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Specific date (YYYY-MM-DD)"
                },
                "days": {
                    "type": "integer",
                    "description": "Get journals from last N days",
                    "default": 7
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
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

_PLURAL_TO_SINGULAR = {
    "emails": "email",
    "linkedin_posts": "linkedin_post",
    "beeper_messages": "beeper_message",
    "transcripts": "transcript",
    "applications": "application",
    "documents": "document",
    "contacts": "contact",
    "meetings": "meeting",
    "journals": "journal",
    "reflections": "reflection",
    "calendars": "calendar",
    "tasks": "task",
    "books": "book",
    "highlights": "highlight",
}


def _query_knowledge(
    query: str,
    content_types: Optional[List[str]] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """Search the knowledge base using hybrid (semantic + keyword) search."""
    if not query:
        return {"error": "Query is required"}

    try:
        from app.features.knowledge.retriever import hybrid_search

        # Normalize plural type names to singular (DB uses singular)
        if content_types:
            content_types = [
                _PLURAL_TO_SINGULAR.get(t, t) for t in content_types
            ]

        # Create a simple wrapper so the retriever can access supabase as db.client
        class _DB:
            def __init__(self, client):
                self.client = client

        db = _DB(supabase)

        results = _run_async(hybrid_search(
            query=query,
            db=db,
            source_types=content_types,
            limit=limit
        ))

        if not results:
            return {
                "status": "no_results",
                "message": f"No results found for '{query}'",
                "results": []
            }

        # Format results
        formatted = []
        for item in results:
            formatted.append({
                "content_type": item.get("source_type"),
                "content": item.get("content", "")[:500],
                "source_id": item.get("source_id"),
                "metadata": item.get("metadata"),
                "similarity": item.get("similarity")
            })

        return {
            "status": "found",
            "count": len(formatted),
            "results": formatted,
            "query": query
        }
    except Exception as e:
        logger.error(f"Knowledge search error: {e}", exc_info=True)
        # Fallback to basic text search if semantic search fails
        return _fallback_text_search(query, content_types, limit)


def _fallback_text_search(
    query: str,
    content_types: Optional[List[str]] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """Fallback text search when vector search is unavailable."""
    try:
        results = []

        # Search emails
        if not content_types or "emails" in content_types:
            emails = supabase.table("emails").select(
                "id, subject, sender, snippet, date"
            ).or_(
                f"subject.ilike.%{query}%,snippet.ilike.%{query}%,body_text.ilike.%{query}%"
            ).order("date", desc=True).limit(limit).execute()

            for e in (emails.data or []):
                results.append({
                    "content_type": "email",
                    "content": f"Subject: {e.get('subject')}\nFrom: {e.get('sender')}\n{e.get('snippet', '')}",
                    "source_id": e.get("id"),
                    "metadata": {"date": e.get("date")}
                })

        # Search meetings
        if not content_types or "meetings" in content_types:
            meetings = supabase.table("meetings").select(
                "id, title, summary, date, contact_name"
            ).or_(
                f"title.ilike.%{query}%,summary.ilike.%{query}%"
            ).order("date", desc=True).limit(limit).execute()

            for m in (meetings.data or []):
                results.append({
                    "content_type": "meeting",
                    "content": f"Meeting: {m.get('title')}\n{m.get('summary', '')}",
                    "source_id": m.get("id"),
                    "metadata": {"date": m.get("date"), "contact": m.get("contact_name")}
                })

        # Search reflections
        if not content_types or "reflections" in content_types:
            reflections = supabase.table("reflections").select(
                "id, title, content, topic_key"
            ).or_(
                f"title.ilike.%{query}%,content.ilike.%{query}%"
            ).is_("deleted_at", "null").limit(limit).execute()

            for r in (reflections.data or []):
                results.append({
                    "content_type": "reflection",
                    "content": f"Reflection: {r.get('title')}\n{r.get('content', '')[:300]}",
                    "source_id": r.get("id"),
                    "metadata": {"topic": r.get("topic_key")}
                })

        return {
            "status": "found" if results else "no_results",
            "count": len(results),
            "results": results[:limit],
            "query": query,
            "note": "Using text search fallback"
        }
    except Exception as e:
        logger.error(f"Fallback search error: {e}")
        return {"error": f"Search failed: {str(e)}"}


async def _search_documents(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search personal documents."""
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
            doc_id = docs[0]["id"]

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


async def _search_conversations(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Search through past conversation history."""
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


def _get_reflections(input: Dict) -> Dict[str, Any]:
    """Get personal reflections/notes."""
    try:
        topic = input.get("topic")
        search = input.get("search")
        limit = input.get("limit", 10)

        query = supabase.table("reflections").select(
            "id, title, topic_key, content, tags, date, mood"
        ).is_("deleted_at", "null")

        if topic:
            query = query.eq("topic_key", topic)

        if search:
            query = query.or_(
                f"title.ilike.%{search}%,content.ilike.%{search}%"
            )

        result = query.order("date", desc=True).limit(limit).execute()

        reflections = []
        for r in result.data or []:
            reflections.append({
                "id": r.get("id"),
                "title": r.get("title"),
                "topic": r.get("topic_key"),
                "content": r.get("content", "")[:500],
                "tags": r.get("tags"),
                "date": r.get("date"),
                "mood": r.get("mood")
            })

        return {"reflections": reflections, "count": len(reflections)}
    except Exception as e:
        logger.error(f"Error getting reflections: {e}")
        return {"error": str(e)}


def _create_reflection(input: Dict) -> Dict[str, Any]:
    """Create or append to a reflection."""
    try:
        title = input.get("title", "").strip()
        content = input.get("content", "").strip()
        topic_key = input.get("topic_key", "").strip()
        tags = input.get("tags", [])

        if not title or not content:
            return {"error": "title and content are required"}

        # Generate topic_key if not provided
        if not topic_key:
            topic_key = title.lower().replace(" ", "-")[:50]

        # Check if reflection with same topic_key exists
        existing = supabase.table("reflections").select(
            "id, title, content"
        ).eq("topic_key", topic_key).is_("deleted_at", "null").execute()

        from datetime import timezone
        now = datetime.now(timezone.utc)

        if existing.data:
            # Append to existing reflection
            old_content = existing.data[0].get("content", "")
            new_content = f"{old_content}\n\n---\n[{now.strftime('%Y-%m-%d')}]\n{content}"

            supabase.table("reflections").update({
                "content": new_content,
                "updated_at": now.isoformat(),
                "last_sync_source": "supabase"
            }).eq("id", existing.data[0]["id"]).execute()

            logger.info(f"Appended to reflection: {title}")
            return {
                "success": True,
                "action": "appended",
                "reflection_id": existing.data[0]["id"],
                "title": existing.data[0]["title"],
                "message": f"Appended content to existing reflection: {existing.data[0]['title']}"
            }
        else:
            # Create new reflection
            reflection_data = {
                "title": title,
                "content": content,
                "topic_key": topic_key,
                "tags": tags if tags else None,
                "date": now.date().isoformat(),
                "last_sync_source": "supabase"
            }

            reflection_data = {k: v for k, v in reflection_data.items() if v is not None}

            result = supabase.table("reflections").insert(reflection_data).execute()

            if result.data:
                logger.info(f"Created reflection: {title}")
                return {
                    "success": True,
                    "action": "created",
                    "reflection_id": result.data[0]["id"],
                    "title": title,
                    "message": f"Created new reflection: {title}"
                }
            return {"error": "Failed to create reflection"}
    except Exception as e:
        logger.error(f"Error creating reflection: {e}")
        return {"error": str(e)}


def _get_journals(input: Dict) -> Dict[str, Any]:
    """Get journal entries."""
    try:
        date = input.get("date")
        days = input.get("days", 7)
        limit = input.get("limit", 10)

        query = supabase.table("journals").select(
            "id, date, title, content, mood, energy, gratitude, wins, challenges"
        )

        if date:
            query = query.eq("date", date)
        else:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            query = query.gte("date", cutoff)

        result = query.order("date", desc=True).limit(limit).execute()

        journals = []
        for j in result.data or []:
            journals.append({
                "id": j.get("id"),
                "date": j.get("date"),
                "title": j.get("title"),
                "content": j.get("content", "")[:500],
                "mood": j.get("mood"),
                "energy": j.get("energy"),
                "gratitude": j.get("gratitude"),
                "wins": j.get("wins"),
                "challenges": j.get("challenges")
            })

        return {"journals": journals, "count": len(journals)}
    except Exception as e:
        logger.error(f"Error getting journals: {e}")
        return {"error": str(e)}


# Need datetime import at top level
from datetime import datetime, timezone
