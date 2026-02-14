"""
Knowledge Service - Main interface for RAG capabilities.

This is the primary class that agents and other services should use.
It provides a clean, unified API for all knowledge operations.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("Jarvis.Knowledge.Service")

# Singleton instance
_knowledge_service = None


class KnowledgeService:
    """
    Unified knowledge service for RAG operations.
    
    Usage:
        knowledge = get_knowledge_service()
        
        # Search across all data
        results = await knowledge.search("What did we discuss about Vietnam?")
        
        # Get context for a contact
        context = await knowledge.get_contact_context(contact_id)
        
        # Index new content
        await knowledge.index_transcript(transcript_id)
    """
    
    def __init__(self, db=None):
        """
        Initialize the knowledge service.
        
        Args:
            db: Optional database client. If not provided, will create one.
        """
        self._db = db
        self._initialized = False
    
    @property
    def db(self):
        """Lazy-load database client."""
        if self._db is None:
            from app.services.database import SupabaseMultiDatabase
            self._db = SupabaseMultiDatabase()
        return self._db
    
    # ==================== SEARCH METHODS ====================
    
    async def search(
        self,
        query: str,
        source_types: List[str] = None,
        contact_id: str = None,
        limit: int = 10,
        threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across all knowledge.

        Args:
            query: Natural language query
            source_types: Optional filter (e.g., ['transcript', 'meeting'])
            contact_id: Optional filter by related contact
            limit: Max results
            threshold: Minimum similarity score (0-1)

        Returns:
            List of matching chunks with content and metadata
        """
        from app.features.knowledge.retriever import hybrid_search

        return await hybrid_search(
            query=query,
            db=self.db,
            source_types=source_types,
            contact_id=contact_id,
            limit=limit,
            threshold=threshold
        )
    
    async def search_messages(
        self,
        query: str,
        platform: str = None,
        contact_id: str = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search specifically in messages (Beeper).
        
        Args:
            query: Search query
            platform: Optional filter ('whatsapp', 'linkedin', etc.)
            contact_id: Optional filter by contact
            limit: Max results
        """
        from app.features.knowledge.retriever import semantic_search
        
        results = await semantic_search(
            query=query,
            db=self.db,
            source_types=["message"],
            contact_id=contact_id,
            limit=limit * 2  # Get more, then filter
        )
        
        # Filter by platform if specified
        if platform:
            results = [r for r in results if r.get("metadata", {}).get("platform") == platform]
        
        return results[:limit]
    
    async def search_meetings(
        self,
        query: str,
        contact_id: str = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search specifically in meetings."""
        from app.features.knowledge.retriever import semantic_search
        
        return await semantic_search(
            query=query,
            db=self.db,
            source_types=["meeting"],
            contact_id=contact_id,
            limit=limit
        )
    
    # ==================== CONTEXT METHODS ====================
    
    async def get_context_for_query(
        self,
        query: str,
        source_types: List[str] = None,
        contact_id: str = None,
        max_tokens: int = 4000
    ) -> str:
        """
        Get formatted context for an LLM prompt.
        
        This is the main method for RAG - returns text ready
        to inject into a prompt.
        
        Args:
            query: The user's question
            source_types: Optional content type filter
            contact_id: Optional contact filter
            max_tokens: Approximate token budget
        
        Returns:
            Formatted context string
        """
        from app.features.knowledge.retriever import retrieve_context
        
        return await retrieve_context(
            query=query,
            db=self.db,
            source_types=source_types,
            contact_id=contact_id,
            max_tokens=max_tokens
        )
    
    async def get_contact_context(
        self,
        contact_id: str,
        include_messages: bool = True,
        include_meetings: bool = True,
        include_transcripts: bool = True,
        limit: int = 20
    ) -> str:
        """
        Get all context related to a specific contact.
        
        Perfect for background agents analyzing relationships.
        
        Args:
            contact_id: UUID of the contact
            include_messages: Include Beeper messages
            include_meetings: Include meeting records
            include_transcripts: Include transcript mentions
            limit: Max chunks per type
        
        Returns:
            Formatted context about the contact
        """
        from app.features.knowledge.retriever import get_contact_context
        
        return await get_contact_context(
            contact_id=contact_id,
            db=self.db,
            limit=limit
        )
    
    async def get_recent_context(
        self,
        days: int = 7,
        source_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get chunks from the last N days.
        
        Useful for "what happened this week" queries.
        """
        from app.features.knowledge.retriever import get_recent_context
        
        return await get_recent_context(
            db=self.db,
            days=days,
            source_types=source_types
        )
    
    # ==================== INDEXING METHODS ====================
    
    async def index_transcript(
        self,
        transcript_id: str,
        force: bool = False
    ) -> int:
        """
        Index a transcript for search.
        
        Call this after creating a new transcript.
        
        Args:
            transcript_id: UUID of the transcript
            force: Re-index even if already indexed
        
        Returns:
            Number of chunks created
        """
        from app.features.knowledge.indexer import index_transcript
        
        return await index_transcript(
            transcript_id=transcript_id,
            db=self.db,
            force=force
        )
    
    async def index_meeting(
        self,
        meeting_id: str,
        force: bool = False
    ) -> int:
        """Index a meeting for search."""
        from app.features.knowledge.indexer import index_meeting
        
        return await index_meeting(
            meeting_id=meeting_id,
            db=self.db,
            force=force
        )
    
    async def index_content(
        self,
        source_type: str,
        source_id: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> int:
        """
        Index any content type.
        
        Generic method for indexing arbitrary content.
        """
        from app.features.knowledge.indexer import index_content
        
        return await index_content(
            source_type=source_type,
            source_id=source_id,
            content=content,
            db=self.db,
            metadata=metadata
        )
    
    async def index_messages(
        self,
        chat_id: str,
        messages: List[Dict[str, Any]],
        platform: str = None,
        contact_id: str = None,
        contact_name: str = None
    ) -> int:
        """
        Index a batch of messages.
        
        Args:
            chat_id: Beeper chat ID
            messages: List of message dicts
            platform: Message platform
            contact_id: Related contact UUID
            contact_name: Contact display name
        """
        from app.features.knowledge.indexer import index_message
        
        return await index_message(
            chat_id=chat_id,
            messages=messages,
            db=self.db,
            platform=platform,
            contact_id=contact_id,
            contact_name=contact_name
        )
    
    async def index_contact(
        self,
        contact_id: str,
        force: bool = False
    ) -> int:
        """Index a contact profile."""
        from app.features.knowledge.indexer import index_contact
        
        return await index_contact(
            contact_id=contact_id,
            db=self.db,
            force=force
        )
    
    # ==================== BULK OPERATIONS ====================
    
    async def reindex_all(
        self,
        content_types: List[str] = None,
        limit: int = None
    ) -> Dict[str, Any]:
        """
        Reindex all content.
        
        Use for initial setup or after schema changes.
        
        Args:
            content_types: Which types to reindex (default: all)
            limit: Max records per type (for testing)
        
        Returns:
            Dict mapping source_type to {indexed: N, errors: N}
        """
        from app.features.knowledge.indexer import reindex_all
        
        return await reindex_all(
            source_types=content_types,
            db=self.db,
            limit=limit
        )
    
    async def delete_chunks_for_source(
        self,
        source_type: str,
        source_id: str
    ) -> int:
        """
        Soft-delete all chunks for a source.
        
        Call this when a source record is deleted.
        """
        try:
            result = self.db.client.table("knowledge_chunks").update({
                "deleted_at": datetime.now().isoformat()
            }).eq("source_type", source_type).eq("source_id", source_id).execute()
            
            return len(result.data) if result.data else 0
        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")
            return 0
    
    # ==================== STATS & HEALTH ====================
    
    async def get_stats(self) -> Dict[str, int]:
        """Get knowledge base statistics by source type."""
        try:
            # Get counts grouped by source_type
            result = self.db.client.table("knowledge_chunks").select(
                "source_type"
            ).is_("deleted_at", "null").execute()
            
            # Count by type
            counts = {}
            for row in (result.data or []):
                source_type = row.get("source_type")
                if source_type:
                    counts[source_type] = counts.get(source_type, 0) + 1
            
            return counts
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check if knowledge system is healthy."""
        supabase_ok = False
        openai_ok = False
        total_chunks = 0
        
        # Check Supabase connection
        try:
            result = self.db.client.table("knowledge_chunks").select(
                "id", count="exact"
            ).is_("deleted_at", "null").limit(1).execute()
            supabase_ok = True
            total_chunks = result.count if hasattr(result, 'count') else 0
        except Exception as e:
            logger.error(f"Supabase health check failed: {e}")
        
        # Check OpenAI API key
        import os
        openai_ok = bool(os.getenv("OPENAI_API_KEY"))
        
        return {
            "supabase_connected": supabase_ok,
            "openai_configured": openai_ok,
            "total_chunks": total_chunks,
            "status": "healthy" if (supabase_ok and openai_ok) else "unhealthy"
        }


def get_knowledge_service() -> KnowledgeService:
    """Get the singleton knowledge service instance."""
    global _knowledge_service
    
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    
    return _knowledge_service


# For background agents - they can create their own instance if needed
def create_knowledge_service(db=None) -> KnowledgeService:
    """Create a new knowledge service instance (for isolation)."""
    return KnowledgeService(db=db)
