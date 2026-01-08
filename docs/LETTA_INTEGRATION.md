# Letta Integration Architecture

## Overview

This document describes the hybrid memory architecture integrating Letta with the existing Mem0-based system.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           JARVIS MEMORY ARCHITECTURE                              │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                   │
│  ┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────┐  │
│  │   MEM0 (Semantic)   │     │  LETTA (Episodic)    │     │   SUPABASE       │  │
│  │                     │     │                      │     │   (Raw Storage)  │  │
│  │  • Facts            │     │  • Conversation      │     │                  │  │
│  │  • Preferences      │     │    history           │     │  chat_messages:  │  │
│  │  • Relationships    │     │  • Self-editing      │     │  - All messages  │  │
│  │  • Insights         │     │    memory blocks     │     │  - Timestamps    │  │
│  │                     │     │  • Topic extraction  │     │  - Source        │  │
│  │  Query: Semantic    │     │  • Session summaries │     │                  │  │
│  │  Search (18 results)│     │                      │     │                  │  │
│  └─────────────────────┘     └──────────────────────┘     └──────────────────┘  │
│           │                           │                           │              │
│           └───────────────────────────┴───────────────────────────┘              │
│                                       │                                          │
│                              ┌────────▼────────┐                                 │
│                              │   CHAT SERVICE  │                                 │
│                              │                 │                                 │
│                              │  System Prompt: │                                 │
│                              │  • 18 Mem0 hits │                                 │
│                              │  • 3 journals   │                                 │
│                              │  • Letta context│                                 │
│                              │  • Tools        │                                 │
│                              └─────────────────┘                                 │
│                                                                                   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Raw Message Storage (Supabase)

**Table: `chat_messages`**
```sql
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID,                    -- Groups messages into sessions
    role TEXT NOT NULL,                 -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,              -- Message content
    source TEXT DEFAULT 'telegram',     -- 'telegram' | 'web' | 'api'
    metadata JSONB,                     -- Tool calls, attachments, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_created ON chat_messages(created_at);
```

**Purpose**: Complete audit log of every message. Never deleted.

### 2. Letta Agent (Episodic Memory)

**Deployment**: Google Cloud Run (same region as other services)

```yaml
# Cloud Run Service
Service: letta-server
Region: asia-southeast1
Memory: 2GB (Letta requires more RAM)
CPU: 2
Port: 8283
Image: letta/letta:latest
Environment:
  - LETTA_PG_URI: (Cloud SQL connection or Supabase pooler)
  - LETTA_SERVER_PASSWORD: (from Secret Manager)
```

**Why Cloud Run (not local)?**
- Consistent availability (not dependent on laptop being on)
- Same latency as other services
- Auto-scaling and managed infrastructure
- Secrets handled via Secret Manager

**Agent Configuration**:
```python
agent = client.agents.create(
    name="jarvis-memory",
    model="claude-sonnet-4-5-20250929",
    memory_blocks=[
        # Core memory - always in context
        {
            "label": "human",
            "value": "Aaron Pütting. 26yo German engineer. Building Jarvis.",
            "limit": 5000
        },
        {
            "label": "persona", 
            "value": "You are a memory management agent for Jarvis...",
            "limit": 2000
        },
        {
            "label": "recent_topics",
            "value": "",  # Self-edited: topics discussed recently
            "limit": 3000
        },
        {
            "label": "decisions",
            "value": "",  # Self-edited: decisions made
            "limit": 2000
        }
    ],
    tools=[
        "memory_replace",
        "memory_insert", 
        "memory_rethink",
        "archival_memory_insert",
        "archival_memory_search",
        "conversation_search"
    ]
)
```

**Key Features Used**:
- **Memory Blocks**: Always-in-context structured memory
- **Self-Editing**: Agent decides what to remember
- **Archival Memory**: Unlimited searchable storage for past conversations
- **Conversation Search**: Full-text + semantic search over history

### 3. Integration Flow

#### A. Real-time (Every Message)

```python
async def process_message(user_message: str, assistant_response: str):
    # 1. Store in raw database (always)
    await db.insert_chat_message(role="user", content=user_message)
    await db.insert_chat_message(role="assistant", content=assistant_response)
    
    # 2. Feed to Letta agent (for memory processing)
    # Letta decides what to remember in its blocks
    await letta_client.agents.messages.create(
        agent_id=LETTA_AGENT_ID,
        messages=[
            {"role": "user", "text": user_message},
            {"role": "assistant", "text": assistant_response}
        ]
    )
```

#### B. Daily Batch (Cloud Scheduler - Midnight)

```python
async def daily_memory_consolidation():
    # 1. Get today's messages from raw storage
    messages = await db.get_chat_messages(date=today)
    
    # 2. Ask Letta to summarize and extract
    summary = await letta_client.agents.messages.create(
        agent_id=LETTA_AGENT_ID,
        messages=[{
            "role": "user",
            "text": f"""
            Please review today's conversations and:
            1. Update your 'recent_topics' block with key topics discussed
            2. Update your 'decisions' block with any decisions made
            3. Archive important facts to archival memory
            4. Identify any patterns or insights worth remembering
            
            Today's conversations:
            {format_messages(messages)}
            """
        }]
    )
    
    # 3. Letta self-edits its memory blocks
    # No additional code needed - Letta handles this autonomously
```

### 4. Retrieval in Chat

```python
async def get_letta_context(query: str) -> str:
    """Get relevant context from Letta for a query."""
    
    # 1. Get Letta's current memory blocks (always in context)
    agent = await letta_client.agents.get(LETTA_AGENT_ID)
    memory_blocks = {b.label: b.value for b in agent.memory.blocks}
    
    # 2. Search archival memory for relevant past conversations
    archival_results = await letta_client.agents.archival_memory.search(
        agent_id=LETTA_AGENT_ID,
        query=query,
        limit=5
    )
    
    # 3. Format for system prompt
    context = f"""
    **CONVERSATION HISTORY (from Letta)**
    
    Recent Topics: {memory_blocks.get('recent_topics', 'None')}
    
    Recent Decisions: {memory_blocks.get('decisions', 'None')}
    
    Relevant Past Conversations:
    {format_archival(archival_results)}
    """
    
    return context
```

### 5. Updated System Prompt Structure

```
┌─────────────────────────────────────────┐
│           SYSTEM PROMPT                  │
├─────────────────────────────────────────┤
│ 1. Instructions (static)                │
│                                         │
│ 2. User Identity (minimal)              │
│    "Aaron Pütting"                      │
│                                         │
│ 3. Mem0 Semantic Memories (18)          │
│    • Facts, preferences, insights       │
│                                         │
│ 4. Letta Episodic Context               │
│    • Recent topics discussed            │
│    • Decisions made                     │
│    • Relevant past conversations        │
│                                         │
│ 5. Recent Journals (3)                  │
│    • Mood, energy, focus                │
│                                         │
│ 6. Available Tools                      │
│    • search_memories (Mem0)             │
│    • search_conversations (Letta)       │
│    • remember_fact (Mem0)               │
└─────────────────────────────────────────┘
```

## Deployment Options

### Option A: Self-Hosted Letta (Recommended)

```yaml
# docker-compose.yml addition
services:
  letta:
    image: letta/letta:latest
    ports:
      - "8283:8283"
    volumes:
      - letta_data:/var/lib/postgresql/data
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}  # For embeddings
      - SECURE=true
      - LETTA_SERVER_PASSWORD=${LETTA_PASSWORD}
    restart: unless-stopped

volumes:
  letta_data:
```

**Pros**: Full control, no additional costs, data stays local
**Cons**: Need to manage infrastructure

### Option B: Letta Cloud

Use Letta's managed service for zero ops overhead.

**Pros**: No infrastructure management
**Cons**: Additional cost, data leaves your infrastructure

## Implementation Plan

### Phase 1: Foundation (Week 1)
- [ ] Create `chat_messages` table in Supabase
- [ ] Update chat service to save all messages
- [ ] Deploy Letta Docker container
- [ ] Create initial Letta agent with memory blocks

### Phase 2: Integration (Week 2)
- [ ] Add Letta client to Intelligence Service
- [ ] Implement real-time message forwarding to Letta
- [ ] Add `search_conversations` tool to chat
- [ ] Update system prompt to include Letta context

### Phase 3: Optimization (Week 3)
- [ ] Add daily consolidation job (Cloud Scheduler)
- [ ] Fine-tune memory block sizes and prompts
- [ ] Add monitoring and logging
- [ ] Performance optimization

## Key Differences: Mem0 vs Letta

| Aspect | Mem0 | Letta |
|--------|------|-------|
| **Primary Use** | Semantic facts | Conversation history |
| **Storage** | Vector DB (pgvector) | Built-in PostgreSQL |
| **Retrieval** | Semantic search | Semantic + full-text |
| **Updates** | API calls | Self-editing agent |
| **Context** | Search results (18) | Memory blocks (always) |
| **Deduplication** | Automatic | Agent-managed |

## Why Both?

**Mem0** excels at:
- Permanent facts ("Aaron's email is...")
- Preferences ("Prefers direct communication")
- Relationships ("Alinta works in biochar")
- Profile data (the 121 memories we seeded)

**Letta** excels at:
- Conversation continuity ("Last time we discussed Antler...")
- Decision tracking ("You decided to...")
- Topic accumulation ("We've talked about FoodTech 5 times")
- Self-improving memory

**Together** they provide comprehensive memory that covers both **who you are** (Mem0) and **what you've discussed** (Letta).
