-- ============================================================================
-- Migration: Add search indexes for improved query performance
-- Created: 2026-01-10
-- ============================================================================

-- Applications table indexes
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_type ON applications(application_type);
CREATE INDEX IF NOT EXISTS idx_applications_deadline ON applications(deadline);
CREATE INDEX IF NOT EXISTS idx_applications_name_trgm ON applications USING gin(name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_applications_institution_trgm ON applications USING gin(institution gin_trgm_ops);

-- LinkedIn Posts table indexes
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_status ON linkedin_posts(status);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_pillar ON linkedin_posts(pillar);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_post_date ON linkedin_posts(post_date DESC);
CREATE INDEX IF NOT EXISTS idx_linkedin_posts_title_trgm ON linkedin_posts USING gin(title gin_trgm_ops);

-- Contacts table (for search_contacts performance)
CREATE INDEX IF NOT EXISTS idx_contacts_first_name_trgm ON contacts USING gin(first_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_last_name_trgm ON contacts USING gin(last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_company_trgm ON contacts USING gin(company gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_contacts_deleted_at ON contacts(deleted_at) WHERE deleted_at IS NULL;

-- Meetings table indexes
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(date DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_contact_id ON meetings(contact_id);
CREATE INDEX IF NOT EXISTS idx_meetings_title_trgm ON meetings USING gin(title gin_trgm_ops);

-- Tasks table indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);

-- Reflections table indexes
CREATE INDEX IF NOT EXISTS idx_reflections_topic_key ON reflections(topic_key);
CREATE INDEX IF NOT EXISTS idx_reflections_deleted_at ON reflections(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_reflections_title_trgm ON reflections USING gin(title gin_trgm_ops);

-- Journals table indexes
CREATE INDEX IF NOT EXISTS idx_journals_date ON journals(date DESC);

-- Emails table indexes (for search_emails_live performance)
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date DESC);
CREATE INDEX IF NOT EXISTS idx_emails_contact_id ON emails(contact_id);
CREATE INDEX IF NOT EXISTS idx_emails_subject_trgm ON emails USING gin(subject gin_trgm_ops);

-- Calendar events indexes
CREATE INDEX IF NOT EXISTS idx_calendar_events_start_time ON calendar_events(start_time);
CREATE INDEX IF NOT EXISTS idx_calendar_events_contact_id ON calendar_events(contact_id);

-- Beeper messages indexes (for chat search)
CREATE INDEX IF NOT EXISTS idx_beeper_messages_timestamp ON beeper_messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_beeper_messages_chat_id ON beeper_messages(beeper_chat_id);

-- NOTE: Trigram indexes require the pg_trgm extension
-- Run this first if not already enabled:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- To verify indexes were created:
-- SELECT indexname FROM pg_indexes WHERE tablename IN ('applications', 'linkedin_posts', 'contacts', 'meetings', 'tasks');
