-- Migration: LinkedIn Connections Import Table
-- Purpose: Store raw LinkedIn connection data for reference and matching

-- Create linkedin_connections table to store raw import data
CREATE TABLE IF NOT EXISTS linkedin_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Raw data from LinkedIn export
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    linkedin_url TEXT NOT NULL UNIQUE,
    email TEXT,
    company TEXT,
    position TEXT,
    connected_on DATE,
    
    -- Matching status
    matched_contact_id UUID REFERENCES contacts(id),
    match_confidence TEXT,  -- 'exact', 'fuzzy', 'manual', 'unmatched'
    match_notes TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_linkedin_connections_name 
    ON linkedin_connections(lower(first_name), lower(last_name));
CREATE INDEX IF NOT EXISTS idx_linkedin_connections_url 
    ON linkedin_connections(linkedin_url);
CREATE INDEX IF NOT EXISTS idx_linkedin_connections_matched 
    ON linkedin_connections(matched_contact_id) WHERE matched_contact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_linkedin_connections_unmatched 
    ON linkedin_connections(id) WHERE matched_contact_id IS NULL;

-- Comment
COMMENT ON TABLE linkedin_connections IS 'Raw LinkedIn connections data imported from CSV export. Used to enrich contacts with LinkedIn URLs.';
