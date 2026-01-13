from fastapi import APIRouter

from app.api.routes import beeper, briefing, calendar, chat, clarifications, contacts, documents, emails, health, journaling, knowledge, memory, transcripts


router = APIRouter()

router.include_router(transcripts.router)
router.include_router(journaling.router)
router.include_router(emails.router)
router.include_router(calendar.router)
router.include_router(contacts.router)
router.include_router(documents.router)
router.include_router(briefing.router)
router.include_router(health.router)
router.include_router(chat.router)
router.include_router(beeper.router)
router.include_router(memory.router)
router.include_router(clarifications.router, prefix="/clarifications")
router.include_router(knowledge.router)

