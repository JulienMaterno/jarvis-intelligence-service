"""
Contact Tools for Chat.

This module contains tools for contact/CRM operations including searching,
creating, updating, and managing contacts.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta, timezone

from app.core.database import supabase
from .base import SYNC_MANAGED_TABLES, logger, _sanitize_ilike


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

CONTACT_TOOLS = [
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
        "name": "create_contact",
        "description": "Create a new contact in the CRM. Automatically checks for duplicates by name (first + last) or email before creating. Returns already_exists flag if contact already exists.",
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
                "company": {
                    "type": "string",
                    "description": "Company name"
                },
                "job_title": {
                    "type": "string",
                    "description": "Job title"
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number"
                },
                "linkedin_url": {
                    "type": "string",
                    "description": "LinkedIn profile URL"
                },
                "notes": {
                    "type": "string",
                    "description": "Initial notes about the contact"
                }
            },
            "required": ["first_name"]
        }
    },
    {
        "name": "update_contact",
        "description": "Update an existing contact's information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name to search for the contact"
                },
                "contact_id": {
                    "type": "string",
                    "description": "Or the contact's UUID directly"
                },
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "company": {"type": "string"},
                "job_title": {"type": "string"},
                "phone": {"type": "string"},
                "linkedin_url": {"type": "string"},
                "notes": {"type": "string"},
                "birthday": {"type": "string", "description": "YYYY-MM-DD format"}
            },
            "required": []
        }
    },
    {
        "name": "add_contact_note",
        "description": "Add a note to an existing contact (appends to existing notes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {
                    "type": "string",
                    "description": "Name of the contact"
                },
                "note": {
                    "type": "string",
                    "description": "Note to add"
                }
            },
            "required": ["contact_name", "note"]
        }
    },
    {
        "name": "who_to_contact",
        "description": """Find contacts you haven't interacted with recently.
Use this when user asks 'who should I reach out to?' or wants to reconnect with contacts.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_inactive": {
                    "type": "integer",
                    "description": "Days without interaction to consider 'inactive'",
                    "default": 30
                },
                "limit": {
                    "type": "integer",
                    "description": "Max contacts to return",
                    "default": 5
                }
            },
            "required": []
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _search_contacts(query: str, limit: int = 5) -> Dict[str, Any]:
    """Search for contacts."""
    try:
        safe_query = _sanitize_ilike(query)
        if not safe_query:
            return {"contacts": [], "count": 0}

        result = supabase.table("contacts").select(
            "id, first_name, last_name, email, company, job_title, phone, "
            "linkedin_url, location, notes, birthday"
        ).or_(
            f"first_name.ilike.%{safe_query}%,last_name.ilike.%{safe_query}%,"
            f"email.ilike.%{safe_query}%,company.ilike.%{safe_query}%"
        ).is_("deleted_at", "null").limit(limit).execute()

        contacts = []
        for c in result.data or []:
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            contacts.append({
                "id": c["id"],
                "name": name,
                "email": c.get("email"),
                "company": c.get("company"),
                "job_title": c.get("job_title"),
                "phone": c.get("phone"),
                "linkedin": c.get("linkedin_url"),
                "notes": c.get("notes")
            })

        return {"contacts": contacts, "count": len(contacts)}
    except Exception as e:
        logger.error(f"Error searching contacts: {e}")
        return {"error": str(e)}


def _get_contact_history(contact_name: str) -> Dict[str, Any]:
    """Get full interaction history with a contact."""
    try:
        safe_name = _sanitize_ilike(contact_name)
        if not safe_name:
            return {"error": "Invalid contact name"}

        # First find the contact
        contact_result = supabase.table("contacts").select(
            "id, first_name, last_name, email, company, notes"
        ).or_(
            f"first_name.ilike.%{safe_name}%,last_name.ilike.%{safe_name}%"
        ).is_("deleted_at", "null").limit(1).execute()

        if not contact_result.data:
            return {"error": f"Contact '{contact_name}' not found"}

        contact = contact_result.data[0]
        contact_id = contact["id"]
        full_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()

        # Get meetings
        meetings = supabase.table("meetings").select(
            "title, date, summary"
        ).eq("contact_id", contact_id).order("date", desc=True).limit(10).execute()

        # Get calendar events
        events = supabase.table("calendar_events").select(
            "summary, start_time, location"
        ).eq("contact_id", contact_id).order("start_time", desc=True).limit(10).execute()

        # Get emails
        email = contact.get("email")
        emails = []
        if email:
            safe_email = _sanitize_ilike(email)
            email_result = supabase.table("emails").select(
                "subject, date, snippet"
            ).or_(
                f"sender.ilike.%{safe_email}%,recipient.ilike.%{safe_email}%"
            ).order("date", desc=True).limit(10).execute()
            emails = email_result.data or []

        return {
            "contact": {
                "id": contact_id,
                "name": full_name,
                "email": contact.get("email"),
                "company": contact.get("company"),
                "notes": contact.get("notes")
            },
            "meetings": meetings.data or [],
            "calendar_events": events.data or [],
            "emails": emails
        }
    except Exception as e:
        logger.error(f"Error getting contact history: {e}")
        return {"error": str(e)}


def _create_contact(input: Dict) -> Dict[str, Any]:
    """Create a new contact with duplicate checking."""
    try:
        first_name = input.get("first_name", "").strip()
        if not first_name:
            return {"error": "first_name is required"}

        last_name = input.get("last_name", "").strip() or None
        email = input.get("email", "").strip() or None

        # Check for duplicates by name (case-insensitive)
        # Only check if we have enough info to make a meaningful match
        existing_contact = None

        if last_name:
            # Check for exact name match (first + last)
            name_check = supabase.table("contacts").select(
                "id, first_name, last_name, email, company"
            ).ilike("first_name", first_name).ilike(
                "last_name", last_name
            ).is_("deleted_at", "null").limit(1).execute()

            if name_check.data:
                existing_contact = name_check.data[0]
        elif email:
            # If no last name but email provided, check by email
            email_check = supabase.table("contacts").select(
                "id, first_name, last_name, email, company"
            ).eq("email", email).is_("deleted_at", "null").limit(1).execute()

            if email_check.data:
                existing_contact = email_check.data[0]

        # Also check email if provided (even when name check passed)
        if not existing_contact and email:
            email_check = supabase.table("contacts").select("id, first_name, last_name, email").ilike(
                "email", email.strip()
            ).is_("deleted_at", "null").limit(1).execute()
            if email_check.data:
                existing = email_check.data[0]
                return {
                    "warning": f"Contact with email '{email}' already exists: {existing.get('first_name', '')} {existing.get('last_name', '')}",
                    "existing_contact_id": existing["id"]
                }

        # If duplicate found, return early
        if existing_contact:
            existing_name = f"{existing_contact.get('first_name', '')} {existing_contact.get('last_name', '')}".strip()
            logger.info(f"Contact already exists: {existing_name} (ID: {existing_contact['id']})")
            return {
                "success": True,
                "already_exists": True,
                "contact_id": existing_contact["id"],
                "name": existing_name,
                "email": existing_contact.get("email"),
                "company": existing_contact.get("company"),
                "message": f"Contact already exists: {existing_name}"
            }

        # No duplicate found, proceed with creation
        contact_data = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "company": input.get("company", "").strip() or None,
            "job_title": input.get("job_title", "").strip() or None,
            "phone": input.get("phone", "").strip() or None,
            "linkedin_url": input.get("linkedin_url", "").strip() or None,
            "notes": input.get("notes", "").strip() or None,
            "last_sync_source": "supabase"
        }

        # Remove None values
        contact_data = {k: v for k, v in contact_data.items() if v is not None}

        result = supabase.table("contacts").insert(contact_data).execute()

        if result.data:
            contact = result.data[0]
            name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
            logger.info(f"Created contact via chat: {name} (ID: {contact['id']})")
            return {
                "success": True,
                "already_exists": False,
                "contact_id": contact["id"],
                "name": name,
                "message": f"Created contact: {name}"
            }
        return {"error": "Failed to create contact"}
    except Exception as e:
        logger.error(f"Error creating contact: {e}")
        return {"error": str(e)}


def _update_contact(input: Dict) -> Dict[str, Any]:
    """Update an existing contact."""
    try:
        contact_name = input.get("contact_name", "").strip()
        contact_id = input.get("contact_id", "").strip()

        # Find the contact first
        if contact_id:
            result = supabase.table("contacts").select("*").eq("id", contact_id).execute()
        elif contact_name:
            safe_name = _sanitize_ilike(contact_name)
            if not safe_name:
                return {"error": "Invalid contact name"}
            result = supabase.table("contacts").select("*").or_(
                f"first_name.ilike.%{safe_name}%,last_name.ilike.%{safe_name}%"
            ).is_("deleted_at", "null").limit(1).execute()
        else:
            return {"error": "Either contact_name or contact_id is required"}

        if not result.data:
            return {"error": "Contact not found"}

        contact = result.data[0]
        contact_id = contact["id"]

        # Build update fields
        update_fields = {}
        for field in ["first_name", "last_name", "email", "company", "job_title",
                      "phone", "linkedin_url", "notes", "birthday"]:
            if field in input:
                val = input[field]
                if val is None or val == "":
                    update_fields[field] = None  # Clear the field
                elif isinstance(val, str):
                    update_fields[field] = val.strip()
                else:
                    update_fields[field] = val

        if not update_fields:
            return {"error": "No fields to update"}

        # Add metadata
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        update_fields["last_sync_source"] = "supabase"

        supabase.table("contacts").update(update_fields).eq("id", contact_id).execute()

        # Fetch updated record
        updated = supabase.table("contacts").select("*").eq("id", contact_id).execute()

        if updated.data:
            c = updated.data[0]
            name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
            logger.info(f"Updated contact via chat: {name}")
            return {
                "success": True,
                "contact_id": contact_id,
                "name": name,
                "updated_fields": list(update_fields.keys()),
                "message": f"Updated contact: {name}"
            }
        return {"error": "Update verification failed"}
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        return {"error": str(e)}


def _add_contact_note(input: Dict) -> Dict[str, Any]:
    """Add a note to an existing contact."""
    try:
        contact_name = input.get("contact_name", "").strip()
        note = input.get("note", "").strip()

        if not contact_name:
            return {"error": "contact_name is required"}
        if not note:
            return {"error": "note is required"}

        # Find the contact
        safe_name = _sanitize_ilike(contact_name)
        if not safe_name:
            return {"error": "Invalid contact name"}
        result = supabase.table("contacts").select(
            "id, first_name, last_name, notes"
        ).or_(
            f"first_name.ilike.%{safe_name}%,last_name.ilike.%{safe_name}%"
        ).is_("deleted_at", "null").limit(1).execute()

        if not result.data:
            return {"error": f"Contact '{contact_name}' not found"}

        contact = result.data[0]
        contact_id = contact["id"]
        existing_notes = contact.get("notes") or ""

        # Append the new note with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_notes = f"{existing_notes}\n\n[{timestamp}] {note}".strip()

        supabase.table("contacts").update({
            "notes": new_notes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_source": "supabase"
        }).eq("id", contact_id).execute()

        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        logger.info(f"Added note to contact via chat: {name}")

        return {
            "success": True,
            "contact_id": contact_id,
            "name": name,
            "note_added": note,
            "message": f"Added note to {name}"
        }
    except Exception as e:
        logger.error(f"Error adding contact note: {e}")
        return {"error": str(e)}


def _who_to_contact(input: Dict) -> Dict[str, Any]:
    """Find contacts you haven't interacted with recently."""
    try:
        days_inactive = input.get("days_inactive", 30)
        limit = input.get("limit", 5)

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_inactive)).isoformat()

        # Get contacts with their last meeting date
        # Limit to 100 and order by least-recently-updated to cap N+1 queries
        contacts = supabase.table("contacts").select(
            "id, first_name, last_name, company, email"
        ).is_("deleted_at", "null").order("updated_at", desc=False).limit(100).execute()

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
                    safe_email = _sanitize_ilike(email)
                    recent_email = supabase.table("emails").select(
                        "date"
                    ).or_(
                        f"sender.ilike.%{safe_email}%,recipient.ilike.%{safe_email}%"
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
        logger.error(f"Error finding contacts to reach out to: {e}")
        return {"error": str(e)}
