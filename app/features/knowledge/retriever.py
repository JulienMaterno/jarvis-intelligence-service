"""
Retrieval service - semantic search across all knowledge.

This is the "read" side of RAG - called when answering questions.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("Jarvis.Knowledge.Retriever")


async def get_query_embedding(query: str) -> List[float]:
    """Generate embedding for a search query."""
    from app.features.knowledge.indexer import get_embedding
    return await get_embedding(query)


async def semantic_search(
    query: str,
    db,
    source_types: List[str] = None,
    contact_id: str = None,
    date_from: datetime = None,
    date_to: datetime = None,
    limit: int = 10,
    similarity_threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Perform semantic search across knowledge chunks.
    
    Args:
        query: The search query (natural language)
        db: Database client
        source_types: Filter by content types (e.g., ['transcript', 'meeting'])
        contact_id: Filter by related contact
        date_from: Filter by date range start
        date_to: Filter by date range end
        limit: Max results to return
        similarity_threshold: Min cosine similarity (0-1)
    
    Returns:
        List of matching chunks with similarity scores
    """
    # Generate query embedding
    query_embedding = await get_query_embedding(query)
    
    # Build the query using pgvector
    # We need to use RPC for vector similarity search
    
    # Convert embedding to string format for Postgres
    embedding_str = f"[{','.join(map(str, query_embedding))}]"
    
    # Build filter conditions
    filters = ["deleted_at IS NULL"]
    params = {
        "query_embedding": embedding_str,
        "match_threshold": similarity_threshold,
        "match_count": limit
    }
    
    if source_types:
        filters.append(f"source_type = ANY(ARRAY{source_types})")
    
    if contact_id:
        filters.append(f"metadata->>'contact_id' = '{contact_id}'")
    
    # Use RPC function for vector search
    # This assumes we have a match_knowledge_chunks function
    try:
        result = db.client.rpc("match_knowledge_chunks", {
            "query_embedding": query_embedding,
            "match_threshold": similarity_threshold,
            "match_count": limit,
            "filter_source_types": source_types,
            "filter_contact_id": contact_id
        }).execute()
        
        if result.data:
            return result.data
    except Exception as e:
        logger.warning(f"RPC search failed, falling back to manual: {e}")
    
    # Fallback: Manual search (less efficient but works without RPC)
    return await _manual_semantic_search(
        query_embedding=query_embedding,
        db=db,
        source_types=source_types,
        contact_id=contact_id,
        limit=limit,
        threshold=similarity_threshold
    )


async def _manual_semantic_search(
    query_embedding: List[float],
    db,
    source_types: List[str] = None,
    contact_id: str = None,
    limit: int = 10,
    threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Fallback semantic search without RPC.
    
    Less efficient but works on any Supabase setup.
    """
    import numpy as np
    
    # Fetch chunks (with filters)
    query = db.client.table("knowledge_chunks").select(
        "id, source_type, source_id, chunk_index, content, metadata, embedding"
    ).is_("deleted_at", "null")
    
    if source_types:
        query = query.in_("source_type", source_types)
    
    if contact_id:
        query = query.eq("metadata->>contact_id", contact_id)
    
    # Limit to reasonable number for in-memory processing
    query = query.limit(1000)
    
    result = query.execute()
    
    if not result.data:
        return []
    
    # Calculate similarities
    query_vec = np.array(query_embedding)
    results = []
    
    for chunk in result.data:
        if not chunk.get("embedding"):
            continue
        
        chunk_vec = np.array(chunk["embedding"])
        
        # Cosine similarity
        similarity = np.dot(query_vec, chunk_vec) / (
            np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec)
        )
        
        if similarity >= threshold:
            results.append({
                "id": chunk["id"],
                "source_type": chunk["source_type"],
                "source_id": chunk["source_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["content"],
                "metadata": chunk["metadata"],
                "similarity": float(similarity)
            })
    
    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    
    return results[:limit]


async def hybrid_search(
    query: str,
    db,
    source_types: List[str] = None,
    contact_id: str = None,
    limit: int = 10,
    threshold: float = 0.6
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining semantic + keyword matching.

    Better for queries with specific names or terms.
    """
    # Semantic search
    semantic_results = await semantic_search(
        query=query,
        db=db,
        source_types=source_types,
        contact_id=contact_id,
        limit=limit * 2,  # Get more for re-ranking
        similarity_threshold=threshold
    )
    
    # Keyword search
    keyword_results = await _keyword_search(
        query=query,
        db=db,
        source_types=source_types,
        limit=limit
    )
    
    # Merge and deduplicate
    seen_ids = set()
    merged = []
    
    # Semantic results first (usually better quality)
    for result in semantic_results:
        if result["id"] not in seen_ids:
            seen_ids.add(result["id"])
            result["match_type"] = "semantic"
            merged.append(result)
    
    # Add keyword results that weren't in semantic
    for result in keyword_results:
        if result["id"] not in seen_ids:
            seen_ids.add(result["id"])
            result["match_type"] = "keyword"
            result["similarity"] = 0.5  # Default score for keyword matches
            merged.append(result)
    
    # Re-sort by similarity
    merged.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    
    return merged[:limit]


async def _keyword_search(
    query: str,
    db,
    source_types: List[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Simple keyword/text search as fallback."""
    # Sanitize query for ILIKE pattern - escape special PostgreSQL LIKE chars
    sanitized = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # Use Postgres full-text search or ILIKE
    base_query = db.client.table("knowledge_chunks").select(
        "id, source_type, source_id, chunk_index, content, metadata"
    ).is_("deleted_at", "null")

    if source_types:
        base_query = base_query.in_("source_type", source_types)

    # Use ILIKE for simple matching with sanitized input
    base_query = base_query.ilike("content", f"%{sanitized}%")

    result = base_query.limit(limit).execute()

    return result.data if result.data else []


async def retrieve_context(
    query: str,
    db,
    source_types: List[str] = None,
    contact_id: str = None,
    limit: int = 10,
    max_tokens: int = 4000
) -> str:
    """
    Retrieve and format context for LLM consumption.
    
    This is the main function for RAG - returns formatted text
    ready to inject into a prompt.
    
    Args:
        query: The user's question
        db: Database client
        source_types: Filter by content types
        contact_id: Filter by related contact
        limit: Max chunks to retrieve
        max_tokens: Approximate token limit for context
    
    Returns:
        Formatted context string for LLM prompt
    """
    # Use hybrid search for best results
    results = await hybrid_search(
        query=query,
        db=db,
        source_types=source_types,
        contact_id=contact_id,
        limit=limit
    )
    
    if not results:
        return ""
    
    # Format results as context
    context_parts = []
    total_chars = 0
    max_chars = max_tokens * 4  # Rough conversion
    
    for result in results:
        # Format each chunk with source info
        source_type = result.get("source_type", "unknown")
        content = result.get("content", "")
        metadata = result.get("metadata", {})
        
        # Build source citation
        source_info = f"[{source_type.upper()}"
        if metadata.get("date"):
            source_info += f" - {metadata['date'][:10]}"
        if metadata.get("contact_name"):
            source_info += f" - {metadata['contact_name']}"
        source_info += "]"
        
        chunk_text = f"{source_info}\n{content}"
        
        # Check token limit
        if total_chars + len(chunk_text) > max_chars:
            break
        
        context_parts.append(chunk_text)
        total_chars += len(chunk_text)
    
    return "\n\n---\n\n".join(context_parts)


async def get_contact_context(
    contact_id: str,
    db,
    limit: int = 20
) -> str:
    """
    Get all context related to a specific contact.

    Useful for background agents analyzing relationships.
    Uses a direct database query filtered by contact_id instead of
    semantic search, since there is no meaningful query to embed.
    """
    try:
        result = db.client.table("knowledge_chunks").select(
            "id, source_type, source_id, chunk_index, content, metadata, created_at"
        ).is_("deleted_at", "null").eq(
            "metadata->>contact_id", contact_id
        ).order("created_at", desc=True).limit(limit).execute()

        results = []
        for chunk in (result.data or []):
            results.append({
                "id": chunk["id"],
                "source_type": chunk["source_type"],
                "source_id": chunk["source_id"],
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk["content"],
                "metadata": chunk.get("metadata", {}),
                "similarity": 1.0,  # Direct match, not semantic
            })
    except Exception as e:
        logger.warning(f"Direct contact context query failed, falling back to semantic: {e}")
        # Fall back to semantic search with contact name if direct query fails
        results = await semantic_search(
            query=f"contact {contact_id}",
            db=db,
            contact_id=contact_id,
            limit=limit,
            similarity_threshold=0
        )

    # Sort by date if available
    results.sort(key=lambda x: x.get("metadata", {}).get("date", ""), reverse=True)

    return await _format_contact_context(results)


async def _format_contact_context(results: List[Dict]) -> str:
    """Format contact-related chunks as context."""
    if not results:
        return "No previous interactions found."
    
    parts = ["## Previous Interactions\n"]
    
    for result in results:
        source_type = result.get("source_type", "")
        metadata = result.get("metadata", {})
        content = result.get("content", "")
        
        date_str = metadata.get("date", "Unknown date")[:10] if metadata.get("date") else "Unknown date"
        
        if source_type == "meeting":
            parts.append(f"### Meeting ({date_str})\n{content}\n")
        elif source_type == "message":
            platform = metadata.get("platform", "chat")
            parts.append(f"### {platform.title()} ({date_str})\n{content}\n")
        elif source_type == "transcript":
            parts.append(f"### Voice Note ({date_str})\n{content[:500]}...\n")
        else:
            parts.append(f"### {source_type.title()} ({date_str})\n{content}\n")
    
    return "\n".join(parts)


async def get_recent_context(
    db,
    days: int = 7,
    source_types: List[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Get recent chunks for a time-based context window.
    
    Useful for "what happened this week" type queries.
    """
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.isoformat()
    
    query = db.client.table("knowledge_chunks").select(
        "id, source_type, source_id, content, metadata, created_at"
    ).is_("deleted_at", "null").gte("created_at", cutoff_str)
    
    if source_types:
        query = query.in_("source_type", source_types)
    
    query = query.order("created_at", desc=True).limit(limit)
    
    result = query.execute()
    
    return result.data if result.data else []
