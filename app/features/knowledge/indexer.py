"""
Indexing service - convert content to searchable chunks with embeddings.

This is the "write" side of RAG - called when new content is created.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.features.knowledge.chunker import (
    chunk_transcript,
    chunk_document,
    chunk_messages,
    chunk_contact,
    chunk_task,
    chunk_calendar_event,
    chunk_application,
    chunk_linkedin_post,
    chunk_book,
    chunk_highlight,
    chunk_email,
    chunk_beeper_message,
)

logger = logging.getLogger("Jarvis.Knowledge.Indexer")


_openai_client = None


def _get_openai_client():
    """Reuse a single AsyncOpenAI client across all embedding calls."""
    global _openai_client
    if _openai_client is None:
        import openai
        import os
        _openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


async def get_embedding(text: str) -> List[float]:
    """Generate embedding for text using OpenAI ada-002 (1536-dim)."""
    client = _get_openai_client()
    response = await client.embeddings.create(
        model="text-embedding-ada-002",
        input=text[:8000]
    )
    return response.data[0].embedding


async def index_content(
    source_type: str,
    source_id: str,
    content: str,
    db,
    metadata: Dict[str, Any] = None,
    segments: List[Dict] = None
) -> int:
    """
    Index any content into the knowledge store.
    
    Automatically detects chunking strategy based on source_type.
    
    Args:
        source_type: 'transcript', 'meeting', 'journal', 'reflection', 
                     'message', 'contact', 'task', 'calendar'
        source_id: UUID of the source record
        content: The text content to index
        db: Database client
        metadata: Additional metadata to include
        segments: For transcripts, the WhisperX segments
    
    Returns:
        Number of chunks created
    """
    metadata = metadata or {}
    
    # Soft-delete existing chunks for this source (re-indexing)
    try:
        db.client.table("knowledge_chunks").update({
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }).eq("source_id", source_id).is_("deleted_at", "null").execute()
    except Exception as e:
        logger.warning(f"Failed to soft-delete existing chunks: {e}")
    
    # Chunk based on content type
    if source_type == "transcript":
        chunks = chunk_transcript(
            full_text=content,
            segments=segments,
            source_id=source_id,
            language=metadata.get("language", "en")
        )
    elif source_type in ("journal", "reflection"):
        chunks = chunk_document(
            content=content,
            source_type=source_type,
            source_id=source_id,
            title=metadata.get("title"),
            date=metadata.get("date"),
            tags=metadata.get("tags")
        )
    elif source_type == "meeting":
        # Meetings are usually summaries, embed as single chunk
        chunks = chunk_document(
            content=content,
            source_type=source_type,
            source_id=source_id,
            title=metadata.get("title"),
            date=metadata.get("date")
        )
    elif source_type == "contact":
        # Contact profiles are formatted specially
        chunk = chunk_contact(metadata)  # metadata contains contact info
        chunk["content"] = content  # Override if content provided
        chunks = [chunk]
    elif source_type == "task":
        chunk = chunk_task(metadata)
        chunks = [chunk]
    elif source_type == "calendar":
        chunk = chunk_calendar_event(metadata)
        chunks = [chunk]
    elif source_type == "application":
        # Applications can be long (questions/answers)
        chunks = chunk_application(metadata)
    elif source_type == "linkedin_post":
        chunk = chunk_linkedin_post(metadata)
        chunks = [chunk]
    elif source_type == "book":
        chunk = chunk_book(metadata)
        chunks = [chunk]
    elif source_type == "highlight":
        chunk = chunk_highlight(metadata, metadata.get("book_title"))
        chunks = [chunk]
    elif source_type == "document":
        # Documents (CV, profiles) - chunk if long
        chunks = chunk_document(
            content=content,
            source_type=source_type,
            source_id=source_id,
            title=metadata.get("title"),
            tags=metadata.get("tags")
        )
    else:
        # Default: paragraph-based chunking
        chunks = chunk_document(content, source_type, source_id)
    
    # Generate embeddings and store
    created_count = 0
    for chunk in chunks:
        try:
            # Generate embedding
            embedding = await get_embedding(chunk["content"])
            
            # Merge metadata
            chunk_metadata = {**metadata, **chunk.get("metadata", {})}
            
            # Insert into database
            db.client.table("knowledge_chunks").insert({
                "source_type": source_type,
                "source_id": source_id,
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk["content"],
                "content_hash": chunk.get("content_hash"),
                "embedding": embedding,
                "metadata": chunk_metadata
            }).execute()
            
            created_count += 1
            
        except Exception as e:
            logger.error(f"Failed to index chunk {chunk.get('chunk_index')}: {e}")
    
    logger.info(f"Indexed {source_type} {source_id}: {created_count}/{len(chunks)} chunks")
    return created_count


async def index_transcript(
    transcript_id: str,
    db,
    force: bool = False
) -> int:
    """
    Index a transcript from the database.
    
    Args:
        transcript_id: UUID of the transcript
        db: Database client
        force: Re-index even if already indexed
    """
    # Check if already indexed
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", transcript_id
        ).eq("source_type", "transcript").limit(1).execute()
        
        if existing.data:
            logger.info(f"Transcript {transcript_id} already indexed, skipping")
            return 0
    
    # Fetch transcript
    result = db.client.table("transcripts").select("*").eq(
        "id", transcript_id
    ).execute()
    
    if not result.data:
        logger.error(f"Transcript not found: {transcript_id}")
        return 0
    
    transcript = result.data[0]
    
    return await index_content(
        source_type="transcript",
        source_id=transcript_id,
        content=transcript.get("full_text", ""),
        db=db,
        metadata={
            "language": transcript.get("language"),
            "source_file": transcript.get("source_file"),
            "date": transcript.get("created_at")
        },
        segments=transcript.get("segments")
    )


async def index_meeting(meeting_id: str, db, force: bool = False) -> int:
    """Index a meeting record."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", meeting_id
        ).eq("source_type", "meeting").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("meetings").select("*").eq("id", meeting_id).execute()
    if not result.data:
        return 0
    
    meeting = result.data[0]
    
    # Build meeting text for embedding
    content_parts = [
        f"Meeting: {meeting.get('title', 'Untitled')}",
        f"With: {meeting.get('contact_name', 'Unknown')}",
    ]
    if meeting.get("summary"):
        content_parts.append(f"Summary: {meeting['summary']}")
    if meeting.get("topics_discussed"):
        topics = meeting["topics_discussed"]
        if isinstance(topics, list):
            # Handle both string and dict formats
            topic_strs = []
            for t in topics:
                if isinstance(t, dict):
                    topic_strs.append(t.get("topic", str(t)))
                else:
                    topic_strs.append(str(t))
            content_parts.append(f"Topics: {', '.join(topic_strs)}")
    if meeting.get("action_items"):
        items = meeting["action_items"]
        if isinstance(items, list):
            # Handle both string and dict formats
            item_strs = []
            for item in items:
                if isinstance(item, dict):
                    item_strs.append(item.get("item", item.get("text", str(item))))
                else:
                    item_strs.append(str(item))
            content_parts.append(f"Action Items: {'; '.join(item_strs)}")
    
    content = "\n".join(content_parts)
    
    return await index_content(
        source_type="meeting",
        source_id=meeting_id,
        content=content,
        db=db,
        metadata={
            "title": meeting.get("title"),
            "date": meeting.get("date"),
            "contact_id": meeting.get("contact_id"),
            "contact_name": meeting.get("contact_name")
        }
    )


async def index_message(
    chat_id: str,
    messages: List[Dict[str, Any]],
    db,
    platform: str = None,
    contact_id: str = None,
    contact_name: str = None,
    force: bool = False
) -> int:
    """
    Index a batch of messages from a chat.
    
    Args:
        chat_id: Beeper chat ID
        messages: List of message dicts
        db: Database client
        platform: 'whatsapp', 'linkedin', etc.
        contact_id: Related contact UUID
        contact_name: Contact's display name
        force: Re-index even if already indexed
    """
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", chat_id
        ).eq("source_type", "message").limit(1).execute()
        if existing.data:
            return 0
    
    # Use message chunker
    chunks = chunk_messages(
        messages=messages,
        conversation_id=chat_id,
        platform=platform,
        contact_id=contact_id,
        contact_name=contact_name
    )
    
    created_count = 0
    for chunk in chunks:
        try:
            embedding = await get_embedding(chunk["content"])
            
            db.client.table("knowledge_chunks").insert({
                "source_type": "message",
                "source_id": chat_id,
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk["content"],
                "content_hash": chunk.get("content_hash"),
                "embedding": embedding,
                "metadata": chunk.get("metadata", {})
            }).execute()
            
            created_count += 1
        except Exception as e:
            logger.error(f"Failed to index message chunk: {e}")
    
    return created_count


async def index_contact(contact_id: str, db, force: bool = False) -> int:
    """Index a contact profile."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", contact_id
        ).eq("source_type", "contact").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("contacts").select("*").eq("id", contact_id).execute()
    if not result.data:
        return 0
    
    contact = result.data[0]
    chunk = chunk_contact(contact)
    
    try:
        embedding = await get_embedding(chunk["content"])
        
        db.client.table("knowledge_chunks").insert({
            "source_type": "contact",
            "source_id": contact_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        
        return 1
    except Exception as e:
        logger.error(f"Failed to index contact: {e}")
        return 0


async def index_application(app_id: str, db, force: bool = False) -> int:
    """Index an application record."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", app_id
        ).eq("source_type", "application").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("applications").select("*").eq("id", app_id).execute()
    if not result.data:
        return 0
    
    app = result.data[0]
    chunks = chunk_application(app)
    
    created_count = 0
    for chunk in chunks:
        try:
            embedding = await get_embedding(chunk["content"])
            db.client.table("knowledge_chunks").insert({
                "source_type": "application",
                "source_id": app_id,
                "chunk_index": chunk.get("chunk_index", 0),
                "content": chunk["content"],
                "content_hash": chunk.get("content_hash"),
                "embedding": embedding,
                "metadata": chunk.get("metadata", {})
            }).execute()
            created_count += 1
        except Exception as e:
            logger.error(f"Failed to index application chunk: {e}")
    
    return created_count


async def index_document(doc_id: str, db, force: bool = False) -> int:
    """Index a document (CV, profile, etc.)."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", doc_id
        ).eq("source_type", "document").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("documents").select("*").eq("id", doc_id).execute()
    if not result.data:
        return 0
    
    doc = result.data[0]
    content = doc.get("content", "")
    
    if not content:
        logger.warning(f"Document {doc_id} has no content")
        return 0
    
    return await index_content(
        source_type="document",
        source_id=doc_id,
        content=content,
        db=db,
        metadata={
            "title": doc.get("title"),
            "type": doc.get("type"),
            "tags": doc.get("tags", [])
        }
    )


async def index_calendar_event(event_id: str, db, force: bool = False) -> int:
    """Index a calendar event."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", event_id
        ).eq("source_type", "calendar").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("calendar_events").select("*").eq("id", event_id).execute()
    if not result.data:
        return 0
    
    event = result.data[0]
    chunk = chunk_calendar_event(event)
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "calendar",
            "source_id": event_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index calendar event: {e}")
        return 0


async def index_task(task_id: str, db, force: bool = False) -> int:
    """Index a task."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", task_id
        ).eq("source_type", "task").limit(1).execute()
        if existing.data:
            return 0

    result = db.client.table("tasks").select("*").eq("id", task_id).execute()
    if not result.data:
        return 0

    task = result.data[0]

    # Skip deleted tasks
    if task.get("deleted_at"):
        return 0

    chunk = chunk_task(task)

    # Skip tasks with minimal content
    if len(chunk["content"]) < 15:
        return 0

    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "task",
            "source_id": task_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {}),
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index task: {e}")
        return 0


async def index_journal(journal_id: str, db, force: bool = False) -> int:
    """Index a journal entry."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", journal_id
        ).eq("source_type", "journal").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("journals").select("*").eq("id", journal_id).execute()
    if not result.data:
        return 0
    
    journal = result.data[0]
    
    # Build content from all journal fields
    content_parts = [f"Journal: {journal.get('title', journal.get('date', 'Untitled'))}"]
    
    if journal.get("content"):
        content_parts.append(journal["content"])
    
    if journal.get("gratitude"):
        content_parts.append(f"Gratitude: {', '.join(journal['gratitude'])}")
    
    if journal.get("wins"):
        content_parts.append(f"Wins: {', '.join(journal['wins'])}")
    
    if journal.get("challenges"):
        content_parts.append(f"Challenges: {', '.join(journal['challenges'])}")
    
    if journal.get("tomorrow_focus"):
        content_parts.append(f"Tomorrow's Focus: {', '.join(journal['tomorrow_focus'])}")
    
    content = "\n\n".join(content_parts)
    
    return await index_content(
        source_type="journal",
        source_id=journal_id,
        content=content,
        db=db,
        metadata={
            "date": str(journal.get("date")),
            "mood": journal.get("mood"),
            "energy": journal.get("energy")
        }
    )


async def index_reflection(reflection_id: str, db, force: bool = False) -> int:
    """Index a reflection."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", reflection_id
        ).eq("source_type", "reflection").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("reflections").select("*").eq("id", reflection_id).execute()
    if not result.data:
        return 0
    
    reflection = result.data[0]
    
    content_parts = [f"Reflection: {reflection.get('title', 'Untitled')}"]
    
    if reflection.get("content"):
        content_parts.append(reflection["content"])
    
    content = "\n\n".join(content_parts)
    
    return await index_content(
        source_type="reflection",
        source_id=reflection_id,
        content=content,
        db=db,
        metadata={
            "date": str(reflection.get("date")),
            "tags": reflection.get("tags", []),
            "mood": reflection.get("mood"),
            "people_mentioned": reflection.get("people_mentioned", [])
        }
    )


async def index_email(email_id: str, db, force: bool = False) -> int:
    """
    Index an email.
    
    Emails contain valuable knowledge about communications and decisions.
    """
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", email_id
        ).eq("source_type", "email").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("emails").select("*").eq("id", email_id).execute()
    if not result.data:
        return 0
    
    email = result.data[0]
    chunk = chunk_email(email)
    
    # Skip emails with no meaningful content
    if len(chunk["content"]) < 50:
        return 0
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "email",
            "source_id": email_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index email: {e}")
        return 0


async def index_book(book_id: str, db, force: bool = False) -> int:
    """Index a book record."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", book_id
        ).eq("source_type", "book").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("books").select("*").eq("id", book_id).execute()
    if not result.data:
        return 0
    
    book = result.data[0]
    chunk = chunk_book(book)
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "book",
            "source_id": book_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index book: {e}")
        return 0


async def index_highlight(highlight_id: str, db, force: bool = False) -> int:
    """Index a book highlight."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", highlight_id
        ).eq("source_type", "highlight").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("highlights").select("*, books(title)").eq("id", highlight_id).execute()
    if not result.data:
        return 0
    
    highlight = result.data[0]
    book_title = highlight.get("books", {}).get("title") if highlight.get("books") else None
    chunk = chunk_highlight(highlight, book_title)
    
    # Skip very short highlights
    if len(chunk["content"]) < 30:
        return 0
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "highlight",
            "source_id": highlight_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index highlight: {e}")
        return 0


async def index_linkedin_post(post_id: str, db, force: bool = False) -> int:
    """Index a LinkedIn post."""
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", post_id
        ).eq("source_type", "linkedin_post").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("linkedin_posts").select("*").eq("id", post_id).execute()
    if not result.data:
        return 0
    
    post = result.data[0]
    chunk = chunk_linkedin_post(post)
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "linkedin_post",
            "source_id": post_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": chunk.get("metadata", {})
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index linkedin post: {e}")
        return 0


async def index_beeper_message(message_id: str, db, force: bool = False) -> int:
    """
    Index a Beeper chat message.
    
    Messages from WhatsApp, LinkedIn, Slack contain valuable relationship context.
    Groups messages by conversation for better semantic retrieval.
    """
    if not force:
        existing = db.client.table("knowledge_chunks").select("id").eq(
            "source_id", message_id
        ).eq("source_type", "beeper_message").limit(1).execute()
        if existing.data:
            return 0
    
    result = db.client.table("beeper_messages").select("*").eq("id", message_id).execute()
    if not result.data:
        return 0
    
    message = result.data[0]
    
    # Skip very short messages (reactions, "ok", etc.)
    content = message.get("content", "")
    if len(content) < 10:
        return 0
    
    # Get chat info for context
    chat_name = message.get("sender_name", "Unknown")
    platform = message.get("platform", "chat")
    
    chunk = chunk_beeper_message(message, chat_name=chat_name, platform=platform)
    
    try:
        embedding = await get_embedding(chunk["content"])
        db.client.table("knowledge_chunks").insert({
            "source_type": "beeper_message",
            "source_id": message_id,
            "chunk_index": 0,
            "content": chunk["content"],
            "content_hash": chunk.get("content_hash"),
            "embedding": embedding,
            "metadata": {
                **chunk.get("metadata", {}),
                "platform": platform,
                "sender_name": message.get("sender_name"),
                "beeper_chat_id": message.get("beeper_chat_id")
            }
        }).execute()
        return 1
    except Exception as e:
        logger.error(f"Failed to index beeper message: {e}")
        return 0


# Table name mapping for reindex_all
TABLE_NAME_MAP = {
    "transcript": "transcripts",
    "meeting": "meetings",
    "contact": "contacts",
    "journal": "journals",
    "reflection": "reflections",
    "task": "tasks",
    "calendar": "calendar_events",
    "application": "applications",
    "document": "documents",
    "linkedin_post": "linkedin_posts",
    "book": "books",
    "highlight": "highlights",
    "email": "emails",
    "beeper_message": "beeper_messages",
}

# Indexing function mapping
INDEX_FUNCTION_MAP = {
    "transcript": lambda id, db: index_transcript(id, db, force=True),
    "meeting": lambda id, db: index_meeting(id, db, force=True),
    "contact": lambda id, db: index_contact(id, db, force=True),
    "journal": lambda id, db: index_journal(id, db, force=True),
    "reflection": lambda id, db: index_reflection(id, db, force=True),
    "task": lambda id, db: index_task(id, db, force=True),
    "calendar": lambda id, db: index_calendar_event(id, db, force=True),
    "application": lambda id, db: index_application(id, db, force=True),
    "document": lambda id, db: index_document(id, db, force=True),
    "email": lambda id, db: index_email(id, db, force=True),
    "book": lambda id, db: index_book(id, db, force=True),
    "highlight": lambda id, db: index_highlight(id, db, force=True),
    "linkedin_post": lambda id, db: index_linkedin_post(id, db, force=True),
    "beeper_message": lambda id, db: index_beeper_message(id, db, force=True),
}


async def reindex_all(
    source_types: List[str] = None,
    db = None,
    limit: int = None
) -> Dict[str, Dict[str, int]]:
    """
    Reindex all content of specified types.
    
    Use this for initial indexing or after schema changes.
    
    Args:
        source_types: Which types to reindex (default: all main content)
        db: Database client
        limit: Max records per type (for testing)
    
    Returns:
        Dict mapping source_type to {indexed: N, errors: N}
    """
    if db is None:
        from app.services.database import SupabaseMultiDatabase
        db = SupabaseMultiDatabase()
    
    # Default to main content types for daily RAG indexing
    # Note: books/highlights excluded (not useful), beeper_messages included
    source_types = source_types or [
        "transcript", "meeting", "journal", "reflection", 
        "contact", "calendar", "application", "document",
        "email", "linkedin_post", "beeper_message"
    ]
    
    results = {}
    
    for source_type in source_types:
        logger.info(f"Reindexing {source_type}...")
        
        table_name = TABLE_NAME_MAP.get(source_type)
        index_func = INDEX_FUNCTION_MAP.get(source_type)
        
        if not table_name or not index_func:
            logger.warning(f"No indexer for type: {source_type}")
            results[source_type] = {"indexed": 0, "errors": 1}
            continue
        
        try:
            # Get records
            query = db.client.table(table_name).select("id")
            if limit:
                query = query.limit(limit)
            records = query.execute()
            
            if not records.data:
                results[source_type] = {"indexed": 0, "errors": 0}
                continue
            
            total_indexed = 0
            total_errors = 0
            
            for record in records.data:
                try:
                    count = await index_func(record["id"], db)
                    total_indexed += count
                except Exception as e:
                    logger.error(f"Error indexing {source_type} {record['id']}: {e}")
                    total_errors += 1
            
            results[source_type] = {"indexed": total_indexed, "errors": total_errors}
            logger.info(f"Indexed {total_indexed} chunks from {len(records.data)} {source_type}s ({total_errors} errors)")
            
        except Exception as e:
            logger.error(f"Failed to reindex {source_type}: {e}")
            results[source_type] = {"indexed": 0, "errors": 1}
    
    logger.info(f"Reindex complete: {results}")
    return results
