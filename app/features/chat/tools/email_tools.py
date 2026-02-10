"""
Email Tools for Chat.

This module contains tools for email operations including reading emails,
creating drafts, sending emails, and managing drafts.
"""

import os
import httpx
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase
from .base import logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

EMAIL_TOOLS = [
    {
        "name": "get_recent_emails",
        "description": "Get recent emails from the inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back",
                    "default": 7
                },
                "limit": {
                    "type": "integer",
                    "description": "Max emails to return",
                    "default": 20
                },
                "unread_only": {
                    "type": "boolean",
                    "description": "Only return unread emails",
                    "default": False
                }
            },
            "required": []
        }
    },
    {
        "name": "get_email_by_id",
        "description": "Get full email content by ID or thread ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "The email UUID or Google message ID"
                },
                "thread_id": {
                    "type": "string",
                    "description": "Get all emails in a thread by thread ID"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_emails_live",
        "description": """Search emails in real-time from Gmail (FALLBACK - use query_knowledge first!).
Use this when query_knowledge doesn't find the email you're looking for.
This searches Gmail directly with filters like sender, date range, labels.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (Gmail search syntax supported)"
                },
                "from_email": {
                    "type": "string",
                    "description": "Filter by sender email"
                },
                "days_back": {
                    "type": "integer",
                    "description": "Search emails from last N days",
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
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _get_recent_emails(input: Dict) -> Dict[str, Any]:
    """Get recent emails from the inbox."""
    try:
        days = input.get("days", 7)
        limit = input.get("limit", 20)
        unread_only = input.get("unread_only", False)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        query = supabase.table("emails").select(
            "id, google_message_id, thread_id, subject, sender, recipient, "
            "date, snippet, labels, is_read, contact_id"
        ).gte("date", cutoff).order("date", desc=True).limit(limit)

        if unread_only:
            query = query.eq("is_read", False)

        result = query.execute()

        emails = []
        for e in result.data or []:
            emails.append({
                "id": e.get("google_message_id"),
                "thread_id": e.get("thread_id"),
                "subject": e.get("subject"),
                "from": e.get("sender"),
                "date": e.get("date"),
                "snippet": e.get("snippet"),
                "is_read": e.get("is_read"),
                "labels": e.get("labels")
            })

        return {
            "emails": emails,
            "count": len(emails),
            "period": f"Last {days} days"
        }
    except Exception as e:
        logger.error(f"Error getting recent emails: {e}")
        return {"error": str(e)}


def _get_email_by_id(input: Dict) -> Dict[str, Any]:
    """Get full email content by ID or thread ID."""
    try:
        email_id = input.get("email_id")
        thread_id = input.get("thread_id")

        if not email_id and not thread_id:
            return {"error": "Either email_id or thread_id is required"}

        if email_id:
            result = supabase.table("emails").select("*").or_(
                f"id.eq.{email_id},google_message_id.eq.{email_id}"
            ).execute()
        else:
            result = supabase.table("emails").select("*").eq(
                "thread_id", thread_id
            ).order("date").execute()

        if not result.data:
            return {"error": "Email not found"}

        if email_id:
            email = result.data[0]
            return {
                "email": {
                    "id": email.get("google_message_id"),
                    "thread_id": email.get("thread_id"),
                    "subject": email.get("subject"),
                    "from": email.get("sender"),
                    "to": email.get("recipient"),
                    "date": email.get("date"),
                    "body": email.get("body_text") or email.get("body_html"),
                    "labels": email.get("labels"),
                    "is_read": email.get("is_read")
                }
            }
        else:
            thread = []
            for e in result.data:
                thread.append({
                    "id": e.get("google_message_id"),
                    "from": e.get("sender"),
                    "date": e.get("date"),
                    "body": e.get("body_text") or e.get("body_html")
                })
            return {
                "thread_id": thread_id,
                "subject": result.data[0].get("subject") if result.data else None,
                "messages": thread,
                "count": len(thread)
            }
    except Exception as e:
        logger.error(f"Error getting email: {e}")
        return {"error": str(e)}


def _search_emails_live(input: Dict) -> Dict[str, Any]:
    """Search emails in real-time from Gmail."""
    try:
        query = input.get("query", "")
        from_email = input.get("from_email")
        days_back = input.get("days_back", 30)
        limit = input.get("limit", 10)

        if not query:
            return {"error": "Search query is required"}

        sync_service_url = os.getenv("SYNC_SERVICE_URL", "https://jarvis-sync-service-qkz4et4n4q-as.a.run.app")

        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{sync_service_url}/gmail/search",
                params={
                    "query": query,
                    "from_email": from_email,
                    "days_back": days_back,
                    "limit": limit
                }
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "emails": result.get("emails", []),
                    "count": len(result.get("emails", [])),
                    "query": query
                }
            else:
                return {"error": f"Gmail search failed: {response.text[:200]}"}

    except httpx.TimeoutException:
        return {"error": "Gmail search timeout - please try again"}
    except Exception as e:
        logger.error(f"Error searching emails: {e}")
        return {"error": str(e)}


def _create_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create an email draft in Gmail."""
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
                    "message": "Draft created and saved to Gmail!",
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
                    "message": "Draft details retrieved"
                }
            else:
                return {"error": f"Failed to get draft: {response.text[:200]}"}

    except Exception as e:
        logger.error(f"Error getting draft: {e}")
        return {"error": str(e)}


def _send_email_draft(params: Dict[str, Any]) -> Dict[str, Any]:
    """Send an existing draft from Gmail."""
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
                    "message": "Email sent successfully!",
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
                    "message": "Draft deleted successfully"
                }
            else:
                return {"error": f"Failed to delete draft: {response.text[:200]}"}

    except Exception as e:
        logger.error(f"Error deleting draft: {e}")
        return {"error": str(e)}
