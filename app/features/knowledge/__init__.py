"""
Knowledge System - Unified RAG for all Jarvis data.

This module provides:
1. Indexing: Convert any content to searchable chunks
2. Retrieval: Semantic search across all data
3. Context Building: Assemble relevant context for LLM

Design for modularity:
- Each component is independent
- Chunking strategies are pluggable
- Works with background agents
"""

from app.features.knowledge.service import (
    KnowledgeService,
    get_knowledge_service,
)
from app.features.knowledge.indexer import (
    index_content,
    index_transcript,
    index_meeting,
    index_message,
    index_contact,
    index_application,
    index_document,
    index_calendar_event,
    index_journal,
    index_reflection,
    reindex_all,
)
from app.features.knowledge.retriever import (
    retrieve_context,
    semantic_search,
    hybrid_search,
)
from app.features.knowledge.chunker import (
    chunk_transcript,
    chunk_document,
    chunk_messages,
    chunk_application,
    chunk_contact,
)

__all__ = [
    # Main service
    "KnowledgeService",
    "get_knowledge_service",
    # Indexing
    "index_content",
    "index_transcript",
    "index_meeting",
    "index_message",
    "index_contact",
    "index_application",
    "index_document",
    "index_calendar_event",
    "index_journal",
    "index_reflection",
    "reindex_all",
    # Retrieval
    "retrieve_context",
    "semantic_search",
    "hybrid_search",
    # Chunking
    "chunk_transcript",
    "chunk_document",
    "chunk_messages",
    "chunk_application",
    "chunk_contact",
]
