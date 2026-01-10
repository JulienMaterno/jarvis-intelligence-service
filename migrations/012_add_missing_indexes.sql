-- ============================================================================
-- Migration: Add missing indexes for idempotency and content search
-- Created: 2026-01-10
-- 
-- CRITICAL: These indexes prevent slowdown as database grows
-- ============================================================================

-- Enable pg_trgm if not already enabled
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================================
-- IDEMPOTENCY INDEXES - For transcript processing lookups
-- These columns are queried during every transcript analysis to check
-- if records already exist for a given transcript
-- ============================================================================

-- Meetings: Check if meeting already created from transcript
CREATE INDEX IF NOT EXISTS idx_meetings_source_transcript_id 
    ON meetings(source_transcript_id) 
    WHERE source_transcript_id IS NOT NULL;

-- Journals: Check if journal already created from transcript
CREATE INDEX IF NOT EXISTS idx_journals_source_transcript_id 
    ON journals(source_transcript_id) 
    WHERE source_transcript_id IS NOT NULL;

-- Reflections: Check if reflection already created from transcript
CREATE INDEX IF NOT EXISTS idx_reflections_source_transcript_id 
    ON reflections(source_transcript_id) 
    WHERE source_transcript_id IS NOT NULL;

-- Tasks: Check if task already created from origin
CREATE INDEX IF NOT EXISTS idx_tasks_origin_id 
    ON tasks(origin_id) 
    WHERE origin_id IS NOT NULL;

-- ============================================================================
-- CONTENT SEARCH INDEXES - For full-text search on large text fields
-- These enable fast ILIKE queries on content fields
-- ============================================================================

-- Reflections content search (currently missing, causes slow queries)
CREATE INDEX IF NOT EXISTS idx_reflections_content_trgm 
    ON reflections USING gin(content gin_trgm_ops);

-- Transcripts full_text search (for searching raw transcripts)
CREATE INDEX IF NOT EXISTS idx_transcripts_full_text_trgm 
    ON transcripts USING gin(full_text gin_trgm_ops);

-- Journals content search
CREATE INDEX IF NOT EXISTS idx_journals_content_trgm 
    ON journals USING gin(content gin_trgm_ops);

-- Meetings summary search
CREATE INDEX IF NOT EXISTS idx_meetings_summary_trgm 
    ON meetings USING gin(summary gin_trgm_ops);

-- ============================================================================
-- TIMESTAMP INDEXES - For time-based queries
-- ============================================================================

-- Transcripts by creation date (for recent transcript queries)
CREATE INDEX IF NOT EXISTS idx_transcripts_created_at 
    ON transcripts(created_at DESC);

-- Reflections by date
CREATE INDEX IF NOT EXISTS idx_reflections_date 
    ON reflections(date DESC);

-- ============================================================================
-- COMPOSITE INDEXES - For common multi-column queries
-- ============================================================================

-- Tasks by status and due date (common query pattern)
CREATE INDEX IF NOT EXISTS idx_tasks_status_due_date 
    ON tasks(status, due_date) 
    WHERE status != 'Done';

-- Meetings by contact and date (for contact history)
CREATE INDEX IF NOT EXISTS idx_meetings_contact_date 
    ON meetings(contact_id, date DESC) 
    WHERE contact_id IS NOT NULL;

-- Emails by contact and date (for contact history)
CREATE INDEX IF NOT EXISTS idx_emails_contact_date 
    ON emails(contact_id, date DESC) 
    WHERE contact_id IS NOT NULL;

-- ============================================================================
-- VERIFICATION QUERIES
-- Run these to verify indexes were created:
-- ============================================================================

-- SELECT indexname, tablename FROM pg_indexes 
-- WHERE indexname LIKE 'idx_%' 
-- ORDER BY tablename, indexname;

-- Check index sizes:
-- SELECT pg_size_pretty(pg_indexes_size('meetings')) as meetings_indexes;
