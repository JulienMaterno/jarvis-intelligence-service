from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.api.models import TranscriptRequest, TranscriptProcessRequest, AnalysisResponse, LinkContactRequest, CreateContactRequest
from app.services.llm import ClaudeMultiAnalyzer
from app.services.database import SupabaseMultiDatabase
from app.services.sync_trigger import trigger_syncs_for_records
import logging

router = APIRouter()
logger = logging.getLogger('Jarvis.Intelligence.API')

# Initialize services
# Note: In a real production app, we might want to use dependency injection
analyzer = ClaudeMultiAnalyzer()
db = SupabaseMultiDatabase()

@router.post("/process/{transcript_id}", response_model=AnalysisResponse)
async def process_transcript(transcript_id: str, background_tasks: BackgroundTasks):
    """
    Process an existing transcript (by ID) and save results to the database.
    """
    try:
        logger.info(f"Received process request for transcript {transcript_id}")
        
        # 1. Fetch transcript from DB
        transcript_record = db.get_transcript(transcript_id)
        if not transcript_record:
            raise HTTPException(status_code=404, detail=f"Transcript {transcript_id} not found")
            
        transcript_text = transcript_record.get("full_text", "")
        filename = transcript_record.get("source_file", "unknown")
        # Try to get date from metadata or use today
        recording_date = None # Logic to extract date if needed, or let analyzer default to today
        
        # 2. Run Claude Analysis
        analysis = analyzer.analyze_transcript(
            transcript=transcript_text,
            filename=filename,
            recording_date=recording_date
        )
        
        # 3. Save structured data to Supabase
        db_records = {
            "transcript_id": transcript_id,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
            "contact_matches": []  # Track CRM linking results
        }
        
        primary_category = analysis.get("primary_category", "other")
        
        # Process Journals (daily entries)
        for journal in analysis.get("journals", []):
            j_id, j_url = db.create_journal(
                journal_data=journal,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
                transcript_id=transcript_id
            )
            db_records["journal_ids"].append(j_id)
            
            # Create tasks from analysis.tasks if present
            if primary_category == "journal" and analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=j_id,
                    origin_type="journal"
                )
                db_records["task_ids"].extend(task_ids)
            
            # Also create tasks from tomorrow_focus items in the journal
            tomorrow_focus = journal.get("tomorrow_focus", [])
            if tomorrow_focus:
                # Convert tomorrow_focus strings to task objects
                focus_tasks = [
                    {"title": item, "description": "From journal tomorrow_focus", "due_date": None}
                    for item in tomorrow_focus
                    if isinstance(item, str) and len(item) > 3
                ]
                if focus_tasks:
                    task_ids = db.create_tasks(
                        tasks_data=focus_tasks,
                        origin_id=j_id,
                        origin_type="journal"
                    )
                    db_records["task_ids"].extend(task_ids)
                    logger.info(f"Created {len(task_ids)} tasks from journal tomorrow_focus")
        
        # Process Meetings
        for meeting in analysis.get("meetings", []):
            m_id, m_url, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
                transcript_id=transcript_id
            )
            db_records["meeting_ids"].append(m_id)
            
            # Add contact match info with meeting context
            if contact_match_info.get("searched_name"):
                contact_match_info["meeting_id"] = m_id
                contact_match_info["meeting_title"] = meeting.get("title", "Untitled")
                db_records["contact_matches"].append(contact_match_info)
            
            # Create tasks linked to this meeting
            if analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=m_id,
                    origin_type="meeting"
                )
                db_records["task_ids"].extend(task_ids)

        # Process Reflections - with smart topic merging
        for reflection in analysis.get("reflections", []):
            topic_key = reflection.get('topic_key')
            tags = reflection.get('tags', [])
            title = reflection.get('title', '')
            
            # Check if we should append to an existing reflection
            existing_reflection = None
            if topic_key:
                existing_reflection = db.find_similar_reflection(
                    topic_key=topic_key,
                    tags=tags,
                    title=title
                )
            
            if existing_reflection:
                # Append to existing reflection
                logger.info(f"Appending to existing reflection: {existing_reflection['title']} (topic: {topic_key})")
                r_id, r_url = db.append_to_reflection(
                    reflection_id=existing_reflection['id'],
                    new_sections=reflection.get('sections', []),
                    new_content=reflection.get('content'),
                    additional_tags=tags,
                    source_file=filename,
                    transcript_id=transcript_id
                )
                db_records["reflection_ids"].append(r_id)
                db_records["reflection_appended"] = True
            else:
                # Create new reflection
                r_id, r_url = db.create_reflection(
                    reflection_data=reflection,
                    transcript=transcript_text,
                    duration=transcript_record.get("audio_duration_seconds", 0),
                    filename=filename,
                    transcript_id=transcript_id
                )
                db_records["reflection_ids"].append(r_id)
            
            # Create tasks linked to this reflection
            if primary_category == "reflection" and analysis.get("tasks") and not db_records["meeting_ids"]:
                 task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=r_id,
                    origin_type="reflection"
                )
                 db_records["task_ids"].extend(task_ids)

        # Trigger syncs in background to push new data to Notion
        background_tasks.add_task(trigger_syncs_for_records, db_records)
        logger.info(f"Scheduled sync triggers for created records")

        return AnalysisResponse(
            status="success",
            analysis=analysis,
            db_records=db_records
        )

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_transcript(request: TranscriptRequest, background_tasks: BackgroundTasks):
    """
    Analyze a transcript and save results to the database.
    """
    try:
        logger.info(f"Received analysis request for {request.filename}")
        
        # 1. Save raw transcript first (so we have it even if analysis fails)
        transcript_id = db.create_transcript(
            source_file=request.filename,
            full_text=request.transcript,
            audio_duration_seconds=request.audio_duration_seconds,
            language=request.language
        )
        
        # 2. Run Claude Analysis
        analysis = analyzer.analyze_transcript(
            transcript=request.transcript,
            filename=request.filename,
            recording_date=request.recording_date
        )
        
        # 3. Save structured data to Supabase
        # We can do this in background if we want faster response, 
        # but for now let's do it synchronously to return the IDs
        
        db_records = {
            "transcript_id": transcript_id,
            "meeting_ids": [],
            "reflection_ids": [],
            "journal_ids": [],
            "task_ids": [],
            "contact_matches": []  # Track CRM linking results
        }
        
        primary_category = analysis.get("primary_category", "other")
        
        # Process Journals (daily entries)
        for journal in analysis.get("journals", []):
            j_id, j_url = db.create_journal(
                journal_data=journal,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id
            )
            db_records["journal_ids"].append(j_id)
            
            # Create tasks linked to this journal
            if primary_category == "journal" and analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=j_id,
                    origin_type="journal"
                )
                db_records["task_ids"].extend(task_ids)
            
            # Also create tasks from tomorrow_focus items in the journal
            tomorrow_focus = journal.get("tomorrow_focus", [])
            if tomorrow_focus:
                # Convert tomorrow_focus strings to task objects
                focus_tasks = [
                    {"title": item, "description": "From journal tomorrow_focus", "due_date": None}
                    for item in tomorrow_focus
                    if isinstance(item, str) and len(item) > 3
                ]
                if focus_tasks:
                    task_ids = db.create_tasks(
                        tasks_data=focus_tasks,
                        origin_id=j_id,
                        origin_type="journal"
                    )
                    db_records["task_ids"].extend(task_ids)
                    logger.info(f"Created {len(task_ids)} tasks from journal tomorrow_focus")
        
        # Process Meetings
        for meeting in analysis.get("meetings", []):
            m_id, m_url, contact_match_info = db.create_meeting(
                meeting_data=meeting,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id
            )
            db_records["meeting_ids"].append(m_id)
            
            # Add contact match info with meeting context
            if contact_match_info.get("searched_name"):
                contact_match_info["meeting_id"] = m_id
                contact_match_info["meeting_title"] = meeting.get("title", "Untitled")
                db_records["contact_matches"].append(contact_match_info)
            
            # Create tasks linked to this meeting
            if analysis.get("tasks"):
                task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=m_id,
                    origin_type="meeting"
                )
                db_records["task_ids"].extend(task_ids)

        # Process Reflections
        for reflection in analysis.get("reflections", []):
            r_id, r_url = db.create_reflection(
                reflection_data=reflection,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id
            )
            db_records["reflection_ids"].append(r_id)
            
            # Create tasks linked to this reflection
            # (If primary category is reflection, tasks likely belong to it)
            if primary_category == "reflection" and analysis.get("tasks") and not db_records["meeting_ids"]:
                 task_ids = db.create_tasks(
                    tasks_data=analysis.get("tasks"),
                    origin_id=r_id,
                    origin_type="reflection"
                )
                 db_records["task_ids"].extend(task_ids)

        # If we have tasks but no meeting/reflection created (e.g. task_planning category),
        # we might want to create a generic "Task Planning" entry or just attach to transcript.
        # For now, the logic above covers most cases.
        
        # Trigger syncs in background to push new data to Notion
        background_tasks.add_task(trigger_syncs_for_records, db_records)
        logger.info(f"Scheduled sync triggers for created records")

        return AnalysisResponse(
            status="success",
            analysis=analysis,
            db_records=db_records
        )

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# CONTACT MANAGEMENT ENDPOINTS
# =========================================================================

@router.patch("/meetings/{meeting_id}/link-contact")
async def link_contact_to_meeting(meeting_id: str, request: LinkContactRequest):
    """
    Link a contact to an existing meeting.
    Used when user selects correct contact from suggestions.
    """
    try:
        logger.info(f"Linking meeting {meeting_id} to contact {request.contact_id}")
        
        # Update the meeting with the contact_id
        result = db.client.table("meetings").update({
            "contact_id": request.contact_id
        }).eq("id", meeting_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
        
        # Get the contact details for confirmation
        contact = db.client.table("contacts").select("first_name, last_name, company").eq("id", request.contact_id).single().execute()
        
        contact_name = f"{contact.data.get('first_name', '')} {contact.data.get('last_name', '')}".strip()
        company = contact.data.get('company', '')
        
        logger.info(f"Meeting {meeting_id} linked to {contact_name}")
        
        return {
            "status": "success",
            "meeting_id": meeting_id,
            "contact_id": request.contact_id,
            "contact_name": contact_name,
            "company": company
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/contacts")
async def create_contact(request: CreateContactRequest):
    """
    Create a new contact in the CRM.
    Optionally link to a meeting after creation.
    """
    try:
        logger.info(f"Creating contact: {request.first_name} {request.last_name or ''}")
        
        payload = {
            "first_name": request.first_name,
            "last_name": request.last_name,
            "company": request.company,
            "position": request.position,
            "email": request.email,
            "phone": request.phone,
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        result = db.client.table("contacts").insert(payload).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create contact")
        
        contact_id = result.data[0]["id"]
        contact_name = f"{request.first_name} {request.last_name or ''}".strip()
        
        logger.info(f"Contact created: {contact_id}")
        
        # Optionally link to meeting
        if request.link_to_meeting_id:
            db.client.table("meetings").update({
                "contact_id": contact_id
            }).eq("id", request.link_to_meeting_id).execute()
            logger.info(f"Linked new contact to meeting {request.link_to_meeting_id}")
        
        return {
            "status": "success",
            "contact_id": contact_id,
            "contact_name": contact_name,
            "linked_to_meeting": request.link_to_meeting_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/search")
async def search_contacts(q: str, limit: int = 5):
    """
    Search contacts by name.
    """
    try:
        if not q or len(q) < 2:
            return {"contacts": []}
        
        result = db.client.table("contacts").select(
            "id, first_name, last_name, company, position"
        ).or_(
            f"first_name.ilike.%{q}%,last_name.ilike.%{q}%"
        ).is_("deleted_at", "null").limit(limit).execute()
        
        contacts = [
            {
                "id": c.get("id"),
                "name": f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
                "company": c.get("company"),
                "position": c.get("position")
            }
            for c in result.data
        ]
        
        return {"contacts": contacts}
        
    except Exception as e:
        logger.error(f"Error searching contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    return {"status": "healthy"}
