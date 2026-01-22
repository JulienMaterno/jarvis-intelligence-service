import logging
import os
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.dependencies import get_services, get_memory
from app.api.models import AnalysisResponse, TranscriptRequest, ProcessTranscriptRequest
from app.services.sync_trigger import trigger_syncs_for_records
from app.core.logging_utils import sanitize_log_message
from app.features.telegram import (
    send_telegram_message,
    build_processing_result_message,
    send_meeting_feedback,
)

router = APIRouter(tags=["Transcripts"])
logger = logging.getLogger("Jarvis.Intelligence.API.Transcripts")

# Default Telegram user/chat ID for clarifications
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0")) or TELEGRAM_CHAT_ID


async def _seed_memory_from_analysis(analysis: dict, source_file: str) -> None:
    """Extract and store memories from transcript analysis."""
    try:
        memory = get_memory()
        await memory.seed_from_transcript_analysis(analysis, source_file)
        logger.info("Seeded memories from transcript analysis")
    except Exception as e:
        logger.warning(f"Failed to seed memories: {e}")


async def _handle_clarifications_needed(
    analysis: dict,
    db_records: dict,
    transcript_id: str,
    db
) -> None:
    """
    Handle clarifications needed from the analysis.
    
    This:
    1. Checks if we can resolve from existing DB
    2. Asks user via Telegram if not
    3. Stores answers for future reference
    """
    clarifications = analysis.get("clarifications_needed", [])
    if not clarifications:
        return
    
    try:
        from app.features.clarification.service import handle_clarifications
        
        # Determine which record to associate clarifications with
        record_type = None
        record_id = None
        
        if db_records.get("meeting_ids"):
            record_type = "meeting"
            record_id = db_records["meeting_ids"][0]
        elif db_records.get("reflection_ids"):
            record_type = "reflection"
            record_id = db_records["reflection_ids"][0]
        elif db_records.get("journal_ids"):
            record_type = "journal"
            record_id = db_records["journal_ids"][0]
        
        result = await handle_clarifications(
            clarifications=clarifications,
            record_type=record_type,
            record_id=record_id,
            transcript_id=transcript_id,
            db=db,
            user_id=TELEGRAM_USER_ID,
            chat_id=TELEGRAM_CHAT_ID,
        )
        
        logger.info(
            "Clarification results - Resolved: %d, Pending: %d, Failed: %d",
            len(result.get("resolved", [])),
            len(result.get("pending", [])),
            len(result.get("failed", []))
        )
        
    except Exception as e:
        logger.error("Failed to handle clarifications: %s", e, exc_info=True)


async def _send_processing_notification(db_records: dict, analysis: dict, transcript_text: str = None) -> None:
    """Send Telegram notification with processing results."""
    try:
        category = analysis.get("primary_category", "other")
        # For "other" category, include transcript preview so user knows what was captured
        preview = transcript_text[:200] if transcript_text else None
        message = build_processing_result_message(
            category=category,
            db_records=db_records,
            analysis=analysis,
            transcript_preview=preview
        )
        await send_telegram_message(message)
        logger.info("Sent Telegram notification for transcript processing")
    except Exception as e:
        logger.error("Failed to send Telegram notification: %s", e, exc_info=True)


async def _handle_proactive_outreach(analysis: dict) -> None:
    """
    Handle proactive outreach if the AI determined it would be valuable.
    
    This sends thoughtful follow-up messages to the user when:
    - They expressed concerns/frustrations that could use support
    - They asked questions that could benefit from research
    - Patterns were observed across their recordings
    - There's valuable follow-up or insight to share
    
    The AI decides whether to reach out in the analysis phase, and if so,
    provides a warm, supportive message to send.
    """
    outreach = analysis.get("proactive_outreach", {})
    
    if not outreach or not outreach.get("should_reach_out"):
        return
    
    message = outreach.get("message")
    if not message:
        logger.debug("Proactive outreach enabled but no message provided")
        return
    
    outreach_type = outreach.get("outreach_type", "follow_up")
    reason = outreach.get("reason", "")
    
    try:
        # Add a slight delay so it doesn't feel immediate/robotic
        import asyncio
        await asyncio.sleep(5)  # 5 second delay
        
        # Format the message with appropriate emoji based on type
        type_emoji = {
            "support": "💭",
            "research": "🔍",
            "pattern_observation": "🔮",
            "follow_up": "💡",
        }.get(outreach_type, "💬")
        
        formatted_message = f"{type_emoji} *Jarvis thinking out loud...*\n\n{message}"
        
        # Add research prompt if research is needed
        research_topics = outreach.get("research_needed", [])
        if research_topics:
            topics_str = ", ".join(research_topics[:3])
            formatted_message += f"\n\n_Want me to research: {topics_str}? Just reply yes!_"
        
        # Store the outreach context in chat_messages so future replies have context
        try:
            from app.features.chat.storage import get_chat_storage
            storage = get_chat_storage()
            await storage.store_message(
                role="assistant",
                content=formatted_message,
                source="proactive_outreach",
                metadata={
                    "outreach_type": outreach_type,
                    "reason": reason,
                    "research_needed": research_topics,
                    "original_analysis_category": analysis.get("primary_category"),
                }
            )
            logger.info("Stored proactive outreach context in chat history")
        except Exception as store_error:
            logger.warning("Failed to store outreach context: %s", store_error)
        
        await send_telegram_message(formatted_message)
        logger.info(
            "Sent proactive outreach [%s]: %s (reason: %s)",
            outreach_type,
            message[:50],
            reason[:50]
        )
    except Exception as e:
        logger.error("Failed to send proactive outreach: %s", e, exc_info=True)


async def _send_meeting_feedback_notifications(
    meeting_ids: list, 
    meetings_data: list, 
    contact_matches: list
) -> None:
    """
    Send feedback notifications for each meeting created.
    This triggers for ALL meetings, whether standalone or with journals.
    """
    if not meeting_ids or not meetings_data:
        return
    
    try:
        for i, (meeting_id, meeting_data) in enumerate(zip(meeting_ids, meetings_data)):
            # Find matching contact info for this meeting
            contact_match = None
            for cm in contact_matches:
                if cm.get("meeting_id") == meeting_id:
                    contact_match = cm
                    break
            
            # Send feedback message for this meeting
            await send_meeting_feedback(
                meeting_id=meeting_id,
                meeting_data=meeting_data,
                contact_match=contact_match
            )
            logger.info(f"Sent meeting feedback for: {meeting_data.get('title', 'Untitled')}")
    except Exception as e:
        logger.error("Failed to send meeting feedback notifications: %s", e, exc_info=True)


def _ensure_task_creation(
    *,
    primary_category: str,
    analysis: dict,
    db_records: dict,
    db,
    origin_id: str,
    origin_type: str,
) -> None:
    """Create follow-up tasks when analysis indicates they belong to the origin."""
    if not analysis.get("tasks"):
        return

    if origin_type == "meeting":
        task_ids = db.create_tasks(
            tasks_data=analysis["tasks"],
            origin_id=origin_id,
            origin_type=origin_type,
        )
        db_records["task_ids"].extend(task_ids)
        return

    if primary_category == origin_type:
        task_ids = db.create_tasks(
            tasks_data=analysis["tasks"],
            origin_id=origin_id,
            origin_type=origin_type,
        )
        db_records["task_ids"].extend(task_ids)


@router.post("/process/{transcript_id}", response_model=AnalysisResponse)
async def process_transcript(
    transcript_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[ProcessTranscriptRequest] = None
) -> AnalysisResponse:
    """
    Process an existing transcript and persist structured AI output.
    
    Args:
        transcript_id: ID of the transcript to process
        request: Optional request body with person_context for meeting attribution
    """
    analyzer, db = get_services()

    try:
        # Extract person context if provided
        person_context = None
        user_notes = None
        if request and request.person_context:
            person_context = {
                "confirmed_person_name": request.person_context.confirmed_person_name,
                "person_confirmed": request.person_context.person_confirmed,
                "contact_id": request.person_context.contact_id,
                "person_email": request.person_context.person_email,  # Email from calendar
                "previous_meetings_summary": request.person_context.previous_meetings_summary,
            }
            # Log without PII (email is redacted)
            person_name = person_context.get('confirmed_person_name', 'Unknown')
            logger.info(f"Processing transcript {transcript_id} with person context: {person_name}")
        
        # Extract user notes if provided (from /note command during meeting)
        if request and request.user_notes:
            user_notes = request.user_notes
            logger.info(f"Processing transcript {transcript_id} with {len(user_notes)} user note(s)")
        
        if not person_context and not user_notes:
            logger.info("Processing stored transcript %s", transcript_id)

        transcript_record = db.get_transcript(transcript_id)
        if not transcript_record:
            raise HTTPException(status_code=404, detail=f"Transcript {transcript_id} not found")

        # IDEMPOTENCY CHECK: Skip if already processed
        # Check if any meetings, journals, or reflections already link to this transcript
        existing_records = db.get_records_for_transcript(transcript_id)
        if existing_records.get("already_processed"):
            logger.info(f"Transcript {transcript_id} already processed, returning existing records")
            return AnalysisResponse(
                status="already_processed",
                analysis={"primary_category": "already_processed", "note": "Transcript was already analyzed"},
                db_records={
                    "transcript_id": transcript_id,
                    "meeting_ids": existing_records.get("meeting_ids", []),
                    "reflection_ids": existing_records.get("reflection_ids", []),
                    "journal_ids": existing_records.get("journal_ids", []),
                    "task_ids": existing_records.get("task_ids", []),
                    "contact_matches": [],
                }
            )

        transcript_text = transcript_record.get("full_text", "")
        filename = transcript_record.get("source_file", "unknown")
        recording_date = None  # Delegate date inference to analyzer when absent

        # Prepend user notes to transcript if provided (critical context from the user)
        if user_notes:
            notes_header = "USER NOTES (added by the user during the meeting - treat as authoritative context):\n"
            for i, note in enumerate(user_notes, 1):
                notes_header += f"  Note {i}: {note}\n"
            notes_header += "\nTRANSCRIPT:\n"
            transcript_text = notes_header + transcript_text
            logger.info(f"Prepended {len(user_notes)} user note(s) to transcript")

        # TWO-STAGE ARCHITECTURE:
        # Stage 1 (Haiku) will gather context from DB
        # Stage 2 (Sonnet) will do the analysis
        # The old manual fetching is kept as fallback for backward compatibility
        
        existing_topics = db.get_existing_reflection_topics()
        
        # Fetch known contacts for smart transcription correction (fallback if Stage 1 fails)
        known_contacts = db.get_contacts_for_transcription(limit=200)
        logger.info(f"Fetched {len(known_contacts)} contacts for transcription correction")
        
        # Fetch recent calendar events to help identify meeting participants (fallback)
        try:
            recent_calendar_events = db.get_recent_calendar_events(hours_back=3)
            if recent_calendar_events:
                logger.info(f"Found {len(recent_calendar_events)} recent calendar events for context")
        except Exception as e:
            logger.warning(f"Could not fetch calendar events (method may not be deployed): {e}")
            recent_calendar_events = []
        
        # Use async analyzer for non-blocking LLM call
        # Pass db for two-stage architecture (Stage 1 will gather rich context)
        analysis = await analyzer.analyze_transcript_async(
            transcript=transcript_text,
            filename=filename,
            recording_date=recording_date,
            existing_topics=existing_topics,
            known_contacts=known_contacts,
            person_context=person_context,  # Pass person context to analyzer
            calendar_context=recent_calendar_events,  # Pass calendar events for name correction
            db=db,  # NEW: Pass db for two-stage context gathering
            use_two_stage=True,  # NEW: Enable two-stage processing
        )

        db_records = {
            "transcript_id": transcript_id,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
            "contact_matches": [],
        }

        primary_category = analysis.get("primary_category", "other")

        for journal in analysis.get("journals", []):
            j_id, _ = db.create_journal(
                journal_data=journal,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
                transcript_id=transcript_id,
            )
            db_records["journal_ids"].append(j_id)

            if primary_category == "journal" and analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis["tasks"],
                    origin_id=j_id,
                    origin_type="journal",
                )
                db_records["task_ids"].extend(task_ids)

            tomorrow_focus = journal.get("tomorrow_focus", [])
            if tomorrow_focus:
                focus_tasks = [
                    {
                        "title": item,
                        "description": "From journal tomorrow_focus",
                        "due_date": None,
                    }
                    for item in tomorrow_focus
                    if isinstance(item, str) and len(item) > 3
                ]
                if focus_tasks:
                    task_ids = db.create_tasks(
                        tasks_data=focus_tasks,
                        origin_id=j_id,
                        origin_type="journal",
                    )
                    db_records["task_ids"].extend(task_ids)
                    logger.info("Created %s tasks from journal tomorrow_focus", len(task_ids))

        for meeting in analysis.get("meetings", []):
            # Get person_email from person_context for enhanced contact matching
            person_email = person_context.get("person_email") if person_context else None
            
            m_id, _, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
                transcript_id=transcript_id,
                person_email=person_email,  # Pass email for contact matching
            )
            db_records["meeting_ids"].append(m_id)

            if contact_match_info.get("searched_name"):
                contact_match_info["meeting_id"] = m_id
                contact_match_info["meeting_title"] = meeting.get("title", "Untitled")
                db_records["contact_matches"].append(contact_match_info)

            _ensure_task_creation(
                primary_category=primary_category,
                analysis=analysis,
                db_records=db_records,
                db=db,
                origin_id=m_id,
                origin_type="meeting",
            )

        for reflection in analysis.get("reflections", []):
            tags = reflection.get("tags", [])
            title = reflection.get("title", "")
            
            # AI-DRIVEN ROUTING: AI decides whether to append via append_to_id
            append_to_id = reflection.get("append_to_id")
            
            if append_to_id:
                # AI explicitly chose to append to this reflection
                # Validate the ID exists
                existing_reflection = db.get_reflection_by_id(append_to_id)
                
                if existing_reflection:
                    logger.info(
                        "AI-directed append to reflection '%s' (id: %s)",
                        existing_reflection.get("title", "Untitled"),
                        append_to_id[:8],
                    )
                    r_id, _ = db.append_to_reflection(
                        reflection_id=append_to_id,
                        new_sections=reflection.get("sections", []),
                        new_content=reflection.get("content"),
                        additional_tags=tags,
                        source_file=filename,
                        transcript_id=transcript_id,
                    )
                    db_records["reflection_ids"].append(r_id)
                    db_records["reflection_appended"] = True
                    db_records["appended_to_title"] = existing_reflection.get("title", "Untitled")
                else:
                    # AI gave invalid ID - create new instead
                    logger.warning(
                        "AI provided invalid append_to_id '%s', creating new reflection",
                        append_to_id,
                    )
                    r_id, _ = db.create_reflection(
                        reflection_data=reflection,
                        transcript=transcript_text,
                        duration=transcript_record.get("audio_duration_seconds", 0),
                        filename=filename,
                        transcript_id=transcript_id,
                    )
                    db_records["reflection_ids"].append(r_id)
            else:
                # AI chose to create new reflection
                logger.info(
                    "AI-directed create new reflection: '%s'",
                    title,
                )
                r_id, _ = db.create_reflection(
                    reflection_data=reflection,
                    transcript=transcript_text,
                    duration=transcript_record.get("audio_duration_seconds", 0),
                    filename=filename,
                    transcript_id=transcript_id,
                )
                db_records["reflection_ids"].append(r_id)

            if primary_category == "reflection" and analysis.get("tasks") and not db_records["meeting_ids"]:
                task_ids = db.create_tasks(
                    tasks_data=analysis["tasks"],
                    origin_id=r_id,
                    origin_type="reflection",
                )
                db_records["task_ids"].extend(task_ids)

        # Process CRM updates (contact info learned from meetings)
        crm_updates = analysis.get("crm_updates", [])
        if crm_updates:
            try:
                crm_result = db.apply_crm_updates(crm_updates)
                if crm_result.get("updated"):
                    logger.info("Applied CRM updates: %s", crm_result["updated"])
                    db_records["crm_updates_applied"] = crm_result["updated"]
                if crm_result.get("not_found"):
                    logger.info("CRM updates skipped (contacts not found): %s", crm_result["not_found"])
            except Exception as e:
                logger.error("Failed to apply CRM updates: %s", e)

        # Schedule background tasks
        background_tasks.add_task(trigger_syncs_for_records, db_records)
        background_tasks.add_task(_send_processing_notification, db_records, analysis, transcript_text)
        background_tasks.add_task(_seed_memory_from_analysis, analysis, filename)
        
        # Handle proactive outreach (AI-initiated follow-up messages)
        if analysis.get("proactive_outreach", {}).get("should_reach_out"):
            background_tasks.add_task(_handle_proactive_outreach, analysis)
        
        # Handle clarifications (ask user via Telegram if AI has questions)
        if analysis.get("clarifications_needed"):
            background_tasks.add_task(
                _handle_clarifications_needed,
                analysis,
                db_records,
                transcript_id,
                db
            )
        
        # Send meeting feedback for EACH meeting (even if created with journal)
        if db_records["meeting_ids"]:
            background_tasks.add_task(
                _send_meeting_feedback_notifications,
                db_records["meeting_ids"],
                analysis.get("meetings", []),
                db_records["contact_matches"]
            )
        
        logger.info("Scheduled sync triggers for records from transcript %s", transcript_id)

        return AnalysisResponse(status="success", analysis=analysis, db_records=db_records)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to process transcript %s", transcript_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_transcript(request: TranscriptRequest, background_tasks: BackgroundTasks) -> AnalysisResponse:
    """Analyze a raw transcript and persist the structured result."""
    analyzer, db = get_services()

    try:
        logger.info("Analyzing transcript upload %s", request.filename)

        transcript_id = db.create_transcript(
            source_file=request.filename,
            full_text=request.transcript,
            audio_duration_seconds=request.audio_duration_seconds,
            language=request.language,
        )

        existing_topics = db.get_existing_reflection_topics()
        
        # Fetch known contacts for smart transcription correction (fallback)
        known_contacts = db.get_contacts_for_transcription(limit=200)
        
        # Use async analyzer for non-blocking LLM call (with two-stage architecture)
        analysis = await analyzer.analyze_transcript_async(
            transcript=request.transcript,
            filename=request.filename,
            recording_date=request.recording_date,
            existing_topics=existing_topics,
            known_contacts=known_contacts,
            db=db,  # Enable two-stage context gathering
            use_two_stage=True,
        )

        db_records = {
            "transcript_id": transcript_id,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
            "contact_matches": [],
        }

        primary_category = analysis.get("primary_category", "other")

        for journal in analysis.get("journals", []):
            j_id, _ = db.create_journal(
                journal_data=journal,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id,
            )
            db_records["journal_ids"].append(j_id)

            if primary_category == "journal" and analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis["tasks"],
                    origin_id=j_id,
                    origin_type="journal",
                )
                db_records["task_ids"].extend(task_ids)

            tomorrow_focus = journal.get("tomorrow_focus", [])
            if tomorrow_focus:
                focus_tasks = [
                    {
                        "title": item,
                        "description": "From journal tomorrow_focus",
                        "due_date": None,
                    }
                    for item in tomorrow_focus
                    if isinstance(item, str) and len(item) > 3
                ]
                if focus_tasks:
                    task_ids = db.create_tasks(
                        tasks_data=focus_tasks,
                        origin_id=j_id,
                        origin_type="journal",
                    )
                    db_records["task_ids"].extend(task_ids)
                    logger.info("Created %s tasks from journal tomorrow_focus", len(task_ids))

        for meeting in analysis.get("meetings", []):
            m_id, _, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id,
            )
            db_records["meeting_ids"].append(m_id)

            if contact_match_info.get("searched_name"):
                contact_match_info["meeting_id"] = m_id
                contact_match_info["meeting_title"] = meeting.get("title", "Untitled")
                db_records["contact_matches"].append(contact_match_info)

            _ensure_task_creation(
                primary_category=primary_category,
                analysis=analysis,
                db_records=db_records,
                db=db,
                origin_id=m_id,
                origin_type="meeting",
            )

        for reflection in analysis.get("reflections", []):
            tags = reflection.get("tags", [])
            title = reflection.get("title", "")
            
            # AI-DRIVEN ROUTING: AI decides whether to append via append_to_id
            append_to_id = reflection.get("append_to_id")
            
            if append_to_id:
                # AI explicitly chose to append to this reflection
                existing_reflection = db.get_reflection_by_id(append_to_id)
                
                if existing_reflection:
                    logger.info(
                        "AI-directed append to reflection '%s' (id: %s)",
                        existing_reflection.get("title", "Untitled"),
                        append_to_id[:8],
                    )
                    r_id, _ = db.append_to_reflection(
                        reflection_id=append_to_id,
                        new_sections=reflection.get("sections", []),
                        new_content=reflection.get("content"),
                        additional_tags=tags,
                        source_file=request.filename,
                        transcript_id=transcript_id,
                    )
                    db_records["reflection_ids"].append(r_id)
                    db_records["reflection_appended"] = True
                    db_records["appended_to_title"] = existing_reflection.get("title", "Untitled")
                else:
                    logger.warning(
                        "AI provided invalid append_to_id '%s', creating new reflection",
                        append_to_id,
                    )
                    r_id, _ = db.create_reflection(
                        reflection_data=reflection,
                        transcript=request.transcript,
                        duration=request.audio_duration_seconds or 0,
                        filename=request.filename,
                        transcript_id=transcript_id,
                    )
                    db_records["reflection_ids"].append(r_id)
            else:
                logger.info(
                    "AI-directed create new reflection: '%s'",
                    title,
                )
                r_id, _ = db.create_reflection(
                    reflection_data=reflection,
                    transcript=request.transcript,
                    duration=request.audio_duration_seconds or 0,
                    filename=request.filename,
                    transcript_id=transcript_id,
                )
                db_records["reflection_ids"].append(r_id)

            if primary_category == "reflection" and analysis.get("tasks") and not db_records["meeting_ids"]:
                task_ids = db.create_tasks(
                    tasks_data=analysis["tasks"],
                    origin_id=r_id,
                    origin_type="reflection",
                )
                db_records["task_ids"].extend(task_ids)

        # Process CRM updates (contact info learned from meetings)
        crm_updates = analysis.get("crm_updates", [])
        if crm_updates:
            try:
                crm_result = db.apply_crm_updates(crm_updates)
                if crm_result.get("updated"):
                    logger.info("Applied CRM updates: %s", crm_result["updated"])
                    db_records["crm_updates_applied"] = crm_result["updated"]
                if crm_result.get("not_found"):
                    logger.info("CRM updates skipped (contacts not found): %s", crm_result["not_found"])
            except Exception as e:
                logger.error("Failed to apply CRM updates: %s", e)

        # Schedule background tasks
        background_tasks.add_task(trigger_syncs_for_records, db_records)
        background_tasks.add_task(_send_processing_notification, db_records, analysis, request.transcript)
        background_tasks.add_task(_seed_memory_from_analysis, analysis, request.filename)
        
        # Handle proactive outreach (AI-initiated follow-up messages)
        if analysis.get("proactive_outreach", {}).get("should_reach_out"):
            background_tasks.add_task(_handle_proactive_outreach, analysis)
        
        # Send meeting feedback for EACH meeting (even if created with journal)
        if db_records["meeting_ids"]:
            background_tasks.add_task(
                _send_meeting_feedback_notifications,
                db_records["meeting_ids"],
                analysis.get("meetings", []),
                db_records["contact_matches"]
            )
        
        logger.info("Scheduled sync triggers for new transcript %s", transcript_id)

        return AnalysisResponse(status="success", analysis=analysis, db_records=db_records)

    except Exception as exc:
        logger.exception("Failed to analyze transcript %s", request.filename)
        raise HTTPException(status_code=500, detail=str(exc))


# =========================================================================
# SCREENPIPE MEETING TRANSCRIPT ENDPOINT
# =========================================================================

from app.api.models import MeetingTranscriptRequest, MeetingTranscriptResponse


@router.post("/process/meeting-transcript", response_model=MeetingTranscriptResponse)
async def process_meeting_transcript(
    request: MeetingTranscriptRequest, 
    background_tasks: BackgroundTasks
) -> MeetingTranscriptResponse:
    """
    Process a meeting transcript from Screenpipe bridge.
    
    This endpoint receives enriched meeting transcripts with:
    - Calendar event metadata (title, attendees)
    - Screen context (OCR text, window titles)
    - Source app information
    
    It analyzes the transcript and creates meeting records.
    """
    analyzer, db = get_services()

    try:
        logger.info(
            "Processing Screenpipe meeting transcript: app=%s, duration=%d min",
            request.source_app,
            request.duration_minutes
        )
        
        # Build filename from metadata for consistency
        filename = f"screenpipe_{request.source_app}_{request.start_time[:10]}.txt"
        
        # Build enhanced context for the analyzer
        context_parts = []
        
        # CRITICAL: Identify the microphone user (Aaron) as the speaker
        user_name = request.user_name or "Aaron"
        context_parts.append(f"SPEAKER IDENTIFICATION: The person speaking into the microphone is {user_name}. They are the host/user. The OTHER person in the meeting is the one they met WITH.")
        context_parts.append(f"Meeting Duration: {request.duration_minutes} minutes")
        
        if request.calendar_event:
            cal = request.calendar_event
            if cal.title:
                context_parts.append(f"Calendar Event: {cal.title}")
            if cal.attendees:
                attendee_names = [a.get("name") or a.get("email", "") for a in cal.attendees]
                context_parts.append(f"Attendees: {', '.join(attendee_names)}")
        
        if request.screen_context:
            sc = request.screen_context
            if sc.window_titles:
                context_parts.append(f"Window Titles: {', '.join(sc.window_titles)}")
            if sc.visible_text_sample:
                context_parts.append(f"Screen Text: {sc.visible_text_sample[:500]}")
        
        # Include user notes if provided (from /note command during meeting)
        if request.user_notes:
            context_parts.append("USER NOTES (added by the user during the meeting - treat as authoritative context):")
            for i, note in enumerate(request.user_notes, 1):
                context_parts.append(f"  Note {i}: {note}")
        
        # Summary length guidance based on meeting duration
        if request.duration_minutes >= 60:
            context_parts.append("SUMMARY LENGTH: This is a LONG meeting (60+ min). Provide comprehensive summary (10-15 sentences).")
        elif request.duration_minutes >= 30:
            context_parts.append("SUMMARY LENGTH: This is a medium meeting (30-60 min). Provide detailed summary (6-10 sentences).")
        elif request.duration_minutes >= 15:
            context_parts.append("SUMMARY LENGTH: This is a shorter meeting (15-30 min). Provide concise summary (4-6 sentences).")
        else:
            context_parts.append("SUMMARY LENGTH: This is a brief meeting (<15 min). Provide brief summary (2-4 sentences).")
        
        # Prepend context to transcript for better analysis
        enhanced_transcript = request.transcript
        if context_parts:
            context_header = "MEETING CONTEXT:\n" + "\n".join(context_parts) + "\n\nTRANSCRIPT:\n"
            enhanced_transcript = context_header + request.transcript
        
        # First, save the transcript to database
        transcript_id = db.create_transcript(
            source_file=filename,
            full_text=request.transcript,
            audio_duration_seconds=request.duration_minutes * 60,
            language="auto",
        )
        logger.info("Saved Screenpipe transcript: %s", transcript_id)
        
        # Get existing topics for reflection routing
        existing_topics = db.get_existing_reflection_topics()
        
        # Fetch known contacts for smart transcription correction (fallback)
        known_contacts = db.get_contacts_for_transcription(limit=200)
        
        # Analyze with Claude (async for non-blocking, with two-stage architecture)
        analysis = await analyzer.analyze_transcript_async(
            transcript=enhanced_transcript,
            filename=filename,
            recording_date=request.start_time[:10],
            existing_topics=existing_topics,
            known_contacts=known_contacts,
            db=db,  # Enable two-stage context gathering
            use_two_stage=True,
        )
        
        db_records = {
            "transcript_id": transcript_id,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
            "contact_matches": [],
        }
        
        primary_category = analysis.get("primary_category", "meeting")
        
        # For Screenpipe transcripts, we force meeting creation
        # even if AI categorizes differently (it's a known meeting)
        meetings = analysis.get("meetings", [])
        
        # If no meeting was extracted but we have calendar info, create one
        if not meetings:
            meeting_title = (
                request.manual_title 
                or (request.calendar_event.title if request.calendar_event else None)
                or f"{request.source_app} Meeting"
            )
            meetings = [{
                "title": meeting_title,
                "summary": analysis.get("summary", "Auto-captured meeting"),
                "date": request.start_time,
                "topics_discussed": analysis.get("key_topics", []),
                "action_items": analysis.get("tasks", []),
            }]
            
            # Extract attendee as contact name if available
            if request.calendar_event and request.calendar_event.attendees:
                # Find first non-organizer attendee
                for attendee in request.calendar_event.attendees:
                    if not attendee.get("organizer"):
                        meetings[0]["contact_name"] = attendee.get("name") or attendee.get("email", "").split("@")[0]
                        break
        
        # Create meeting records
        for meeting in meetings:
            # Override title if manual title provided
            if request.manual_title:
                meeting["title"] = request.manual_title
            
            # Extract calendar event ID for linking
            calendar_event_id = None
            if request.calendar_event and request.calendar_event.google_event_id:
                calendar_event_id = request.calendar_event.google_event_id
            
            m_id, _, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=request.transcript,
                duration=request.duration_minutes * 60,
                filename=filename,
                transcript_id=transcript_id,
                calendar_event_id=calendar_event_id,
            )
            db_records["meeting_ids"].append(m_id)
            
            if contact_match_info.get("searched_name"):
                contact_match_info["meeting_id"] = m_id
                contact_match_info["meeting_title"] = meeting.get("title", "Untitled")
                db_records["contact_matches"].append(contact_match_info)
            
            # Create tasks from meeting action items
            if meeting.get("action_items"):
                task_data = [
                    {"title": item, "description": f"From {request.source_app} meeting"}
                    for item in meeting["action_items"]
                    if isinstance(item, str)
                ]
                if task_data:
                    task_ids = db.create_tasks(
                        tasks_data=task_data,
                        origin_id=m_id,
                        origin_type="meeting"
                    )
                    db_records["task_ids"].extend(task_ids)
        
        # Also create any standalone tasks from analysis
        if analysis.get("tasks"):
            origin_id = db_records["meeting_ids"][0] if db_records["meeting_ids"] else None
            if origin_id:
                task_ids = db.create_tasks(
                    tasks_data=analysis["tasks"],
                    origin_id=origin_id,
                    origin_type="meeting"
                )
                db_records["task_ids"].extend(task_ids)
        
        # Schedule background tasks
        background_tasks.add_task(trigger_syncs_for_records, db_records)
        background_tasks.add_task(_send_processing_notification, db_records, analysis, request.transcript)
        background_tasks.add_task(_seed_memory_from_analysis, analysis, "screenpipe_meeting")
        
        # Handle proactive outreach (AI-initiated follow-up messages)
        if analysis.get("proactive_outreach", {}).get("should_reach_out"):
            background_tasks.add_task(_handle_proactive_outreach, analysis)
        
        # Send meeting feedback notifications
        if db_records["meeting_ids"]:
            background_tasks.add_task(
                _send_meeting_feedback_notifications,
                db_records["meeting_ids"],
                meetings,
                db_records["contact_matches"]
            )
        
        meeting_id = db_records["meeting_ids"][0] if db_records["meeting_ids"] else None
        meeting_title = meetings[0].get("title") if meetings else None
        
        logger.info(
            "Processed Screenpipe transcript: meeting=%s, tasks=%d",
            meeting_id, len(db_records["task_ids"])
        )
        
        return MeetingTranscriptResponse(
            status="success",
            transcript_id=transcript_id,
            meeting_id=meeting_id,
            meeting_title=meeting_title,
            tasks_created=len(db_records["task_ids"]),
            contact_matches=db_records["contact_matches"]
        )
        
    except Exception as exc:
        logger.exception("Failed to process Screenpipe meeting transcript")
        raise HTTPException(status_code=500, detail=str(exc))
