import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_database
from app.api.models import (
    ContactInteractionsResponse,
    ContactSummaryResponse,
    CreateContactRequest,
    LinkContactRequest,
)

router = APIRouter(tags=["Contacts"])
logger = logging.getLogger("Jarvis.Intelligence.API.Contacts")


def _build_contact_name(first_name: Optional[str], last_name: Optional[str]) -> str:
    pieces = [first_name or "", last_name or ""]
    return " ".join(part for part in pieces if part).strip()


@router.patch("/meetings/{meeting_id}/link-contact")
async def link_contact_to_meeting(meeting_id: str, request: LinkContactRequest):
    """Attach a contact to an existing meeting record."""
    db = get_database()

    try:
        logger.info("Linking meeting %s to contact %s", meeting_id, request.contact_id)

        # First get the contact details
        contact = (
            db.client.table("contacts")
            .select("first_name, last_name, company")
            .eq("id", request.contact_id)
            .single()
            .execute()
        )
        
        if not contact.data:
            raise HTTPException(status_code=404, detail=f"Contact {request.contact_id} not found")

        contact_name = _build_contact_name(
            contact.data.get("first_name"), contact.data.get("last_name")
        )

        # Update BOTH contact_id AND contact_name - contact_name is needed for Notion sync!
        result = (
            db.client.table("meetings")
            .update({
                "contact_id": request.contact_id,
                "contact_name": contact_name,  # Critical for Notion sync
                "updated_at": datetime.now(timezone.utc).isoformat()  # Trigger sync
            })
            .eq("id", meeting_id)
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

        return {
            "status": "success",
            "meeting_id": meeting_id,
            "contact_id": request.contact_id,
            "contact_name": contact_name,
            "company": contact.data.get("company", ""),
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed linking contact %s to meeting %s", request.contact_id, meeting_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/contacts")
async def create_contact(request: CreateContactRequest):
    """Create a contact and optionally link it to a meeting."""
    db = get_database()

    try:
        logger.info("Creating contact %s %s", request.first_name, request.last_name or "")

        payload = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "company": request.company,
            "position": request.position,
            "email": request.email,
            "phone": request.phone,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        result = db.client.table("contacts").insert(payload).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create contact")

        contact_id = result.data[0]["id"]
        contact_name = _build_contact_name(request.first_name, request.last_name)

        if request.link_to_meeting_id:
            db.client.table("meetings").update({"contact_id": contact_id}).eq(
                "id", request.link_to_meeting_id
            ).execute()
            logger.info(
                "Linked new contact %s to meeting %s",
                contact_id,
                request.link_to_meeting_id,
            )

        return {
            "status": "success",
            "contact_id": contact_id,
            "contact_name": contact_name,
            "linked_to_meeting": request.link_to_meeting_id,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to create contact")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/contacts/search")
async def search_contacts(q: str, limit: int = 5):
    """Search contacts by partial name match."""
    db = get_database()

    try:
        if not q or len(q.strip()) < 2:
            return {"contacts": []}

        result = (
            db.client.table("contacts")
            .select("id, first_name, last_name, company, position")
            .or_(f"first_name.ilike.%{q}%,last_name.ilike.%{q}%")
            .is_("deleted_at", "null")
            .limit(limit)
            .execute()
        )

        contacts = [
            {
                "id": c.get("id"),
                "name": _build_contact_name(c.get("first_name"), c.get("last_name")),
                "company": c.get("company"),
                "position": c.get("position"),
            }
            for c in result.data
        ]

        return {"contacts": contacts}

    except Exception as exc:
        logger.exception("Failed to search contacts for query %s", q)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/contacts/{contact_id}/interactions", response_model=ContactInteractionsResponse)
async def get_contact_interactions(contact_id: str, limit: int = 50) -> ContactInteractionsResponse:
    """Return the recent interactions for a contact."""
    db = get_database()

    try:
        interactions = db.get_contact_interactions(contact_id, limit=limit)
        counts = {"meeting": 0, "email": 0, "calendar_event": 0, "total": len(interactions)}
        for interaction in interactions:
            interaction_type = interaction.get("interaction_type")
            if interaction_type in counts:
                counts[interaction_type] += 1

        contact = (
            db.client.table("contacts")
            .select("first_name, last_name, email, company")
            .eq("id", contact_id)
            .single()
            .execute()
        )
        if not contact.data:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")

        contact_name = _build_contact_name(
            contact.data.get("first_name"), contact.data.get("last_name")
        )

        return ContactInteractionsResponse(
            status="success",
            contact_id=contact_id,
            contact_name=contact_name,
            total_interactions=counts["total"],
            interactions=interactions,
            summary=counts,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch interactions for contact %s", contact_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/contacts/{contact_id}/summary", response_model=ContactSummaryResponse)
async def get_contact_summary(contact_id: str) -> ContactSummaryResponse:
    """Return an aggregated summary for a contact."""
    from datetime import datetime

    db = get_database()

    try:
        contact = (
            db.client.table("contacts")
            .select("*")
            .eq("id", contact_id)
            .single()
            .execute()
        )
        if not contact.data:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")

        interactions = db.get_contact_interactions(contact_id, limit=10)

        now = datetime.utcnow().isoformat()
        upcoming = (
            db.client.table("calendar_events")
            .select("*")
            .eq("contact_id", contact_id)
            .gte("start_time", now)
            .is_("deleted_at", "null")
            .limit(5)
            .execute()
        )

        all_interactions = db.get_contact_interactions(contact_id, limit=1000)
        counts = {
            "meetings": sum(1 for i in all_interactions if i.get("interaction_type") == "meeting"),
            "emails": sum(1 for i in all_interactions if i.get("interaction_type") == "email"),
            "calendar_events": sum(
                1 for i in all_interactions if i.get("interaction_type") == "calendar_event"
            ),
        }

        return ContactSummaryResponse(
            status="success",
            contact=contact.data,
            interaction_counts=counts,
            recent_interactions=interactions,
            upcoming_events=upcoming.data,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to build summary for contact %s", contact_id)
        raise HTTPException(status_code=500, detail=str(exc))
