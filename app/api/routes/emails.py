import logging
from fastapi import APIRouter, HTTPException

from app.api.dependencies import get_database
from app.api.models import CreateEmailRequest, EmailResponse, LinkEmailRequest

router = APIRouter(tags=["Emails"])
logger = logging.getLogger("Jarvis.Intelligence.API.Emails")


@router.post("/emails", response_model=EmailResponse)
async def create_email(request: CreateEmailRequest) -> EmailResponse:
    """Persist an email record and link it to related CRM entities."""
    db = get_database()

    try:
        logger.info("Creating email entry for subject %s", request.subject)

        email_id, email_url = db.create_email(
            subject=request.subject,
            from_email=request.from_email,
            to_emails=request.to_emails,
            body_text=request.body_text,
            body_html=request.body_html,
            from_name=request.from_name,
            cc_emails=request.cc_emails,
            direction=request.direction,
            sent_at=request.sent_at,
            received_at=request.received_at,
            message_id=request.message_id,
            thread_id=request.thread_id,
            contact_id=request.contact_id,
            contact_name=request.contact_name,
            meeting_id=request.meeting_id,
            category=request.category,
            tags=request.tags,
            has_attachments=request.has_attachments,
            attachment_names=request.attachment_names,
            source_provider=request.source_provider,
            raw_data=request.raw_data,
        )

        contact_name = None
        if request.contact_id:
            try:
                contact = (
                    db.client.table("contacts")
                    .select("first_name, last_name")
                    .eq("id", request.contact_id)
                    .single()
                    .execute()
                )
                if contact.data:
                    first_name = contact.data.get("first_name", "")
                    last_name = contact.data.get("last_name", "")
                    contact_name = f"{first_name} {last_name}".strip()
            except Exception as exc:
                logger.warning("Unable to fetch contact %s: %s", request.contact_id, exc)

        return EmailResponse(
            status="success",
            email_id=email_id,
            email_url=email_url,
            contact_id=request.contact_id,
            contact_name=contact_name,
        )

    except Exception as exc:
        logger.exception("Failed creating email for subject %s", request.subject)
        raise HTTPException(status_code=500, detail=str(exc))


@router.patch("/emails/{email_id}/link")
async def link_email(email_id: str, request: LinkEmailRequest):
    """Attach an email to a meeting or a contact."""
    db = get_database()

    try:
        logger.info("Linking email %s", email_id)

        update_data: dict[str, str] = {}
        if request.meeting_id:
            db.link_email_to_meeting(email_id, request.meeting_id)
            update_data["meeting_id"] = request.meeting_id

        if request.contact_id:
            db.client.table("emails").update({"contact_id": request.contact_id}).eq(
                "id", email_id
            ).execute()
            update_data["contact_id"] = request.contact_id

        return {"status": "success", "email_id": email_id, **update_data}

    except Exception as exc:
        logger.exception("Failed to link email %s", email_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/emails/thread/{thread_id}")
async def get_email_thread(thread_id: str):
    """Return all emails that belong to a thread."""
    db = get_database()

    try:
        emails = db.get_emails_by_thread(thread_id)
        return {
            "status": "success",
            "thread_id": thread_id,
            "email_count": len(emails),
            "emails": emails,
        }

    except Exception as exc:
        logger.exception("Failed to load thread %s", thread_id)
        raise HTTPException(status_code=500, detail=str(exc))
