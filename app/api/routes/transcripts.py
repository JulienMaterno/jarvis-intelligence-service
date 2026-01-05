import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.dependencies import get_services
from app.api.models import AnalysisResponse, TranscriptRequest
from app.services.sync_trigger import trigger_syncs_for_records
from app.features.telegram import (
    send_telegram_message, 
    build_processing_result_message,
    send_meeting_feedback,
)

router = APIRouter(tags=["Transcripts"])
logger = logging.getLogger("Jarvis.Intelligence.API.Transcripts")


async def _send_processing_notification(db_records: dict, analysis: dict) -> None:
    """Send Telegram notification with processing results."""
    try:
        category = analysis.get("primary_category", "other")
        message = build_processing_result_message(
            category=category,
            db_records=db_records,
            analysis=analysis
        )
        await send_telegram_message(message)
        logger.info("Sent Telegram notification for transcript processing")
    except Exception as e:
        logger.error("Failed to send Telegram notification: %s", e, exc_info=True)


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
async def process_transcript(transcript_id: str, background_tasks: BackgroundTasks) -> AnalysisResponse:
    """Process an existing transcript and persist structured AI output."""
    analyzer, db = get_services()

    try:
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

        existing_topics = db.get_existing_reflection_topics()
        analysis = analyzer.analyze_transcript(
            transcript=transcript_text,
            filename=filename,
            recording_date=recording_date,
            existing_topics=existing_topics,
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
            m_id, _, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
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
        background_tasks.add_task(_send_processing_notification, db_records, analysis)
        
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
        analysis = analyzer.analyze_transcript(
            transcript=request.transcript,
            filename=request.filename,
            recording_date=request.recording_date,
            existing_topics=existing_topics,
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
        background_tasks.add_task(_send_processing_notification, db_records, analysis)
        
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
