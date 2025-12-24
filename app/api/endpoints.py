from fastapi import APIRouter

from app.api.routes import briefing, calendar, contacts, emails, health, journaling, transcripts


router = APIRouter()

router.include_router(transcripts.router)
router.include_router(journaling.router)
router.include_router(emails.router)
router.include_router(calendar.router)
router.include_router(contacts.router)
router.include_router(briefing.router)
router.include_router(health.router)
