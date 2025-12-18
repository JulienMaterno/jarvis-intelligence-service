from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.api.models import TranscriptRequest, TranscriptProcessRequest, AnalysisResponse
from app.services.llm import ClaudeMultiAnalyzer
from app.services.database import SupabaseMultiDatabase
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
            "task_ids": []
        }
        
        primary_category = analysis.get("primary_category", "other")
        
        # Process Meetings
        for meeting in analysis.get("meetings", []):
            m_id, m_url = db.create_meeting(
                meeting_data=meeting,
                transcript=transcript_text,
                duration=transcript_record.get("audio_duration_seconds", 0),
                filename=filename,
                transcript_id=transcript_id
            )
            db_records["meeting_ids"].append(m_id)
            
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
            "task_ids": []
        }
        
        primary_category = analysis.get("primary_category", "other")
        
        # Process Meetings
        for meeting in analysis.get("meetings", []):
            m_id, m_url = db.create_meeting(
                meeting_data=meeting,
                transcript=request.transcript,
                duration=request.audio_duration_seconds or 0,
                filename=request.filename,
                transcript_id=transcript_id
            )
            db_records["meeting_ids"].append(m_id)
            
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
        
        return AnalysisResponse(
            status="success",
            analysis=analysis,
            db_records=db_records
        )

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
