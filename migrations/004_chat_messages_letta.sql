-- Migration: Create chat_messages table for raw message storage
-- This stores EVERY message exchanged, providing a complete audit log
-- Letta will process these for episodic memory extraction

-- Drop existing table if it exists (for clean migration)
DROP TABLE IF EXISTS chat_messages CASCADE;

-- Raw message storage
CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Session grouping (optional, for multi-turn conversations)
    session_id UUID,
    
    -- Message content
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    
    -- Source tracking
    source TEXT DEFAULT 'telegram' CHECK (source IN ('telegram', 'web', 'api', 'voice')),
    
    -- Additional context
    metadata JSONB DEFAULT '{}',  -- tool_calls, attachments, model_used, etc.
    
    -- Letta processing status
    letta_processed BOOLEAN DEFAULT FALSE,
    letta_processed_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT content_not_empty CHECK (length(trim(content)) > 0)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages(role);
CREATE INDEX IF NOT EXISTS idx_chat_messages_letta_pending ON chat_messages(letta_processed) WHERE NOT letta_processed;

-- Enable RLS (Row Level Security)
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

-- Policy: Service role can do everything
CREATE POLICY "Service role full access" ON chat_messages
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Comment for documentation
COMMENT ON TABLE chat_messages IS 'Raw storage of all chat messages. Every message is stored here for audit and Letta processing.';
COMMENT ON COLUMN chat_messages.session_id IS 'Groups messages into logical sessions (e.g., one Telegram conversation)';
COMMENT ON COLUMN chat_messages.metadata IS 'JSON: tool_calls, attachments, model_used, tokens, latency_ms, etc.';
COMMENT ON COLUMN chat_messages.letta_processed IS 'Whether Letta has processed this message for episodic memory';

-- ============================================================================
-- Letta-related tables for local caching (optional - Letta has its own storage)
-- ============================================================================

-- Cache of Letta memory blocks (for faster access without API calls)
DROP TABLE IF EXISTS letta_memory_cache CASCADE;
CREATE TABLE letta_memory_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    block_label TEXT NOT NULL,
    block_value TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(agent_id, block_label)
);

-- Topics extracted from conversations (searchable index)
DROP TABLE IF EXISTS conversation_topics CASCADE;
CREATE TABLE conversation_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_name TEXT NOT NULL,
    topic_summary TEXT,
    first_discussed DATE,
    last_discussed DATE,
    discussion_count INT DEFAULT 1,
    related_message_ids UUID[],  -- References to chat_messages
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversation_topics_name ON conversation_topics(topic_name);
CREATE INDEX IF NOT EXISTS idx_conversation_topics_last ON conversation_topics(last_discussed DESC);

-- Full-text search on topics
CREATE INDEX IF NOT EXISTS idx_conversation_topics_fts ON conversation_topics 
    USING gin(to_tsvector('english', topic_name || ' ' || COALESCE(topic_summary, '')));

COMMENT ON TABLE conversation_topics IS 'Topics extracted by Letta from conversations. Cumulative knowledge base.';
