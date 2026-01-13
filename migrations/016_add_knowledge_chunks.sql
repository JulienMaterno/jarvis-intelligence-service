-- Migration: Add knowledge_chunks table for RAG
-- This is the unified vector store for all content types

-- Enable pgvector extension (should already exist from mem0)
CREATE EXTENSION IF NOT EXISTS vector;

-- Main chunks table
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source tracking (what this chunk came from)
    source_type TEXT NOT NULL,  -- 'transcript', 'meeting', 'journal', 'reflection', 'message', 'contact', 'task', 'calendar'
    source_id UUID NOT NULL,     -- ID of the source record
    chunk_index INTEGER DEFAULT 0,  -- For multi-chunk sources, which chunk is this
    
    -- Content
    content TEXT NOT NULL,       -- The actual text content
    content_hash TEXT,           -- For deduplication
    
    -- Vector embedding
    embedding vector(1536),      -- OpenAI ada-002 dimensions
    
    -- Rich metadata for filtering
    metadata JSONB DEFAULT '{}',
    -- Expected metadata fields:
    -- - contact_id: UUID (if related to a specific person)
    -- - contact_name: TEXT
    -- - date: DATE or TIMESTAMPTZ
    -- - speaker: TEXT (for transcripts)
    -- - timestamp_start: FLOAT (for audio segments)
    -- - timestamp_end: FLOAT
    -- - platform: TEXT (for beeper messages: 'whatsapp', 'linkedin', etc.)
    -- - direction: TEXT ('incoming', 'outgoing')
    -- - language: TEXT
    -- - tags: TEXT[]
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- For soft deletes when source is deleted
    deleted_at TIMESTAMPTZ
);

-- Index for vector similarity search (HNSW is faster for queries)
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding 
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- Index for filtering by source
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source 
    ON knowledge_chunks(source_type, source_id);

-- Index for filtering by contact
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_contact 
    ON knowledge_chunks((metadata->>'contact_id'));

-- Index for filtering by date
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_date 
    ON knowledge_chunks((metadata->>'date'));

-- Index for content deduplication
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_hash 
    ON knowledge_chunks(content_hash);

-- Composite index for common query pattern
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_type_date 
    ON knowledge_chunks(source_type, (metadata->>'date') DESC)
    WHERE deleted_at IS NULL;

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_knowledge_chunks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_knowledge_chunks_updated_at
    BEFORE UPDATE ON knowledge_chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_knowledge_chunks_updated_at();

-- Comment
COMMENT ON TABLE knowledge_chunks IS 'Unified vector store for RAG across all content types';

-- Helpful view for checking index status
CREATE OR REPLACE VIEW knowledge_stats AS
SELECT 
    source_type,
    COUNT(*) as chunk_count,
    COUNT(DISTINCT source_id) as source_count,
    MIN(created_at) as earliest,
    MAX(created_at) as latest
FROM knowledge_chunks
WHERE deleted_at IS NULL
GROUP BY source_type
ORDER BY chunk_count DESC;

COMMENT ON VIEW knowledge_stats IS 'Statistics about indexed content by source type';

-- Function for efficient vector similarity search
-- This is called by the retrieval service
CREATE OR REPLACE FUNCTION match_knowledge_chunks(
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    filter_source_types text[] DEFAULT NULL,
    filter_contact_id text DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    source_type text,
    source_id uuid,
    chunk_index int,
    content text,
    metadata jsonb,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kc.id,
        kc.source_type,
        kc.source_id,
        kc.chunk_index,
        kc.content,
        kc.metadata,
        1 - (kc.embedding <=> query_embedding) AS similarity
    FROM knowledge_chunks kc
    WHERE
        kc.deleted_at IS NULL
        AND 1 - (kc.embedding <=> query_embedding) > match_threshold
        AND (filter_source_types IS NULL OR kc.source_type = ANY(filter_source_types))
        AND (filter_contact_id IS NULL OR kc.metadata->>'contact_id' = filter_contact_id)
    ORDER BY kc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_knowledge_chunks IS 'Efficient vector similarity search with filtering';

