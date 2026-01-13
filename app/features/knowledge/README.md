# Knowledge System (RAG)

## Overview

This module provides Retrieval Augmented Generation (RAG) capabilities across ALL Jarvis data sources.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE SYSTEM                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Transcripts │  │  Meetings   │  │  Messages   │  │  Contacts   │             │
│  │             │  │  Journals   │  │  (Beeper)   │  │  Calendar   │             │
│  │             │  │ Reflections │  │             │  │   Tasks     │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                │                     │
│         └────────────────┴────────────────┴────────────────┘                     │
│                                   │                                              │
│                                   ▼                                              │
│                    ┌──────────────────────────────┐                              │
│                    │     Indexing Service         │                              │
│                    │  - Detects content type      │                              │
│                    │  - Applies chunking strategy │                              │
│                    │  - Generates embeddings      │                              │
│                    │  - Stores in knowledge_chunks│                              │
│                    └──────────────────────────────┘                              │
│                                   │                                              │
│                                   ▼                                              │
│                    ┌──────────────────────────────┐                              │
│                    │      knowledge_chunks        │  (pgvector)                  │
│                    │  - source_type               │                              │
│                    │  - source_id                 │                              │
│                    │  - content                   │                              │
│                    │  - embedding (vector 1536)   │                              │
│                    │  - metadata (JSONB)          │                              │
│                    └──────────────────────────────┘                              │
│                                   │                                              │
│                                   ▼                                              │
│                    ┌──────────────────────────────┐                              │
│                    │     Retrieval Service        │                              │
│                    │  - Semantic search           │                              │
│                    │  - Hybrid search (+ keyword) │                              │
│                    │  - Filter by source type     │                              │
│                    │  - Filter by date range      │                              │
│                    │  - Filter by person/contact  │                              │
│                    └──────────────────────────────┘                              │
│                                   │                                              │
│                                   ▼                                              │
│                    ┌──────────────────────────────┐                              │
│                    │      Context Builder         │                              │
│                    │  - Assembles relevant chunks │                              │
│                    │  - Ranks by relevance        │                              │
│                    │  - Formats for LLM           │                              │
│                    │  - Respects token limits     │                              │
│                    └──────────────────────────────┘                              │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Chunking Strategies

### 1. Transcript Chunking
- Use WhisperX segments as natural boundaries
- Target: ~500 tokens per chunk
- Preserve speaker information
- Include timestamp metadata

### 2. Document Chunking (Journals, Reflections)
- Use paragraph/section boundaries
- Target: ~400 tokens per chunk
- Preserve section headers

### 3. Message Chunking (Beeper)
- Group messages by conversation window (e.g., 10 messages)
- Or embed individual messages for short ones
- Include sender/recipient metadata

### 4. Structured Data (Contacts, Tasks, Calendar)
- Format as natural language text
- Embed as single chunk (usually small enough)

## Usage

### Indexing (when data is created)
```python
from app.features.knowledge import index_content

# Automatically detects type and applies correct chunking
await index_content(
    source_type="transcript",
    source_id="42946a06-...",
    content=transcript_text,
    metadata={"speaker": "Jonas", "language": "de"}
)
```

### Retrieval (when answering questions)
```python
from app.features.knowledge import retrieve_context

# Get relevant chunks for a query
chunks = await retrieve_context(
    query="What did Jonas say about BCG?",
    source_types=["transcript", "meeting"],  # Optional filter
    contact_id="...",  # Optional: filter by person
    limit=10
)
```

### For Background Agents
```python
from app.features.knowledge import KnowledgeService

# Agents get a knowledge service instance
knowledge = KnowledgeService()

# Search across all data
results = await knowledge.search("Vietnam travel plans")

# Get context for a specific contact
contact_context = await knowledge.get_contact_context(contact_id)

# Get recent context (last 7 days)
recent = await knowledge.get_recent_context(days=7)
```

## Database Schema

See: `migrations/016_add_knowledge_chunks.sql`
