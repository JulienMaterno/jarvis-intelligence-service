"""
Chunking strategies for different content types.

The goal of chunking is to:
1. Keep chunks small enough for good retrieval precision (~500 tokens)
2. Preserve semantic boundaries (don't cut mid-sentence)
3. Include relevant metadata for each chunk
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.Knowledge.Chunker")

# Approximate tokens (1 token ≈ 4 chars for English, 2-3 for German)
TARGET_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
CHARS_PER_TOKEN = 4  # Conservative estimate


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    return len(text) // CHARS_PER_TOKEN


def content_hash(text: str) -> str:
    """Generate hash for deduplication."""
    return hashlib.md5(text.encode()).hexdigest()


def chunk_transcript(
    full_text: str,
    segments: List[Dict[str, Any]] = None,
    source_id: str = None,
    language: str = "en",
    speaker_info: Dict[str, str] = None
) -> List[Dict[str, Any]]:
    """
    Chunk a transcript into semantically meaningful pieces.
    
    Strategy:
    1. If segments available, use them as natural boundaries
    2. Group segments until we hit target token count
    3. Include timestamp and speaker metadata
    
    Args:
        full_text: The complete transcript text
        segments: WhisperX segments with start/end times (optional)
        source_id: UUID of the source transcript
        language: Detected language
        speaker_info: Dict mapping speaker IDs to names
    
    Returns:
        List of chunk dicts with content, metadata, and hash
    """
    chunks = []
    
    if segments and len(segments) > 0:
        # Use segments for natural chunking
        chunks = _chunk_by_segments(segments, speaker_info, source_id)
    else:
        # Fall back to paragraph-based chunking
        chunks = _chunk_by_paragraphs(full_text, source_id)
    
    # Add language to all chunks
    for chunk in chunks:
        chunk["metadata"]["language"] = language
    
    logger.info(f"Chunked transcript {source_id} into {len(chunks)} chunks")
    return chunks


def _chunk_by_segments(
    segments: List[Dict[str, Any]],
    speaker_info: Dict[str, str] = None,
    source_id: str = None
) -> List[Dict[str, Any]]:
    """Group segments into chunks of ~500 tokens."""
    chunks = []
    current_texts = []
    current_tokens = 0
    current_start = None
    current_speakers = set()
    
    speaker_info = speaker_info or {}
    
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        
        seg_tokens = estimate_tokens(text)
        speaker = seg.get("speaker", "")
        speaker_name = speaker_info.get(speaker, speaker)
        
        # Track first segment's start time
        if current_start is None:
            current_start = seg.get("start", 0)
        
        # Check if adding this segment exceeds limit
        if current_tokens + seg_tokens > MAX_CHUNK_TOKENS and current_texts:
            # Save current chunk
            chunk_content = " ".join(current_texts)
            chunks.append({
                "content": chunk_content,
                "content_hash": content_hash(chunk_content),
                "chunk_index": len(chunks),
                "metadata": {
                    "timestamp_start": current_start,
                    "timestamp_end": seg.get("start", current_start),
                    "speakers": list(current_speakers),
                    "segment_count": len(current_texts)
                }
            })
            # Reset
            current_texts = []
            current_tokens = 0
            current_start = seg.get("start", 0)
            current_speakers = set()
        
        # Add segment
        current_texts.append(text)
        current_tokens += seg_tokens
        if speaker_name:
            current_speakers.add(speaker_name)
    
    # Don't forget the last chunk
    if current_texts:
        chunk_content = " ".join(current_texts)
        chunks.append({
            "content": chunk_content,
            "content_hash": content_hash(chunk_content),
            "chunk_index": len(chunks),
            "metadata": {
                "timestamp_start": current_start,
                "timestamp_end": segments[-1].get("end", current_start) if segments else current_start,
                "speakers": list(current_speakers),
                "segment_count": len(current_texts)
            }
        })
    
    return chunks


def _chunk_by_paragraphs(
    text: str,
    source_id: str = None
) -> List[Dict[str, Any]]:
    """Fall back: chunk by paragraphs/sentences."""
    chunks = []
    
    # Split by double newlines (paragraphs) or sentences
    paragraphs = re.split(r'\n\n+', text)
    
    current_texts = []
    current_tokens = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_tokens = estimate_tokens(para)
        
        # If single paragraph exceeds max, split by sentences
        if para_tokens > MAX_CHUNK_TOKENS:
            # Save current if any
            if current_texts:
                chunk_content = "\n\n".join(current_texts)
                chunks.append({
                    "content": chunk_content,
                    "content_hash": content_hash(chunk_content),
                    "chunk_index": len(chunks),
                    "metadata": {}
                })
                current_texts = []
                current_tokens = 0
            
            # Split long paragraph
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sent in sentences:
                sent_tokens = estimate_tokens(sent)
                if current_tokens + sent_tokens > MAX_CHUNK_TOKENS and current_texts:
                    chunk_content = " ".join(current_texts)
                    chunks.append({
                        "content": chunk_content,
                        "content_hash": content_hash(chunk_content),
                        "chunk_index": len(chunks),
                        "metadata": {}
                    })
                    current_texts = []
                    current_tokens = 0
                current_texts.append(sent)
                current_tokens += sent_tokens
        else:
            # Normal paragraph
            if current_tokens + para_tokens > MAX_CHUNK_TOKENS and current_texts:
                chunk_content = "\n\n".join(current_texts)
                chunks.append({
                    "content": chunk_content,
                    "content_hash": content_hash(chunk_content),
                    "chunk_index": len(chunks),
                    "metadata": {}
                })
                current_texts = []
                current_tokens = 0
            current_texts.append(para)
            current_tokens += para_tokens
    
    # Last chunk
    if current_texts:
        chunk_content = "\n\n".join(current_texts)
        chunks.append({
            "content": chunk_content,
            "content_hash": content_hash(chunk_content),
            "chunk_index": len(chunks),
            "metadata": {}
        })
    
    return chunks


def chunk_document(
    content: str,
    source_type: str,
    source_id: str = None,
    title: str = None,
    date: str = None,
    tags: List[str] = None
) -> List[Dict[str, Any]]:
    """
    Chunk a document (journal, reflection, etc.).
    
    For shorter documents (<800 tokens), returns single chunk.
    For longer documents, splits by sections/paragraphs.
    """
    tokens = estimate_tokens(content)
    
    base_metadata = {
        "title": title,
        "date": date,
        "tags": tags or []
    }
    
    # Short document - single chunk
    if tokens <= MAX_CHUNK_TOKENS:
        return [{
            "content": content,
            "content_hash": content_hash(content),
            "chunk_index": 0,
            "metadata": base_metadata
        }]
    
    # Longer document - use paragraph chunking
    chunks = _chunk_by_paragraphs(content, source_id)
    
    # Add base metadata to all chunks
    for chunk in chunks:
        chunk["metadata"].update(base_metadata)
    
    logger.info(f"Chunked {source_type} {source_id} into {len(chunks)} chunks")
    return chunks


def chunk_messages(
    messages: List[Dict[str, Any]],
    conversation_id: str = None,
    platform: str = None,
    contact_id: str = None,
    contact_name: str = None,
    window_size: int = 10
) -> List[Dict[str, Any]]:
    """
    Chunk messages into conversation windows.
    
    Strategy:
    1. Group messages into windows of N messages
    2. Each window becomes one chunk
    3. Include sender info in the text
    
    Args:
        messages: List of message dicts with content, is_outgoing, timestamp
        conversation_id: Beeper chat ID
        platform: 'whatsapp', 'linkedin', etc.
        contact_id: Related contact UUID
        contact_name: Contact's name
        window_size: How many messages per chunk
    
    Returns:
        List of chunk dicts
    """
    chunks = []
    
    if not messages:
        return chunks
    
    # Sort by timestamp
    sorted_msgs = sorted(messages, key=lambda m: m.get("timestamp", ""))
    
    # Process in windows
    for i in range(0, len(sorted_msgs), window_size):
        window = sorted_msgs[i:i + window_size]
        
        # Format messages as conversation text
        lines = []
        for msg in window:
            sender = "Me" if msg.get("is_outgoing") else (contact_name or "Them")
            text = msg.get("content", "").strip()
            if text:
                lines.append(f"{sender}: {text}")
        
        if not lines:
            continue
        
        content = "\n".join(lines)
        
        # Get time range
        first_ts = window[0].get("timestamp")
        last_ts = window[-1].get("timestamp")
        
        chunks.append({
            "content": content,
            "content_hash": content_hash(content),
            "chunk_index": len(chunks),
            "metadata": {
                "platform": platform,
                "contact_id": contact_id,
                "contact_name": contact_name,
                "conversation_id": conversation_id,
                "message_count": len(window),
                "timestamp_start": first_ts,
                "timestamp_end": last_ts
            }
        })
    
    logger.info(f"Chunked {len(messages)} messages into {len(chunks)} chunks")
    return chunks


def chunk_contact(contact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a contact as a single chunk.
    
    Contacts are usually small, so we embed the whole profile.
    """
    lines = []
    
    name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    if name:
        lines.append(f"Name: {name}")
    
    if contact.get("company"):
        lines.append(f"Company: {contact['company']}")
    
    if contact.get("job_title"):
        lines.append(f"Job Title: {contact['job_title']}")
    
    if contact.get("email"):
        lines.append(f"Email: {contact['email']}")
    
    if contact.get("location"):
        lines.append(f"Location: {contact['location']}")
    
    if contact.get("notes"):
        lines.append(f"Notes: {contact['notes']}")
    
    # Include relationship context if available
    if contact.get("dynamic_properties"):
        props = contact["dynamic_properties"]
        if props.get("relationship"):
            lines.append(f"Relationship: {props['relationship']}")
        if props.get("how_met"):
            lines.append(f"How Met: {props['how_met']}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "contact_id": contact.get("id"),
            "contact_name": name,
            "company": contact.get("company"),
            "is_contact_profile": True
        }
    }


def chunk_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Format a task as a single chunk."""
    lines = [f"Task: {task.get('title', 'Untitled')}"]
    
    if task.get("description"):
        lines.append(f"Description: {task['description']}")
    
    if task.get("status"):
        lines.append(f"Status: {task['status']}")
    
    if task.get("due_date"):
        lines.append(f"Due: {task['due_date']}")
    
    if task.get("project"):
        lines.append(f"Project: {task['project']}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "status": task.get("status"),
            "due_date": task.get("due_date"),
            "project": task.get("project"),
            "priority": task.get("priority")
        }
    }


def chunk_calendar_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Format a calendar event as a single chunk."""
    lines = [f"Event: {event.get('summary', 'Untitled Event')}"]
    
    if event.get("start_time"):
        lines.append(f"When: {event['start_time']}")
    
    if event.get("location"):
        lines.append(f"Location: {event['location']}")
    
    if event.get("description"):
        # Truncate long descriptions
        desc = event["description"][:500]
        lines.append(f"Description: {desc}")
    
    if event.get("attendees"):
        attendee_names = [a.get("email", "") for a in event["attendees"][:5]]
        lines.append(f"Attendees: {', '.join(attendee_names)}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "date": event.get("start_time"),
            "location": event.get("location"),
            "attendee_count": len(event.get("attendees", [])),
            "google_event_id": event.get("google_event_id")
        }
    }


def chunk_application(app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk an application record.
    
    Applications can have long content (questions/answers), so we chunk if needed.
    """
    # Build searchable text from all fields
    lines = [f"Application: {app.get('name', 'Untitled')}"]
    
    if app.get("institution"):
        lines.append(f"Institution: {app['institution']}")
    
    if app.get("application_type"):
        lines.append(f"Type: {app['application_type']}")
    
    if app.get("status"):
        lines.append(f"Status: {app['status']}")
    
    if app.get("deadline"):
        lines.append(f"Deadline: {app['deadline']}")
    
    if app.get("grant_amount"):
        lines.append(f"Grant Amount: {app['grant_amount']}")
    
    if app.get("context"):
        lines.append(f"Context: {app['context']}")
    
    if app.get("notes"):
        lines.append(f"Notes: {app['notes']}")
    
    header_content = "\n".join(lines)
    
    # If there's long content (questions/answers), add it and chunk if needed
    full_content = app.get("content", "")
    if full_content:
        combined = f"{header_content}\n\n{full_content}"
    else:
        combined = header_content
    
    # Check if chunking is needed
    tokens = estimate_tokens(combined)
    
    if tokens <= MAX_CHUNK_TOKENS:
        return [{
            "content": combined,
            "content_hash": content_hash(combined),
            "chunk_index": 0,
            "metadata": {
                "application_type": app.get("application_type"),
                "status": app.get("status"),
                "institution": app.get("institution"),
                "deadline": app.get("deadline")
            }
        }]
    
    # Need to chunk - use paragraph chunking on the content
    chunks = _chunk_by_paragraphs(combined, app.get("id"))
    
    # Add metadata to all chunks
    for chunk in chunks:
        chunk["metadata"].update({
            "application_type": app.get("application_type"),
            "status": app.get("status"),
            "institution": app.get("institution"),
            "deadline": app.get("deadline")
        })
    
    return chunks


def chunk_linkedin_post(post: Dict[str, Any]) -> Dict[str, Any]:
    """Format a LinkedIn post as a single chunk."""
    lines = [f"LinkedIn Post: {post.get('title', 'Untitled')}"]
    
    if post.get("post_date"):
        lines.append(f"Date: {post['post_date']}")
    
    if post.get("status"):
        lines.append(f"Status: {post['status']}")
    
    if post.get("pillar"):
        lines.append(f"Pillar: {post['pillar']}")
    
    if post.get("content"):
        lines.append(f"\n{post['content']}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "date": post.get("post_date"),
            "status": post.get("status"),
            "pillar": post.get("pillar")
        }
    }


def chunk_book(book: Dict[str, Any]) -> Dict[str, Any]:
    """Format a book record as a single chunk."""
    lines = [f"Book: {book.get('title', 'Untitled')}"]
    
    if book.get("author"):
        lines.append(f"Author: {book['author']}")
    
    if book.get("status"):
        lines.append(f"Status: {book['status']}")
    
    if book.get("my_rating"):
        lines.append(f"My Rating: {book['my_rating']}")
    
    if book.get("my_review"):
        lines.append(f"My Review: {book['my_review']}")
    
    if book.get("notes"):
        lines.append(f"Notes: {book['notes']}")
    
    if book.get("key_takeaways"):
        lines.append(f"Key Takeaways: {book['key_takeaways']}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "author": book.get("author"),
            "status": book.get("status"),
            "rating": book.get("my_rating")
        }
    }


def chunk_highlight(highlight: Dict[str, Any], book_title: str = None) -> Dict[str, Any]:
    """Format a book highlight as a single chunk."""
    lines = []
    
    if book_title:
        lines.append(f"Highlight from: {book_title}")
    
    if highlight.get("highlight_text"):
        lines.append(f'"{highlight["highlight_text"]}"')
    
    if highlight.get("note"):
        lines.append(f"My Note: {highlight['note']}")
    
    if highlight.get("chapter"):
        lines.append(f"Chapter: {highlight['chapter']}")
    
    content = "\n".join(lines)
    
    return {
        "content": content,
        "content_hash": content_hash(content),
        "chunk_index": 0,
        "metadata": {
            "book_id": highlight.get("book_id"),
            "book_title": book_title,
            "chapter": highlight.get("chapter")
        }
    }
