import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.dependencies import get_services
from app.api.models import AnalysisResponse, TranscriptRequest
from app.services.sync_trigger import trigger_syncs_for_records

router = APIRouter(tags=["Transcripts"])
logger = logging.getLogger("Jarvis.Intelligence.API.Transcripts")


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
            topic_key = reflection.get("topic_key")
            tags = reflection.get("tags", [])
            title = reflection.get("title", "")

            existing_reflection = None
            if topic_key:
                existing_reflection = db.find_similar_reflection(
                    topic_key=topic_key,
                    tags=tags,
                    title=title,
                )

            if existing_reflection:
                logger.info(
                    "Appending to reflection %s (topic %s)",
                    existing_reflection["title"],
                    topic_key,
                )
                r_id, _ = db.append_to_reflection(
                    reflection_id=existing_reflection["id"],
                    new_sections=reflection.get("sections", []),
                    new_content=reflection.get("content"),
                    additional_tags=tags,
                    source_file=filename,
                    transcript_id=transcript_id,
                )
                db_records["reflection_ids"].append(r_id)
                db_records["reflection_appended"] = True
            else:
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

        background_tasks.add_task(trigger_syncs_for_records, db_records)
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
            topic_key = reflection.get("topic_key")
            tags = reflection.get("tags", [])
            title = reflection.get("title", "")

            existing_reflection = None
            if topic_key:
                existing_reflection = db.find_similar_reflection(
                    topic_key=topic_key,
                    tags=tags,
                    title=title,
                )

            if existing_reflection:
                logger.info(
                    "Appending to reflection %s (topic %s)",
                    existing_reflection["title"],
                    topic_key,
                )
                r_id, _ = db.append_to_reflection(
                    reflection_id=existing_reflection["id"],
                    new_sections=reflection.get("sections", []),
                    new_content=reflection.get("content"),
                    additional_tags=tags,
                    source_file=request.filename,
                    transcript_id=transcript_id,
                )
                db_records["reflection_ids"].append(r_id)
                db_records["reflection_appended"] = True
            else:
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

        background_tasks.add_task(trigger_syncs_for_records, db_records)
        logger.info("Scheduled sync triggers for new transcript %s", transcript_id)

        return AnalysisResponse(status="success", analysis=analysis, db_records=db_records)

    except Exception as exc:
        logger.exception("Failed to analyze transcript %s", request.filename)
        raise HTTPException(status_code=500, detail=str(exc))
