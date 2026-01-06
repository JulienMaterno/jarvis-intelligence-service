"""
Memory API Routes

Provides endpoints for:
- Viewing all memories
- Adding new memories manually
- Correcting/updating existing memories
- Deleting memories
- Searching memories
- Bulk seeding from existing data
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.api.dependencies import get_memory, get_database
from app.features.memory import MemoryType

router = APIRouter(tags=["Memory"])
logger = logging.getLogger("Jarvis.Intelligence.API.Memory")


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class MemoryItem(BaseModel):
    """A single memory item."""
    id: str
    memory: str
    type: Optional[str] = "fact"
    metadata: Optional[dict] = None
    created_at: Optional[str] = None


class AddMemoryRequest(BaseModel):
    """Request to add a new memory."""
    content: str = Field(..., description="The memory content in natural language")
    memory_type: str = Field(
        default="fact",
        description="Type: fact, interaction, insight, preference, relationship"
    )
    metadata: Optional[dict] = Field(default=None, description="Optional metadata")
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "content": "My GitHub profile is github.com/aaron",
                    "memory_type": "fact"
                },
                {
                    "content": "I was employee #1 at Algenie, not #3",
                    "memory_type": "fact"
                },
                {
                    "content": "I prefer meetings in the morning before 11am",
                    "memory_type": "preference"
                }
            ]
        }


class CorrectMemoryRequest(BaseModel):
    """Request to correct/update an existing memory."""
    memory_id: str = Field(..., description="ID of the memory to correct")
    new_content: str = Field(..., description="The corrected memory content")
    
    class Config:
        json_schema_extra = {
            "example": {
                "memory_id": "mem_abc123",
                "new_content": "I was employee #1 at Algenie (founding team)"
            }
        }


class SearchMemoryRequest(BaseModel):
    """Request to search memories."""
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(default=10, ge=1, le=50)
    memory_type: Optional[str] = Field(default=None, description="Filter by type")


class MemoryResponse(BaseModel):
    """Response with memory details."""
    status: str
    memory_id: Optional[str] = None
    message: Optional[str] = None


class MemoryListResponse(BaseModel):
    """Response with list of memories."""
    status: str
    count: int
    memories: List[MemoryItem]


class SeedingStatusResponse(BaseModel):
    """Response for seeding operations."""
    status: str
    memories_added: int
    source: str
    details: Optional[dict] = None


# ============================================================================
# MEMORY ENDPOINTS
# ============================================================================

@router.get("/memory", response_model=MemoryListResponse)
async def list_memories(
    limit: int = 50,
    memory_type: Optional[str] = None
):
    """
    List all memories.
    
    Args:
        limit: Maximum memories to return (default 50)
        memory_type: Filter by type (fact, interaction, preference, relationship, insight)
    
    Returns:
        List of all stored memories
    """
    memory_service = get_memory()
    
    try:
        memories = await memory_service.get_all(limit=limit)
        
        # Filter by type if specified
        if memory_type:
            memories = [
                m for m in memories 
                if m.get("metadata", {}).get("type") == memory_type
            ]
        
        # Format for response
        items = []
        for mem in memories:
            items.append(MemoryItem(
                id=mem.get("id", ""),
                memory=mem.get("memory", mem.get("content", "")),
                type=mem.get("metadata", {}).get("type", "fact"),
                metadata=mem.get("metadata"),
                created_at=mem.get("metadata", {}).get("added_at"),
            ))
        
        return MemoryListResponse(
            status="success",
            count=len(items),
            memories=items
        )
        
    except Exception as e:
        logger.exception("Failed to list memories")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory", response_model=MemoryResponse)
async def add_memory(request: AddMemoryRequest):
    """
    Add a new memory manually.
    
    Use this to tell Jarvis things to remember:
    - Personal facts: "My GitHub is github.com/yourname"
    - Preferences: "I prefer video calls over phone calls"
    - Relationships: "John Smith is my co-founder at Algenie"
    
    The memory will be automatically retrieved in future conversations
    when relevant.
    """
    memory_service = get_memory()
    
    try:
        # Map string type to enum
        type_mapping = {
            "fact": MemoryType.FACT,
            "interaction": MemoryType.INTERACTION,
            "insight": MemoryType.INSIGHT,
            "preference": MemoryType.PREFERENCE,
            "relationship": MemoryType.RELATIONSHIP,
        }
        mem_type = type_mapping.get(request.memory_type.lower(), MemoryType.FACT)
        
        memory_id = await memory_service.add(
            content=request.content,
            memory_type=mem_type,
            metadata=request.metadata,
        )
        
        if memory_id:
            logger.info(f"Added manual memory: {request.content[:50]}...")
            return MemoryResponse(
                status="success",
                memory_id=memory_id,
                message=f"Memory added: {request.content[:100]}"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to add memory")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to add memory")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/correct", response_model=MemoryResponse)
async def correct_memory(request: CorrectMemoryRequest):
    """
    Correct an existing memory using Mem0's native update.
    
    Use this when Jarvis remembers something incorrectly:
    - First find the memory using GET /memory or POST /memory/search
    - Then provide the memory_id and the corrected content
    
    The memory will be updated in place, preserving history.
    """
    memory_service = get_memory()
    
    try:
        # Use Mem0's native update for proper versioning
        updated = await memory_service.update(
            memory_id=request.memory_id,
            new_content=request.new_content
        )
        
        if not updated:
            raise HTTPException(
                status_code=404, 
                detail=f"Memory {request.memory_id} not found"
            )
        
        logger.info(f"Corrected memory {request.memory_id}")
        
        return MemoryResponse(
            status="success",
            memory_id=request.memory_id,
            message=f"Memory corrected: {request.new_content[:100]}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to correct memory")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/{memory_id}", response_model=MemoryResponse)
async def delete_memory(memory_id: str):
    """
    Delete a specific memory.
    
    Use this to remove incorrect or outdated memories.
    """
    memory_service = get_memory()
    
    try:
        deleted = await memory_service.delete(memory_id)
        
        if deleted:
            return MemoryResponse(
                status="success",
                memory_id=memory_id,
                message="Memory deleted"
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Memory {memory_id} not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete memory {memory_id}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple memories."""
    memory_ids: List[str] = Field(..., description="List of memory IDs to delete")


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete operation."""
    status: str
    deleted_count: int
    failed_count: int
    failed_ids: List[str] = []


@router.post("/memory/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_memories(request: BulkDeleteRequest):
    """
    Delete multiple memories at once.
    
    Use this for cleanup after reviewing memories:
    1. GET /memory to list all memories
    2. Identify IDs of memories to delete
    3. POST /memory/bulk-delete with the list of IDs
    """
    memory_service = get_memory()
    
    deleted_count = 0
    failed_count = 0
    failed_ids = []
    
    for memory_id in request.memory_ids:
        try:
            deleted = await memory_service.delete(memory_id)
            if deleted:
                deleted_count += 1
            else:
                failed_count += 1
                failed_ids.append(memory_id)
        except Exception as e:
            logger.warning(f"Failed to delete memory {memory_id}: {e}")
            failed_count += 1
            failed_ids.append(memory_id)
    
    logger.info(f"Bulk delete: {deleted_count} deleted, {failed_count} failed")
    
    return BulkDeleteResponse(
        status="success" if failed_count == 0 else "partial",
        deleted_count=deleted_count,
        failed_count=failed_count,
        failed_ids=failed_ids
    )


@router.delete("/memory/all", response_model=MemoryResponse)
async def delete_all_memories(confirm: str = ""):
    """
    Delete ALL memories. Use with caution!
    
    Requires confirmation query param: ?confirm=yes-delete-all
    """
    if confirm != "yes-delete-all":
        raise HTTPException(
            status_code=400,
            detail="Must provide ?confirm=yes-delete-all to confirm deletion of all memories"
        )
    
    memory_service = get_memory()
    
    try:
        # Get all memories and delete each
        memories = await memory_service.get_all(limit=1000)
        deleted_count = 0
        
        for mem in memories:
            mem_id = mem.get("id")
            if mem_id:
                await memory_service.delete(mem_id)
                deleted_count += 1
        
        logger.warning(f"Deleted ALL {deleted_count} memories")
        
        return MemoryResponse(
            status="success",
            message=f"Deleted all {deleted_count} memories"
        )
        
    except Exception as e:
        logger.exception("Failed to delete all memories")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/search", response_model=MemoryListResponse)
async def search_memories(request: SearchMemoryRequest):
    """
    Search memories semantically.
    
    Use natural language to find relevant memories:
    - "Algenie" - Find all memories about Algenie
    - "food preferences" - Find dietary preferences
    - "John Smith" - Find memories about a specific person
    """
    memory_service = get_memory()
    
    try:
        # Map type string to enum if provided
        mem_type = None
        if request.memory_type:
            type_mapping = {
                "fact": MemoryType.FACT,
                "interaction": MemoryType.INTERACTION,
                "insight": MemoryType.INSIGHT,
                "preference": MemoryType.PREFERENCE,
                "relationship": MemoryType.RELATIONSHIP,
            }
            mem_type = type_mapping.get(request.memory_type.lower())
        
        memories = await memory_service.search(
            query=request.query,
            limit=request.limit,
            memory_type=mem_type,
        )
        
        # Format for response
        items = []
        for mem in memories:
            items.append(MemoryItem(
                id=mem.get("id", ""),
                memory=mem.get("memory", mem.get("content", "")),
                type=mem.get("metadata", {}).get("type", "fact"),
                metadata=mem.get("metadata"),
                created_at=mem.get("metadata", {}).get("added_at"),
            ))
        
        return MemoryListResponse(
            status="success",
            count=len(items),
            memories=items
        )
        
    except Exception as e:
        logger.exception("Failed to search memories")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MEMORY SEEDING ENDPOINTS
# ============================================================================

@router.post("/memory/seed/contacts", response_model=SeedingStatusResponse)
async def seed_from_contacts(
    background_tasks: BackgroundTasks,
    limit: int = 50
):
    """
    Seed memories from existing contacts.
    
    Extracts relationship information from contacts database:
    - Names and companies
    - Job titles and positions
    - Meaningful notes (filters out system IDs and garbage)
    
    Uses Mem0's automatic deduplication to prevent duplicates.
    Runs in background to avoid timeout.
    """
    memory_service = get_memory()
    db = get_database()
    
    try:
        # Fetch contacts
        result = db.client.table("contacts").select(
            "first_name, last_name, company, job_title, notes, linkedin_url"
        ).order(
            "updated_at", desc=True
        ).limit(limit).execute()
        
        contacts = result.data or []
        
        # Seed in background
        async def _seed():
            count = 0
            for contact in contacts:
                name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                
                # Skip contacts without meaningful names
                if not name or len(name) < 2:
                    continue
                
                # Build comprehensive relationship info
                job_title = contact.get("job_title", "")
                company = contact.get("company", "")
                
                if job_title and company:
                    info = f"{name} is {job_title} at {company}"
                    await memory_service.remember_relationship(info, name)
                    count += 1
                elif job_title:
                    info = f"{name} is {job_title}"
                    await memory_service.remember_relationship(info, name)
                    count += 1
                elif company:
                    info = f"{name} works at {company}"
                    await memory_service.remember_relationship(info, name)
                    count += 1
                
                # Only add notes if they're meaningful text
                notes = contact.get("notes", "")
                if notes and len(notes) > 10:
                    # Filter out system IDs and numeric-only notes
                    if not notes.isdigit() and not notes.strip().startswith("1") or len(notes) > 20:
                        # Also filter out notes that look like "Created from Beeper"
                        if "created from" not in notes.lower():
                            await memory_service.remember_relationship(
                                f"About {name}: {notes[:300]}",
                                name
                            )
                            count += 1
            
            logger.info(f"Seeded {count} memories from {len(contacts)} contacts")
        
        background_tasks.add_task(_seed)
        
        return SeedingStatusResponse(
            status="started",
            memories_added=0,  # Will be counted in background
            source="contacts",
            details={"contacts_found": len(contacts)}
        )
        
    except Exception as e:
        logger.exception("Failed to seed from contacts")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/seed/meetings", response_model=SeedingStatusResponse)
async def seed_from_meetings(
    background_tasks: BackgroundTasks,
    limit: int = 30,
    days_back: int = 90
):
    """
    Seed memories from meeting records.
    
    Extracts interaction history from meetings:
    - Meeting summaries with contacts
    - Topics discussed
    - Key takeaways
    
    Args:
        limit: Maximum meetings to process
        days_back: How far back to look (default 90 days)
    """
    memory_service = get_memory()
    db = get_database()
    
    try:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        
        # Fetch recent meetings with summaries
        result = db.client.table("meetings").select(
            "title, summary, contact_name, date, topics_discussed"
        ).gte(
            "date", cutoff
        ).not_.is_(
            "summary", "null"
        ).order(
            "date", desc=True
        ).limit(limit).execute()
        
        meetings = result.data or []
        
        async def _seed():
            count = 0
            for meeting in meetings:
                contact = meeting.get("contact_name", "")
                summary = meeting.get("summary", "")
                title = meeting.get("title", "")
                date = meeting.get("date", "")
                
                if summary and contact:
                    await memory_service.remember_interaction(
                        f"Meeting '{title}': {summary[:200]}",
                        contact_name=contact,
                        interaction_date=date,
                        source="meeting_seed"
                    )
                    count += 1
            
            logger.info(f"Seeded {count} memories from {len(meetings)} meetings")
        
        background_tasks.add_task(_seed)
        
        return SeedingStatusResponse(
            status="started",
            memories_added=0,
            source="meetings",
            details={"meetings_found": len(meetings), "days_back": days_back}
        )
        
    except Exception as e:
        logger.exception("Failed to seed from meetings")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/memory/seed/transcripts", response_model=SeedingStatusResponse)
async def seed_from_transcripts(
    background_tasks: BackgroundTasks,
    limit: int = 20,
    days_back: int = 60
):
    """
    Seed memories by analyzing existing transcripts.
    
    This is the richest source of memories - it re-analyzes transcripts
    using Claude to extract:
    - Personal facts mentioned
    - Preferences expressed
    - Relationship information
    - Key decisions and plans
    
    This is CPU/token intensive, so limit is lower by default.
    
    Args:
        limit: Maximum transcripts to process (default 20)
        days_back: How far back to look (default 60 days)
    """
    memory_service = get_memory()
    db = get_database()
    
    try:
        from datetime import timedelta
        from app.services.llm import ClaudeMultiAnalyzer
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        
        # Fetch transcripts with actual content
        result = db.client.table("transcripts").select(
            "id, full_text, source_file, created_at"
        ).gte(
            "created_at", cutoff
        ).not_.is_(
            "full_text", "null"
        ).order(
            "created_at", desc=True
        ).limit(limit).execute()
        
        transcripts = result.data or []
        
        async def _seed():
            llm = ClaudeMultiAnalyzer()
            total_count = 0
            
            for transcript in transcripts:
                text = transcript.get("full_text", "")
                source = transcript.get("source_file", "unknown")
                
                if not text or len(text) < 100:
                    continue
                
                try:
                    # Use the memory service's built-in method
                    count = await memory_service.seed_from_raw_transcript(
                        transcript_text=text,
                        source_file=source,
                        llm_client=llm
                    )
                    total_count += count
                            
                except Exception as e:
                    logger.warning(f"Failed to extract from transcript {source}: {e}")
                    continue
            
            logger.info(f"Seeded {total_count} memories from {len(transcripts)} transcripts")
        
        background_tasks.add_task(_seed)
        
        return SeedingStatusResponse(
            status="started",
            memories_added=0,
            source="transcripts",
            details={"transcripts_found": len(transcripts), "days_back": days_back}
        )
        
    except Exception as e:
        logger.exception("Failed to seed from transcripts")
        raise HTTPException(status_code=500, detail=str(e))


async def _extract_memories_from_text(llm, text: str) -> List[dict]:
    """
    Use Claude to extract memorable facts from transcript text.
    
    Returns list of {type, content} dicts.
    """
    prompt = f"""Analyze this transcript and extract key memorable facts about the speaker.

Focus on:
1. Personal facts (where they work, role, background, etc.)
2. Preferences (how they like to work, communication style, etc.)
3. Relationships (people mentioned, their roles, connections)
4. Goals and plans (what they want to achieve, timelines)
5. Important decisions or insights

Return a JSON array of memories to store. Each memory should be:
- Concise (one sentence)
- Written in third person ("User works at...", "User prefers...")
- Specific and actionable

Example output:
[
  {{"type": "fact", "content": "User is the co-founder and CEO of Algenie"}},
  {{"type": "preference", "content": "User prefers morning meetings before 11am"}},
  {{"type": "relationship", "content": "John Smith is User's co-founder at Algenie"}},
  {{"type": "insight", "content": "User is planning to raise Series A in Q2 2024"}}
]

Return ONLY the JSON array, no other text. Maximum 10 memories.

TRANSCRIPT:
{text[:4000]}
"""
    
    try:
        response = llm.client.messages.create(
            model="claude-3-5-haiku-20241022",  # Use fast model for bulk
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        result_text = response.content[0].text.strip()
        
        # Parse JSON
        import json
        if result_text.startswith("["):
            return json.loads(result_text)
        else:
            # Try to extract JSON from response
            start = result_text.find("[")
            end = result_text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(result_text[start:end])
        
        return []
        
    except Exception as e:
        logger.warning(f"Failed to extract memories: {e}")
        return []


@router.post("/memory/seed/all", response_model=SeedingStatusResponse)
async def seed_all_memories(
    background_tasks: BackgroundTasks,
    contacts_limit: int = 50,
    meetings_limit: int = 30,
    transcripts_limit: int = 20,
    days_back: int = 90
):
    """
    Comprehensive memory seeding from all sources.
    
    This is the recommended endpoint for initial memory setup.
    Seeds from:
    1. Contacts (relationships, companies, notes)
    2. Meetings (interaction history with summaries)
    3. Transcripts (rich extraction using Claude)
    
    Args:
        contacts_limit: Max contacts to process (default 50)
        meetings_limit: Max meetings to process (default 30)
        transcripts_limit: Max transcripts to process (default 20)
        days_back: How far back to look for meetings/transcripts
    
    Note: This is a background job. Check /memory/stats for results.
    """
    memory_service = get_memory()
    db = get_database()
    
    try:
        from datetime import timedelta
        from app.services.llm import ClaudeMultiAnalyzer
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        
        # Fetch all data upfront
        contacts_result = db.client.table("contacts").select(
            "first_name, last_name, company, job_title, notes, linkedin_url"
        ).order("updated_at", desc=True).limit(contacts_limit).execute()
        
        meetings_result = db.client.table("meetings").select(
            "title, summary, contact_name, date, topics_discussed"
        ).gte("date", cutoff).not_.is_("summary", "null").order(
            "date", desc=True
        ).limit(meetings_limit).execute()
        
        transcripts_result = db.client.table("transcripts").select(
            "id, full_text, source_file, created_at"
        ).gte("created_at", cutoff).not_.is_("full_text", "null").order(
            "created_at", desc=True
        ).limit(transcripts_limit).execute()
        
        contacts = contacts_result.data or []
        meetings = meetings_result.data or []
        transcripts = transcripts_result.data or []
        
        async def _seed_all():
            total = 0
            
            # 1. Seed from contacts
            for contact in contacts:
                name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                if not name:
                    continue
                
                parts = [name]
                if contact.get("job_title"):
                    parts.append(f"is {contact['job_title']}")
                if contact.get("company"):
                    parts.append(f"at {contact['company']}")
                
                if len(parts) > 1:
                    await memory_service.remember_relationship(" ".join(parts), name)
                    total += 1
                
                if contact.get("notes"):
                    await memory_service.remember_relationship(
                        f"About {name}: {contact['notes'][:300]}", name
                    )
                    total += 1
            
            logger.info(f"Seeded {total} memories from contacts")
            
            # 2. Seed from meetings
            meetings_count = 0
            for meeting in meetings:
                contact = meeting.get("contact_name", "")
                summary = meeting.get("summary", "")
                title = meeting.get("title", "")
                date = meeting.get("date", "")
                
                if summary and contact:
                    await memory_service.remember_interaction(
                        f"Meeting '{title}': {summary[:150]}",
                        contact_name=contact,
                        interaction_date=date,
                        source="initial_seed"
                    )
                    meetings_count += 1
            
            total += meetings_count
            logger.info(f"Seeded {meetings_count} memories from meetings")
            
            # 3. Seed from transcripts (most intensive)
            llm = ClaudeMultiAnalyzer()
            transcripts_count = 0
            
            for transcript in transcripts:
                text = transcript.get("full_text", "")
                source = transcript.get("source_file", "unknown")
                
                if text and len(text) >= 100:
                    count = await memory_service.seed_from_raw_transcript(
                        text, source, llm
                    )
                    transcripts_count += count
            
            total += transcripts_count
            logger.info(f"Seeded {transcripts_count} memories from transcripts")
            logger.info(f"TOTAL: Seeded {total} memories from all sources")
        
        background_tasks.add_task(_seed_all)
        
        return SeedingStatusResponse(
            status="started",
            memories_added=0,
            source="all",
            details={
                "contacts_found": len(contacts),
                "meetings_found": len(meetings),
                "transcripts_found": len(transcripts),
                "days_back": days_back
            }
        )
        
    except Exception as e:
        logger.exception("Failed to start comprehensive seeding")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/stats")
async def get_memory_stats():
    """
    Get statistics about stored memories.
    
    Returns counts by type and recent activity.
    """
    memory_service = get_memory()
    
    try:
        all_memories = await memory_service.get_all(limit=500)
        
        # Count by type
        type_counts = {}
        for mem in all_memories:
            mem_type = mem.get("metadata", {}).get("type", "unknown")
            type_counts[mem_type] = type_counts.get(mem_type, 0) + 1
        
        return {
            "status": "success",
            "total_memories": len(all_memories),
            "by_type": type_counts,
            "is_available": memory_service.is_available(),
        }
        
    except Exception as e:
        logger.exception("Failed to get memory stats")
        raise HTTPException(status_code=500, detail=str(e))
