"""
Books Tools for Chat.

This module contains tools for creating summary books and managing
the book summary pipeline.

Tools:
- create_summary_book: Generate a curated book list and trigger EPUB creation
- get_summary_book_status: Check progress of a summary book pipeline
- list_summary_book_projects: List all summary book projects
"""

import os
import logging
from typing import Dict, Any

import httpx

from .base import _get_identity_token, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

BOOKS_PIPELINE_TOOLS = [
    {
        "name": "create_summary_book",
        "description": """Create a summary book (compiled EPUB) for any topic.

Use when user says:
- "Create a summary book about [topic]"
- "Make me a book of summaries on [topic]"
- "Compile book summaries for [topic]"
- "I want to read about [topic], make me a summary book"

This triggers an end-to-end pipeline:
1. AI generates a curated list of important books on the topic
2. Downloads EPUBs from LibGen
3. Processes all books with AI (chapter summaries)
4. Compiles into a single summary EPUB
5. Uploads to Bookfusion for e-reader sync

The pipeline runs in the background (30-60 minutes for 30 books).
Use get_summary_book_status to check progress.

IMPORTANT: Before triggering, discuss the topic with the user to understand:
- What specific aspects they care about
- Whether they want academic, practical, or popular books
- Any specific books they want included or excluded
- How many books (default 30)""",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic to create a summary book for (e.g., 'synthetic biology', 'regenerative agriculture')"
                },
                "title": {
                    "type": "string",
                    "description": "Custom title for the book (default: 'Summary: [Topic]')"
                },
                "book_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "author": {"type": "string"},
                            "why": {"type": "string"}
                        },
                        "required": ["title"]
                    },
                    "description": "Optional pre-defined book list. If not provided, AI generates one from the topic."
                },
                "max_books": {
                    "type": "integer",
                    "description": "Maximum number of books to include (default 30)",
                    "default": 30
                },
                "context": {
                    "type": "string",
                    "description": "Additional context to guide book selection (e.g., 'focus on practical applications, not theory')"
                },
                "skip_upload": {
                    "type": "boolean",
                    "description": "If true, skip uploading to Bookfusion",
                    "default": False
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "get_summary_book_status",
        "description": """Check the status of a summary book pipeline job.

Use when user says:
- "How is my summary book going?"
- "Check the status of the book pipeline"
- "Is the [topic] book done yet?"

Returns current step, progress, and result when complete.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "The project ID returned from create_summary_book"
                }
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "list_summary_book_projects",
        "description": """List all summary book projects.

Use when user says:
- "What summary books have I created?"
- "Show my book projects"
- "List summary books"

Returns all projects with their status.""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


# =============================================================================
# HELPERS
# =============================================================================

def _get_sync_service_url() -> str:
    """Get the sync service URL."""
    return os.getenv(
        "SYNC_SERVICE_URL",
        "https://jarvis-sync-service-776871804948.asia-southeast1.run.app"
    )


def _call_sync_service(method: str, path: str, json_data: dict | None = None, timeout: float = 120.0) -> dict:
    """Call the sync service with proper authentication.

    Args:
        method: HTTP method ('get' or 'post')
        path: URL path (e.g., '/books/create-summary-book')
        json_data: Request body for POST requests
        timeout: Request timeout in seconds

    Returns:
        Response JSON or error dict
    """
    sync_url = _get_sync_service_url()
    identity_token = _get_identity_token(sync_url)

    headers = {"Content-Type": "application/json"}
    if identity_token:
        headers["Authorization"] = f"Bearer {identity_token}"

    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "post":
                response = client.post(f"{sync_url}{path}", headers=headers, json=json_data)
            else:
                response = client.get(f"{sync_url}{path}", headers=headers)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return {"error": f"Not found: {response.text[:200]}"}
            else:
                error_detail = response.text[:200]
                logger.error(f"Sync service error: {response.status_code} - {error_detail}")
                return {"error": f"Service error ({response.status_code}): {error_detail}"}

    except httpx.TimeoutException:
        logger.error(f"Timeout calling sync service: {path}")
        return {"error": "Sync service timeout - the pipeline may still be running. Try checking status later."}
    except Exception as e:
        logger.error(f"Error calling sync service: {e}")
        return {"error": str(e)}


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _create_summary_book(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a summary book for a topic.

    Triggers the summary book pipeline on the sync service which runs
    in the background (typically 30-60 minutes for 30 books).
    """
    topic = params.get("topic", "").strip()
    if not topic:
        return {"error": "topic is required"}

    title = params.get("title") or f"Summary: {topic.title()}"
    book_list = params.get("book_list")
    max_books = params.get("max_books", 30)
    context = params.get("context", "")
    skip_upload = params.get("skip_upload", False)

    logger.info(f"Creating summary book: topic='{topic}', title='{title}', max_books={max_books}")

    request_body = {
        "topic": topic,
        "title": title,
        "max_books": max_books,
        "context": context,
        "skip_upload": skip_upload,
    }

    if book_list:
        request_body["book_list"] = book_list

    result = _call_sync_service("post", "/books/create-summary-book", request_body)

    if "error" in result:
        return result

    project_id = result.get("project_id", "unknown")

    return {
        "success": True,
        "project_id": project_id,
        "title": title,
        "topic": topic,
        "max_books": max_books,
        "status": "queued",
        "message": (
            f"Summary book pipeline started for '{topic}' (project: {project_id}). "
            f"This will generate a list of ~{max_books} books, download them, "
            f"create AI summaries, and compile into an EPUB. "
            f"Expected time: 30-60 minutes. "
            f"Use get_summary_book_status with project_id '{project_id}' to check progress."
        )
    }


def _get_summary_book_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Check the status of a summary book pipeline."""
    project_id = params.get("project_id", "").strip()
    if not project_id:
        return {"error": "project_id is required"}

    result = _call_sync_service("get", f"/books/summary-book-status/{project_id}")

    if "error" in result:
        return result

    status = result.get("status", "unknown")
    response = {
        "project_id": project_id,
        "title": result.get("title"),
        "status": status,
        "current_step": result.get("current_step"),
    }

    if status == "completed":
        pipeline_result = result.get("result", {})
        response.update({
            "books_processed": pipeline_result.get("processing", {}).get("processed", 0),
            "books_failed": pipeline_result.get("processing", {}).get("failed", 0),
            "total_time_minutes": pipeline_result.get("total_time_minutes"),
            "bookfusion_id": pipeline_result.get("bookfusion_id"),
            "message": f"Summary book '{result.get('title')}' is ready! "
                       f"{pipeline_result.get('processing', {}).get('processed', 0)} books processed."
        })
    elif status == "failed":
        response["error"] = result.get("error")
        response["message"] = f"Pipeline failed: {result.get('error', 'Unknown error')}"
    elif status == "running":
        response["message"] = f"Pipeline is running (step: {result.get('current_step', 'processing')})"
    else:
        response["message"] = f"Pipeline status: {status}"

    return response


def _list_summary_book_projects(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all summary book projects."""
    result = _call_sync_service("get", "/books/summary-book-projects")

    if "error" in result:
        return result

    projects = result.get("projects", [])

    return {
        "projects": projects,
        "count": len(projects),
        "message": f"Found {len(projects)} summary book project(s)"
    }
