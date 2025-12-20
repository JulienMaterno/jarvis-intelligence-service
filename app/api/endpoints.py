from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.api.models import (
    TranscriptRequest, TranscriptProcessRequest, AnalysisResponse, 
    LinkContactRequest, CreateContactRequest,
    CreateEmailRequest, EmailResponse, LinkEmailRequest,
    CreateCalendarEventRequest, CalendarEventResponse, LinkCalendarEventRequest,
    ContactInteractionsResponse, ContactSummaryResponse,
    JournalPromptRequest, JournalPromptResponse
)
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
                    source_file=request.filename,
                    transcript_id=transcript_id
                )
                db_records["reflection_ids"].append(r_id)
                db_records["reflection_appended"] = True
            else:
                # Create new reflection
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


# =========================================================================
# EMAIL ENDPOINTS
# =========================================================================

@router.post("/emails")
async def create_email(request: CreateEmailRequest):
    """
    Create a new email record and link to contacts/meetings.
    """
    try:
        logger.info(f"Creating email: {request.subject}")
        
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
            raw_data=request.raw_data
        )
        
        # Get linked contact info
        contact_info = None
        if request.contact_id:
            try:
                contact = db.client.table("contacts").select("first_name, last_name").eq("id", request.contact_id).single().execute()
                if contact.data:
                    contact_name = f"{contact.data.get('first_name', '')} {contact.data.get('last_name', '')}".strip()
                    contact_info = {"id": request.contact_id, "name": contact_name}
            except Exception as e:
                logger.warning(f"Could not fetch contact {request.contact_id}: {e}")
        
        return EmailResponse(
            status="success",
            email_id=email_id,
            email_url=email_url,
            contact_id=request.contact_id,
            contact_name=contact_info["name"] if contact_info else None
        )
        
    except Exception as e:
        logger.error(f"Error creating email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/emails/{email_id}/link")
async def link_email(email_id: str, request: LinkEmailRequest):
    """
    Link an email to a meeting or contact.
    """
    try:
        logger.info(f"Linking email {email_id}")
        
        update_data = {}
        if request.meeting_id:
            db.link_email_to_meeting(email_id, request.meeting_id)
            update_data["meeting_id"] = request.meeting_id
        
        if request.contact_id:
            db.client.table("emails").update({
                "contact_id": request.contact_id
            }).eq("id", email_id).execute()
            update_data["contact_id"] = request.contact_id
        
        return {
            "status": "success",
            "email_id": email_id,
            **update_data
        }
        
    except Exception as e:
        logger.error(f"Error linking email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emails/thread/{thread_id}")
async def get_email_thread(thread_id: str):
    """
    Get all emails in a conversation thread.
    """
    try:
        emails = db.get_emails_by_thread(thread_id)
        return {
            "status": "success",
            "thread_id": thread_id,
            "email_count": len(emails),
            "emails": emails
        }
    except Exception as e:
        logger.error(f"Error fetching email thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# CALENDAR EVENT ENDPOINTS
# =========================================================================

@router.post("/calendar-events")
async def create_calendar_event(request: CreateCalendarEventRequest):
    """
    Create a new calendar event and link to contacts/meetings.
    """
    try:
        logger.info(f"Creating calendar event: {request.title}")
        
        event_id, event_url = db.create_calendar_event(
            title=request.title,
            start_time=request.start_time,
            end_time=request.end_time,
            description=request.description,
            location=request.location,
            organizer_email=request.organizer_email,
            organizer_name=request.organizer_name,
            attendees=request.attendees,
            all_day=request.all_day,
            status=request.status,
            contact_id=request.contact_id,
            contact_name=request.contact_name,
            meeting_id=request.meeting_id,
            email_id=request.email_id,
            event_type=request.event_type,
            tags=request.tags,
            meeting_url=request.meeting_url,
            is_recurring=request.is_recurring,
            recurrence_rule=request.recurrence_rule,
            source_provider=request.source_provider,
            source_event_id=request.source_event_id,
            raw_data=request.raw_data
        )
        
        # Get linked contact info
        contact_info = None
        if request.contact_id:
            try:
                contact = db.client.table("contacts").select("first_name, last_name").eq("id", request.contact_id).single().execute()
                if contact.data:
                    contact_name = f"{contact.data.get('first_name', '')} {contact.data.get('last_name', '')}".strip()
                    contact_info = {"id": request.contact_id, "name": contact_name}
            except Exception as e:
                logger.warning(f"Could not fetch contact {request.contact_id}: {e}")
        
        return CalendarEventResponse(
            status="success",
            event_id=event_id,
            event_url=event_url,
            contact_id=request.contact_id,
            contact_name=contact_info["name"] if contact_info else None
        )
        
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/calendar-events/{event_id}/link")
async def link_calendar_event(event_id: str, request: LinkCalendarEventRequest):
    """
    Link a calendar event to a meeting or contact.
    """
    try:
        logger.info(f"Linking calendar event {event_id}")
        
        update_data = {}
        if request.meeting_id:
            db.link_calendar_event_to_meeting(event_id, request.meeting_id)
            update_data["meeting_id"] = request.meeting_id
        
        if request.contact_id:
            db.client.table("calendar_events").update({
                "contact_id": request.contact_id
            }).eq("id", event_id).execute()
            update_data["contact_id"] = request.contact_id
        
        return {
            "status": "success",
            "event_id": event_id,
            **update_data
        }
        
    except Exception as e:
        logger.error(f"Error linking calendar event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendar-events/upcoming")
async def get_upcoming_events(limit: int = 20):
    """
    Get upcoming calendar events.
    """
    try:
        events = db.get_upcoming_events(limit=limit)
        return {
            "status": "success",
            "event_count": len(events),
            "events": events
        }
    except Exception as e:
        logger.error(f"Error fetching upcoming events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# CONTACT INTERACTION ENDPOINTS
# =========================================================================

@router.get("/contacts/{contact_id}/interactions")
async def get_contact_interactions(contact_id: str, limit: int = 50):
    """
    Get all interactions (meetings, emails, calendar events) for a contact.
    """
    try:
        interactions = db.get_contact_interactions(contact_id, limit=limit)
        
        # Count by type
        counts = {
            "meeting": 0,
            "email": 0,
            "calendar_event": 0,
            "total": len(interactions)
        }
        for interaction in interactions:
            interaction_type = interaction.get("interaction_type")
            if interaction_type in counts:
                counts[interaction_type] += 1
        
        # Get contact info
        try:
            contact = db.client.table("contacts").select("first_name, last_name, email, company").eq("id", contact_id).single().execute()
            if not contact.data:
                raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
            contact_name = f"{contact.data.get('first_name', '')} {contact.data.get('last_name', '')}".strip()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching contact {contact_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
        return ContactInteractionsResponse(
            status="success",
            contact_id=contact_id,
            contact_name=contact_name,
            total_interactions=counts["total"],
            interactions=interactions,
            summary=counts
        )
        
    except Exception as e:
        logger.error(f"Error fetching contact interactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contacts/{contact_id}/summary")
async def get_contact_summary(contact_id: str):
    """
    Get comprehensive summary of a contact with all interactions and stats.
    """
    try:
        # Get contact details
        contact = db.client.table("contacts").select("*").eq("id", contact_id).single().execute()
        if not contact.data:
            raise HTTPException(status_code=404, detail=f"Contact {contact_id} not found")
        contact_data = contact.data
        
        # Get recent interactions
        interactions = db.get_contact_interactions(contact_id, limit=10)
        
        # Get upcoming events
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        upcoming = db.client.table("calendar_events").select("*").eq(
            "contact_id", contact_id
        ).gte("start_time", now).is_("deleted_at", "null").limit(5).execute()
        
        # Count interactions by type
        all_interactions = db.get_contact_interactions(contact_id, limit=1000)
        counts = {
            "meetings": sum(1 for i in all_interactions if i.get("interaction_type") == "meeting"),
            "emails": sum(1 for i in all_interactions if i.get("interaction_type") == "email"),
            "calendar_events": sum(1 for i in all_interactions if i.get("interaction_type") == "calendar_event"),
        }
        
        return ContactSummaryResponse(
            status="success",
            contact=contact_data,
            interaction_counts=counts,
            recent_interactions=interactions,
            upcoming_events=upcoming.data
        )
        
    except Exception as e:
        logger.error(f"Error fetching contact summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


# =========================================================================
# EVENING JOURNAL PROMPT GENERATION
# =========================================================================

@router.post("/journal/evening-prompt")
async def generate_evening_journal_prompt(request: JournalPromptRequest):
    """
    Generate an AI-powered evening journal prompt based on the day's activities.
    
    The AI analyzes meetings, emails, calendar events, tasks etc. and:
    1. Extracts the most meaningful highlights
    2. Generates personalized reflection prompts
    3. Creates a formatted message for Telegram
    """
    from datetime import datetime
    
    try:
        logger.info("Generating AI evening journal prompt")
        
        activity_data = request.activity_data
        
        # Build context for Claude
        context_parts = []
        people_mentioned = set()
        
        # Meetings
        if activity_data.meetings:
            meeting_summaries = []
            for m in activity_data.meetings:
                title = m.get("title", "Untitled")
                summary = m.get("summary", "")[:200] if m.get("summary") else ""
                meeting_summaries.append(f"- {title}: {summary}")
                if m.get("people_mentioned"):
                    people_mentioned.update(m["people_mentioned"])
            context_parts.append(f"MEETINGS ({len(activity_data.meetings)}):\n" + "\n".join(meeting_summaries))
        
        # Calendar events
        if activity_data.calendar_events:
            event_summaries = []
            for e in activity_data.calendar_events:
                title = e.get("summary") or e.get("title", "Untitled")
                event_summaries.append(f"- {title}")
                if e.get("attendees"):
                    for att in e["attendees"]:
                        if att.get("displayName"):
                            people_mentioned.add(att["displayName"])
            context_parts.append(f"CALENDAR EVENTS ({len(activity_data.calendar_events)}):\n" + "\n".join(event_summaries))
        
        # Emails (filter out noise)
        if activity_data.emails:
            skip_keywords = ["unsubscribe", "newsletter", "automated", "noreply", "no-reply", "github", "notification"]
            meaningful_emails = []
            for e in activity_data.emails:
                subject = e.get("subject", "")
                if not any(kw in subject.lower() for kw in skip_keywords):
                    sender = e.get("sender", "")
                    meaningful_emails.append(f"- {subject} (from: {sender})")
                    if e.get("contact_name"):
                        people_mentioned.add(e["contact_name"])
            if meaningful_emails:
                context_parts.append(f"EMAILS ({len(meaningful_emails)} meaningful):\n" + "\n".join(meaningful_emails[:10]))
        
        # Tasks completed
        if activity_data.tasks_completed:
            task_titles = [t.get("title", "Task") for t in activity_data.tasks_completed]
            context_parts.append(f"TASKS COMPLETED ({len(task_titles)}):\n- " + "\n- ".join(task_titles))
        
        # Tasks created
        if activity_data.tasks_created:
            task_titles = [t.get("title", "Task") for t in activity_data.tasks_created]
            context_parts.append(f"NEW TASKS ({len(task_titles)}):\n- " + "\n- ".join(task_titles))
        
        # Reflections recorded
        if activity_data.reflections:
            reflection_titles = [r.get("title", "Reflection") for r in activity_data.reflections]
            context_parts.append(f"REFLECTIONS RECORDED ({len(reflection_titles)}):\n- " + "\n- ".join(reflection_titles))
        
        # Journals
        if activity_data.journals:
            for j in activity_data.journals:
                if j.get("highlights"):
                    context_parts.append(f"JOURNAL HIGHLIGHTS: {', '.join(j['highlights'][:5])}")
        
        full_context = "\n\n".join(context_parts) if context_parts else "No significant activities recorded today."
        
        # Call Claude for analysis
        prompt = f"""You are a thoughtful personal assistant helping someone reflect on their day for journaling.

TODAY'S ACTIVITIES:
{full_context}

PEOPLE INTERACTED WITH: {', '.join(list(people_mentioned)[:10]) if people_mentioned else 'None recorded'}

Based on this day's activities, generate:

1. HIGHLIGHTS (2-4 bullet points): The most meaningful or interesting moments from today. Be specific and insightful, not generic. If there were meetings, mention what they might have been about. If tasks were completed, acknowledge the accomplishment. Focus on substance, not just listing things.

2. REFLECTION_PROMPTS (2-3 questions): Personalized questions that would help this person reflect meaningfully on TODAY specifically. Reference actual events/people from the day. Avoid generic questions like "what are you grateful for" - instead ask about specific things from the day.

3. PEOPLE_SUMMARY (1 sentence, optional): If they interacted with notable people today, a brief note about it.

Respond in JSON format:
{{
    "highlights": ["highlight 1", "highlight 2", ...],
    "reflection_prompts": ["question 1?", "question 2?", ...],
    "people_summary": "sentence about people or null"
}}

Be warm but concise. Skip the fluff."""

        import anthropic
        import json
        import os
        
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        response_text = response.content[0].text
        
        # Extract JSON from response
        try:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse Claude response as JSON: {response_text}")
            analysis = {
                "highlights": ["Reflect on your day's activities"],
                "reflection_prompts": ["What stood out to you today?"],
                "people_summary": None
            }
        
        highlights = analysis.get("highlights", [])
        prompts = analysis.get("reflection_prompts", [])
        people_summary = analysis.get("people_summary")
        
        # Build formatted message
        now = datetime.utcnow()
        message = f"""📓 **Evening Journal**

🕐 _{now.strftime('%A, %B %d')}_

"""
        
        if highlights:
            message += "**Today's highlights:**\n"
            for h in highlights:
                message += f"• {h}\n"
            message += "\n"
        
        if people_summary:
            message += f"👥 {people_summary}\n\n"
        
        if prompts:
            message += "**Things to reflect on:**\n"
            for p in prompts:
                message += f"• {p}\n"
            message += "\n"
        
        message += "_Reply with a voice note or text to journal_ 🎙️"
        
        return JournalPromptResponse(
            status="success",
            highlights=highlights,
            reflection_prompts=prompts,
            people_summary=people_summary,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Error generating evening journal prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
