-- Memory table for AI memory system (Supabase-native)
-- Replaces Mem0 + Qdrant with simple Supabase storage
-- Uses pgvector for semantic search OR simple text search

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Core content
    memory TEXT NOT NULL,  -- The memory text itself
    memory_type TEXT DEFAULT 'fact',  -- fact, interaction, insight, preference, relationship
    
    -- Metadata
    user_id TEXT DEFAULT 'aaron',
    source TEXT,  -- Where this memory came from: chat, transcript, beeper, manual
    source_id TEXT,  -- ID of the source (transcript_id, message_id, etc.)
    category TEXT,  -- Optional category for grouping
    confidence FLOAT DEFAULT 1.0,  -- How confident we are (0-1)
    
    -- For vector search (optional - can use text search instead)
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ,  -- Track when memory was last used
    
    -- Soft delete
    deleted_at TIMESTAMPTZ
);

-- Indexes for fast querying
CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_deleted ON memories(deleted_at) WHERE deleted_at IS NULL;

-- Full text search index (works without embeddings!)
CREATE INDEX IF NOT EXISTS idx_memories_text_search 
    ON memories USING GIN(to_tsvector('english', memory));

-- Vector search index (if using embeddings)
CREATE INDEX IF NOT EXISTS idx_memories_embedding 
    ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- RLS
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role has full access to memories"
    ON memories
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_memories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memories_updated_at
    BEFORE UPDATE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION update_memories_updated_at();

-- Helper function for text search
CREATE OR REPLACE FUNCTION search_memories_text(
    search_query TEXT,
    limit_count INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    memory TEXT,
    memory_type TEXT,
    source TEXT,
    relevance FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        m.id,
        m.memory,
        m.memory_type,
        m.source,
        ts_rank(to_tsvector('english', m.memory), plainto_tsquery('english', search_query))::FLOAT as relevance
    FROM memories m
    WHERE 
        m.deleted_at IS NULL
        AND to_tsvector('english', m.memory) @@ plainto_tsquery('english', search_query)
    ORDER BY relevance DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Comments
COMMENT ON TABLE memories IS 'AI memory storage - facts, interactions, insights about the user';
COMMENT ON COLUMN memories.memory IS 'The actual memory text';
COMMENT ON COLUMN memories.embedding IS 'Optional vector embedding for semantic search';
COMMENT ON COLUMN memories.source IS 'Where this memory came from: chat, transcript, beeper, manual';
