-- Migration: Add pending_clarifications table
-- This stores questions the AI needs answered to complete analysis

CREATE TABLE IF NOT EXISTS pending_clarifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT NOT NULL,              -- Telegram user ID
    chat_id BIGINT NOT NULL,              -- Telegram chat ID for responses
    item TEXT NOT NULL,                   -- What needs clarification (e.g., "Other Person's Identity")
    question TEXT NOT NULL,               -- The question to ask user
    context JSONB DEFAULT '{}',           -- Additional context from analysis
    record_type TEXT,                     -- 'meeting', 'reflection', 'transcript', etc.
    record_id UUID,                       -- ID of the record needing clarification
    source_transcript_id UUID,            -- Original transcript ID
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'resolved', 'skipped', 'expired')),
    answer TEXT,                          -- User's answer once provided
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours'
);

-- Index for fast lookup of pending clarifications by user
CREATE INDEX IF NOT EXISTS idx_pending_clarifications_user 
    ON pending_clarifications(user_id, status, created_at DESC);

-- Index for finding clarifications by record
CREATE INDEX IF NOT EXISTS idx_pending_clarifications_record 
    ON pending_clarifications(record_type, record_id);

-- Add comment
COMMENT ON TABLE pending_clarifications IS 'Stores questions the AI needs user to answer for better analysis';
