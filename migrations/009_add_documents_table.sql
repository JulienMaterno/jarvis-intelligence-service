-- Documents table for storing personal documents (CV, profiles, etc.)
-- Created: 2025-01-XX
-- 
-- This table stores:
-- - Extracted text content (for search and AI context)
-- - Optional file URL for actual file storage (GCS)
-- - Metadata and type classification

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Core content
    title TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'other',  -- cv, profile, application, notes, other
    content TEXT,  -- Extracted text content
    content_hash VARCHAR(16),  -- For deduplication
    
    -- File storage (optional)
    filename TEXT,  -- Original filename
    file_url TEXT,  -- GCS URL for the actual file
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    tags TEXT[] DEFAULT '{}',
    
    -- Stats
    word_count INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(type);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_tags ON documents USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

-- Full text search index on content
CREATE INDEX IF NOT EXISTS idx_documents_content_search 
    ON documents USING GIN(to_tsvector('english', COALESCE(content, '') || ' ' || COALESCE(title, '')));

-- Enable RLS (Row Level Security)
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- For service role, allow all operations
CREATE POLICY "Service role has full access to documents"
    ON documents
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Updated_at trigger
CREATE OR REPLACE FUNCTION update_documents_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_documents_updated_at();

-- Comments
COMMENT ON TABLE documents IS 'Personal documents storage (CV, profiles, applications, etc.)';
COMMENT ON COLUMN documents.content IS 'Extracted text content from document, used for search and AI context';
COMMENT ON COLUMN documents.file_url IS 'GCS URL for actual file (for email attachments, downloads)';
COMMENT ON COLUMN documents.content_hash IS 'First 16 chars of SHA256 hash of content, for deduplication';
