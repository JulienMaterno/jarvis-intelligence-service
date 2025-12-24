-- Migration: Add scheduled_briefings table
-- Date: 2025-01-XX
-- Purpose: Support hourly scheduling of meeting briefings with 15-min lead time

-- Create scheduled_briefings table
CREATE TABLE IF NOT EXISTS scheduled_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL,
    event_title TEXT,
    event_start TIMESTAMPTZ,
    send_at TIMESTAMPTZ NOT NULL,
    briefing_text TEXT NOT NULL,
    contact_id UUID REFERENCES contacts(id),
    contact_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, sent, failed
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Indexes for common queries
    CONSTRAINT valid_status CHECK (status IN ('pending', 'sent', 'failed'))
);

-- Index for finding due briefings (run every minute)
CREATE INDEX IF NOT EXISTS idx_scheduled_briefings_pending 
ON scheduled_briefings(send_at, status) 
WHERE status = 'pending';

-- Index for finding existing scheduled briefings for an event
CREATE INDEX IF NOT EXISTS idx_scheduled_briefings_event 
ON scheduled_briefings(event_id, status);

-- Index for cleanup of old briefings
CREATE INDEX IF NOT EXISTS idx_scheduled_briefings_created 
ON scheduled_briefings(created_at);

-- Comment
COMMENT ON TABLE scheduled_briefings IS 'Pre-generated meeting briefings scheduled for delivery 15 min before meetings';

-- Grant access (adjust based on your setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON scheduled_briefings TO service_role;
