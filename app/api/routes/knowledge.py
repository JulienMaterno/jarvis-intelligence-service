"""
Knowledge/RAG API endpoints.

These endpoints expose the knowledge system for:
1. AI agents to search context
2. Web UI to display search results  
3. Background agents to query the knowledge base
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging

from app.features.knowledge import get_knowledge_service

logger = logging.getLogger("Jarvis.API.Knowledge")
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ===================== Request/Response Models =====================

class SearchRequest(BaseModel):
    """Search request for knowledge base."""
    query: str = Field(..., description="Search query text")
    source_types: Optional[List[str]] = Field(
        None, 
        description="Filter by content types: transcript, meeting, journal, reflection, contact, message, etc."
    )
    contact_id: Optional[str] = Field(None, description="Filter by contact UUID")
    limit: int = Field(10, ge=1, le=50, description="Max results to return")
    threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchResult(BaseModel):
    """A single search result."""
    source_type: str
    source_id: str
    content: str
    similarity: float
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    results: List[SearchResult]
    total: int


class ContextRequest(BaseModel):
    """Request for formatted context (for LLM prompts)."""
    query: str = Field(..., description="The user's question")
    source_types: Optional[List[str]] = None
    contact_id: Optional[str] = None
    max_tokens: int = Field(4000, ge=500, le=16000)


class ContextResponse(BaseModel):
    """Formatted context for LLM injection."""
    query: str
    context: str
    token_estimate: int


class IndexStats(BaseModel):
    """Knowledge base statistics."""
    total_chunks: int
    by_source_type: Dict[str, int]


class HealthStatus(BaseModel):
    """Health check status."""
    status: str
    supabase_connected: bool
    openai_configured: bool
    total_chunks: int


# ===================== Endpoints =====================

@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """
    Semantic search across the knowledge base.
    
    Use this to find relevant content based on natural language queries.
    Results are ranked by similarity score.
    
    **For AI agents**: Use this to find context before responding.
    """
    try:
        knowledge = get_knowledge_service()
        
        results = await knowledge.search(
            query=request.query,
            source_types=request.source_types,
            contact_id=request.contact_id,
            limit=request.limit,
            threshold=request.threshold
        )
        
        return SearchResponse(
            query=request.query,
            results=[SearchResult(**r) for r in results],
            total=len(results)
        )
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=SearchResponse)
async def search_knowledge_get(
    q: str = Query(..., description="Search query"),
    types: Optional[str] = Query(None, description="Comma-separated source types"),
    contact_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.5, ge=0.0, le=1.0)
):
    """
    GET version of search for simple queries.
    
    Example: /knowledge/search?q=meeting with john about budget&types=meeting,transcript&limit=5
    """
    source_types = types.split(",") if types else None
    
    return await search_knowledge(SearchRequest(
        query=q,
        source_types=source_types,
        contact_id=contact_id,
        limit=limit,
        threshold=threshold
    ))


@router.post("/context", response_model=ContextResponse)
async def get_rag_context(request: ContextRequest):
    """
    Get formatted context for LLM prompt injection.
    
    Returns a ready-to-use context string that can be directly
    injected into an AI prompt. Handles token limits automatically.
    
    **For AI agents**: Use this when you need context for a response.
    """
    try:
        knowledge = get_knowledge_service()
        
        context = await knowledge.get_context_for_query(
            query=request.query,
            source_types=request.source_types,
            contact_id=request.contact_id,
            max_tokens=request.max_tokens
        )
        
        # Estimate tokens (rough: 4 chars per token)
        token_estimate = len(context) // 4
        
        return ContextResponse(
            query=request.query,
            context=context,
            token_estimate=token_estimate
        )
    except Exception as e:
        logger.error(f"Context retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/contact/{contact_id}/context")
async def get_contact_context(
    contact_id: str,
    include_messages: bool = Query(True),
    include_meetings: bool = Query(True),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get all knowledge related to a specific contact.
    
    Returns formatted context about a person including:
    - Their profile information
    - Meeting history
    - Message conversations
    - Mentions in transcripts
    
    **For AI agents**: Use when discussing or preparing for interaction with a person.
    """
    try:
        knowledge = get_knowledge_service()
        
        context = await knowledge.get_contact_context(
            contact_id=contact_id,
            include_messages=include_messages,
            include_meetings=include_meetings,
            limit=limit
        )
        
        return {
            "contact_id": contact_id,
            "context": context,
            "token_estimate": len(context) // 4
        }
    except Exception as e:
        logger.error(f"Contact context failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_context(
    days: int = Query(7, ge=1, le=90),
    source_types: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Get recent context from the knowledge base.
    
    Retrieves recently indexed content, useful for:
    - Daily briefings
    - "What happened this week" queries
    - Background agent context gathering
    """
    try:
        knowledge = get_knowledge_service()
        types_list = source_types.split(",") if source_types else None
        
        context = await knowledge.get_recent_context(
            days=days,
            source_types=types_list,
            limit=limit
        )
        
        return {
            "days": days,
            "context": context,
            "token_estimate": len(context) // 4
        }
    except Exception as e:
        logger.error(f"Recent context failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=IndexStats)
async def get_knowledge_stats():
    """
    Get knowledge base statistics.
    
    Shows how many chunks are indexed by source type.
    Useful for monitoring the health of the RAG system.
    """
    try:
        knowledge = get_knowledge_service()
        stats = await knowledge.get_stats()
        
        return IndexStats(
            by_source_type=stats,
            total_chunks=sum(stats.values())
        )
    except Exception as e:
        logger.error(f"Stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthStatus)
async def knowledge_health_check():
    """
    Check if the knowledge system is healthy.
    
    Verifies:
    - Supabase connection
    - OpenAI API key configured
    - Table accessible
    """
    try:
        knowledge = get_knowledge_service()
        health = await knowledge.health_check()
        
        return HealthStatus(
            status=health.get("status", "unknown"),
            supabase_connected=health.get("supabase_connected", False),
            openai_configured=health.get("openai_configured", False),
            total_chunks=health.get("total_chunks", 0)
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthStatus(
            status="error",
            supabase_connected=False,
            openai_configured=False,
            total_chunks=0
        )


@router.post("/reindex")
async def trigger_reindex(
    source_types: Optional[List[str]] = None,
    limit: Optional[int] = None
):
    """
    Trigger a reindex of the knowledge base.
    
    **Warning**: This can be slow for large datasets.
    Use source_types filter to reindex specific content.
    Use limit for testing.
    
    Example: POST /knowledge/reindex with body:
    {"source_types": ["meeting", "journal"], "limit": 100}
    """
    try:
        knowledge = get_knowledge_service()
        
        results = await knowledge.reindex_all(
            content_types=source_types,
            limit=limit
        )
        
        return {
            "status": "completed",
            "results": results
        }
    except Exception as e:
        logger.error(f"Reindex failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
