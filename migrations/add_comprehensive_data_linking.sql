-- ============================================================================
-- Comprehensive Data Linking Architecture for Jarvis Intelligence System
-- ============================================================================
-- Purpose: Create a fully interconnected data structure where all interactions
--          (meetings, emails, calendar events, etc.) link back to contacts
--          
-- This enables queries like:
-- "Show me everything about John Smith" -> meetings, emails, calendar events, etc.
-- ============================================================================

-- ============================================================================
-- PART 1: ENHANCE CONTACTS TABLE
-- ============================================================================

-- Add email field if it doesn't exist (for better matching)
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS email TEXT;

-- Add alternative emails for matching
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS alternative_emails TEXT[];

-- Add notes about interactions
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS interaction_summary TEXT;

-- Add last interaction date for tracking
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS last_interaction_date DATE;

-- Add interaction count for analytics
ALTER TABLE contacts 
ADD COLUMN IF NOT EXISTS total_interactions INTEGER DEFAULT 0;

-- Create index for email-based lookups
CREATE INDEX IF NOT EXISTS idx_contacts_email 
ON contacts(email) 
WHERE email IS NOT NULL AND deleted_at IS NULL;

-- Create index for name-based lookups (if not exists)
CREATE INDEX IF NOT EXISTS idx_contacts_names 
ON contacts(first_name, last_name) 
WHERE deleted_at IS NULL;

-- Add comment
COMMENT ON COLUMN contacts.email IS 'Primary email address for contact matching and communication';
COMMENT ON COLUMN contacts.alternative_emails IS 'Additional email addresses associated with this contact';
COMMENT ON COLUMN contacts.last_interaction_date IS 'Date of most recent interaction (meeting, email, etc.)';
COMMENT ON COLUMN contacts.total_interactions IS 'Total number of interactions with this contact';


-- ============================================================================
-- PART 2: CREATE EMAILS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Email Metadata
    message_id TEXT UNIQUE,  -- Unique email message ID from provider
    thread_id TEXT,          -- Email thread ID for grouping conversations
    subject TEXT NOT NULL,
    
    -- Content
    body_text TEXT,          -- Plain text body
    body_html TEXT,          -- HTML body (optional)
    snippet TEXT,            -- Short preview (first ~200 chars)
    
    -- Participants
    from_email TEXT NOT NULL,
    from_name TEXT,
    to_emails TEXT[] NOT NULL,  -- Array of recipient emails
    cc_emails TEXT[],           -- CC recipients
    bcc_emails TEXT[],          -- BCC recipients
    
    -- Contact Linking
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    contact_name TEXT,  -- Name extracted from email (before linking)
    
    -- Related Entities
    meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,  -- Link to related meeting
    
    -- Timestamps
    sent_at TIMESTAMP WITH TIME ZONE,
    received_at TIMESTAMP WITH TIME ZONE,
    
    -- Classification
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),  -- Received or sent
    category TEXT,  -- 'work', 'personal', 'newsletter', etc.
    tags TEXT[],
    
    -- Status
    is_read BOOLEAN DEFAULT false,
    is_starred BOOLEAN DEFAULT false,
    is_archived BOOLEAN DEFAULT false,
    
    -- Attachments
    has_attachments BOOLEAN DEFAULT false,
    attachment_count INTEGER DEFAULT 0,
    attachment_names TEXT[],
    
    -- Source
    source_provider TEXT,  -- 'gmail', 'outlook', 'manual', etc.
    raw_data JSONB,        -- Store raw email data for reference
    
    -- Sync tracking
    notion_page_id TEXT,
    notion_synced_at TIMESTAMP WITH TIME ZONE,
    last_sync_source TEXT DEFAULT 'supabase'
);

-- Create indexes for emails table
CREATE INDEX IF NOT EXISTS idx_emails_contact_id 
ON emails(contact_id) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_emails_from_email 
ON emails(from_email) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_emails_thread_id 
ON emails(thread_id) 
WHERE thread_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_emails_meeting_id 
ON emails(meeting_id) 
WHERE meeting_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_emails_sent_at 
ON emails(sent_at DESC) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_emails_subject 
ON emails USING gin(to_tsvector('english', subject)) 
WHERE deleted_at IS NULL;

-- Add comments
COMMENT ON TABLE emails IS 'Email communications linked to contacts and meetings';
COMMENT ON COLUMN emails.contact_id IS 'Primary contact associated with this email (sender for inbound, main recipient for outbound)';
COMMENT ON COLUMN emails.meeting_id IS 'Optional link to related meeting if email is follow-up or scheduling';
COMMENT ON COLUMN emails.thread_id IS 'Groups related emails in a conversation thread';


-- ============================================================================
-- PART 3: CREATE CALENDAR EVENTS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS calendar_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    deleted_at TIMESTAMP WITH TIME ZONE,
    
    -- Event Details
    title TEXT NOT NULL,
    description TEXT,
    location TEXT,
    
    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    all_day BOOLEAN DEFAULT false,
    timezone TEXT,
    
    -- Status
    status TEXT CHECK (status IN ('confirmed', 'tentative', 'cancelled')),
    
    -- Participants
    organizer_email TEXT,
    organizer_name TEXT,
    attendees JSONB,  -- Array of {email, name, response_status}
    
    -- Contact Linking
    contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
    contact_name TEXT,  -- Name extracted from calendar (before linking)
    
    -- Related Entities
    meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL,  -- Link to meeting notes after event
    email_id UUID REFERENCES emails(id) ON DELETE SET NULL,      -- Link to invitation email
    
    -- Recurrence
    is_recurring BOOLEAN DEFAULT false,
    recurrence_rule TEXT,  -- RRULE format
    recurrence_parent_id UUID REFERENCES calendar_events(id) ON DELETE CASCADE,
    
    -- Links
    meeting_url TEXT,  -- Zoom, Meet, Teams link
    conference_data JSONB,
    
    -- Classification
    event_type TEXT,  -- 'meeting', 'appointment', 'reminder', 'out_of_office', etc.
    tags TEXT[],
    
    -- Source
    source_provider TEXT,  -- 'google_calendar', 'outlook', 'manual', etc.
    source_event_id TEXT UNIQUE,  -- Original event ID from calendar provider
    raw_data JSONB,
    
    -- Sync tracking
    notion_page_id TEXT,
    notion_synced_at TIMESTAMP WITH TIME ZONE,
    last_sync_source TEXT DEFAULT 'supabase'
);

-- Create indexes for calendar_events table
CREATE INDEX IF NOT EXISTS idx_calendar_events_contact_id 
ON calendar_events(contact_id) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_meeting_id 
ON calendar_events(meeting_id) 
WHERE meeting_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_email_id 
ON calendar_events(email_id) 
WHERE email_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_start_time 
ON calendar_events(start_time DESC) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_organizer 
ON calendar_events(organizer_email) 
WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_calendar_events_title 
ON calendar_events USING gin(to_tsvector('english', title)) 
WHERE deleted_at IS NULL;

-- Add comments
COMMENT ON TABLE calendar_events IS 'Calendar events linked to contacts and meetings';
COMMENT ON COLUMN calendar_events.contact_id IS 'Primary contact associated with this event';
COMMENT ON COLUMN calendar_events.meeting_id IS 'Link to meeting record if notes were created for this event';
COMMENT ON COLUMN calendar_events.email_id IS 'Link to invitation email if available';


-- ============================================================================
-- PART 4: ENHANCE EXISTING TABLES WITH BETTER LINKING
-- ============================================================================

-- Add email-based linking to meetings (if not exists)
ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS contact_email TEXT;

-- Add calendar event link to meetings (if not exists)
ALTER TABLE meetings 
ADD COLUMN IF NOT EXISTS calendar_event_id UUID REFERENCES calendar_events(id) ON DELETE SET NULL;

-- Create index for email-based meeting lookups
CREATE INDEX IF NOT EXISTS idx_meetings_contact_email 
ON meetings(contact_email) 
WHERE contact_email IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_meetings_calendar_event 
ON meetings(calendar_event_id) 
WHERE calendar_event_id IS NOT NULL AND deleted_at IS NULL;

-- Add comments
COMMENT ON COLUMN meetings.contact_email IS 'Email address of primary meeting contact for matching';
COMMENT ON COLUMN meetings.calendar_event_id IS 'Link to calendar event if this meeting was scheduled';


-- ============================================================================
-- PART 5: CREATE INTERACTION_LOG VIEW
-- ============================================================================
-- This view provides a unified timeline of all interactions with contacts

CREATE OR REPLACE VIEW interaction_log AS
SELECT 
    'meeting' AS interaction_type,
    m.id AS interaction_id,
    m.contact_id,
    c.first_name || ' ' || COALESCE(c.last_name, '') AS contact_name,
    m.title AS title,
    m.summary AS description,
    m.date::timestamp with time zone AS interaction_date,
    m.location,
    m.created_at,
    NULL AS from_email,
    NULL AS to_emails,
    m.people_mentioned AS participants,
    m.topics_discussed::jsonb AS metadata,
    m.notion_page_id,
    m.source_file AS source
FROM meetings m
LEFT JOIN contacts c ON m.contact_id = c.id
WHERE m.deleted_at IS NULL

UNION ALL

SELECT 
    'email' AS interaction_type,
    e.id AS interaction_id,
    e.contact_id,
    c.first_name || ' ' || COALESCE(c.last_name, '') AS contact_name,
    e.subject AS title,
    e.snippet AS description,
    COALESCE(e.sent_at, e.received_at) AS interaction_date,
    NULL AS location,
    e.created_at,
    e.from_email,
    e.to_emails,
    ARRAY[e.from_name] AS participants,
    jsonb_build_object(
        'direction', e.direction,
        'category', e.category,
        'tags', e.tags
    ) AS metadata,
    e.notion_page_id,
    e.source_provider AS source
FROM emails e
LEFT JOIN contacts c ON e.contact_id = c.id
WHERE e.deleted_at IS NULL

UNION ALL

SELECT 
    'calendar_event' AS interaction_type,
    ce.id AS interaction_id,
    ce.contact_id,
    c.first_name || ' ' || COALESCE(c.last_name, '') AS contact_name,
    ce.title AS title,
    ce.description AS description,
    ce.start_time AS interaction_date,
    ce.location,
    ce.created_at,
    ce.organizer_email AS from_email,
    NULL AS to_emails,
    ARRAY[ce.organizer_name] AS participants,
    jsonb_build_object(
        'event_type', ce.event_type,
        'status', ce.status,
        'all_day', ce.all_day,
        'tags', ce.tags
    ) AS metadata,
    ce.notion_page_id,
    ce.source_provider AS source
FROM calendar_events ce
LEFT JOIN contacts c ON ce.contact_id = c.id
WHERE ce.deleted_at IS NULL

ORDER BY interaction_date DESC;

-- Add comment
COMMENT ON VIEW interaction_log IS 'Unified view of all interactions (meetings, emails, calendar events) with contacts, ordered by date';


-- ============================================================================
-- PART 6: CREATE HELPER FUNCTIONS FOR CONTACT MATCHING
-- ============================================================================

-- Function to find contact by email
CREATE OR REPLACE FUNCTION find_contact_by_email(email_address TEXT)
RETURNS UUID AS $$
DECLARE
    contact_uuid UUID;
BEGIN
    -- Try primary email first
    SELECT id INTO contact_uuid
    FROM contacts
    WHERE LOWER(email) = LOWER(email_address)
    AND deleted_at IS NULL
    LIMIT 1;
    
    IF contact_uuid IS NOT NULL THEN
        RETURN contact_uuid;
    END IF;
    
    -- Try alternative emails
    SELECT id INTO contact_uuid
    FROM contacts
    WHERE email_lower = ANY(alternative_emails)
    AND deleted_at IS NULL
    LIMIT 1;
    
    RETURN contact_uuid;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_contact_by_email IS 'Find contact by email address (checks both primary and alternative emails)';


-- Function to update contact interaction stats
CREATE OR REPLACE FUNCTION update_contact_interaction_stats(contact_uuid UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE contacts
    SET 
        total_interactions = (
            SELECT COUNT(*)
            FROM interaction_log
            WHERE contact_id = contact_uuid
        ),
        last_interaction_date = (
            SELECT MAX(interaction_date::date)
            FROM interaction_log
            WHERE contact_id = contact_uuid
        ),
        updated_at = timezone('utc'::text, now())
    WHERE id = contact_uuid;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_contact_interaction_stats IS 'Update contact interaction counts and last interaction date';


-- ============================================================================
-- PART 7: CREATE TRIGGERS FOR AUTOMATIC STAT UPDATES
-- ============================================================================

-- Trigger function to update contact stats when interactions are added
CREATE OR REPLACE FUNCTION trigger_update_contact_stats()
RETURNS TRIGGER AS $$
BEGIN
    -- Update stats for the contact
    IF NEW.contact_id IS NOT NULL THEN
        PERFORM update_contact_interaction_stats(NEW.contact_id);
    END IF;
    
    -- Also update for OLD contact if contact was changed
    IF TG_OP = 'UPDATE' AND OLD.contact_id IS NOT NULL AND OLD.contact_id != NEW.contact_id THEN
        PERFORM update_contact_interaction_stats(OLD.contact_id);
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for each table
DROP TRIGGER IF EXISTS trigger_meetings_update_contact_stats ON meetings;
CREATE TRIGGER trigger_meetings_update_contact_stats
AFTER INSERT OR UPDATE ON meetings
FOR EACH ROW
WHEN (NEW.contact_id IS NOT NULL AND NEW.deleted_at IS NULL)
EXECUTE FUNCTION trigger_update_contact_stats();

DROP TRIGGER IF EXISTS trigger_emails_update_contact_stats ON emails;
CREATE TRIGGER trigger_emails_update_contact_stats
AFTER INSERT OR UPDATE ON emails
FOR EACH ROW
WHEN (NEW.contact_id IS NOT NULL AND NEW.deleted_at IS NULL)
EXECUTE FUNCTION trigger_update_contact_stats();

DROP TRIGGER IF EXISTS trigger_calendar_events_update_contact_stats ON calendar_events;
CREATE TRIGGER trigger_calendar_events_update_contact_stats
AFTER INSERT OR UPDATE ON calendar_events
FOR EACH ROW
WHEN (NEW.contact_id IS NOT NULL AND NEW.deleted_at IS NULL)
EXECUTE FUNCTION trigger_update_contact_stats();


-- ============================================================================
-- PART 8: CREATE USEFUL QUERIES AS VIEWS
-- ============================================================================

-- View: Contact Summary with interaction counts
CREATE OR REPLACE VIEW contact_summary AS
SELECT 
    c.id,
    c.first_name,
    c.last_name,
    c.email,
    c.company,
    c.position,
    c.last_interaction_date,
    c.total_interactions,
    COUNT(DISTINCT m.id) AS meeting_count,
    COUNT(DISTINCT e.id) AS email_count,
    COUNT(DISTINCT ce.id) AS calendar_event_count,
    MAX(COALESCE(m.date, e.sent_at::date, ce.start_time::date)) AS latest_interaction
FROM contacts c
LEFT JOIN meetings m ON c.id = m.contact_id AND m.deleted_at IS NULL
LEFT JOIN emails e ON c.id = e.contact_id AND e.deleted_at IS NULL
LEFT JOIN calendar_events ce ON c.id = ce.contact_id AND ce.deleted_at IS NULL
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.first_name, c.last_name, c.email, c.company, c.position, 
         c.last_interaction_date, c.total_interactions;

COMMENT ON VIEW contact_summary IS 'Summary of each contact with interaction counts by type';


-- View: Recent Interactions (last 30 days)
CREATE OR REPLACE VIEW recent_interactions AS
SELECT *
FROM interaction_log
WHERE interaction_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY interaction_date DESC;

COMMENT ON VIEW recent_interactions IS 'All interactions from the last 30 days';


-- View: Upcoming Calendar Events
CREATE OR REPLACE VIEW upcoming_calendar_events AS
SELECT 
    ce.*,
    c.first_name || ' ' || COALESCE(c.last_name, '') AS contact_name,
    c.email AS contact_email,
    c.company AS contact_company
FROM calendar_events ce
LEFT JOIN contacts c ON ce.contact_id = c.id
WHERE ce.deleted_at IS NULL
AND ce.start_time >= CURRENT_TIMESTAMP
AND ce.status != 'cancelled'
ORDER BY ce.start_time ASC;

COMMENT ON VIEW upcoming_calendar_events IS 'Future calendar events with contact details';


-- ============================================================================
-- PART 9: SAMPLE QUERIES
-- ============================================================================

-- Example 1: Get all interactions for a specific contact
-- SELECT * FROM interaction_log WHERE contact_id = 'uuid-here' ORDER BY interaction_date DESC;

-- Example 2: Get contact summary with all stats
-- SELECT * FROM contact_summary WHERE email = 'john@example.com';

-- Example 3: Find all emails in a thread
-- SELECT * FROM emails WHERE thread_id = 'thread-id-here' ORDER BY sent_at;

-- Example 4: Get upcoming meetings with a contact
-- SELECT * FROM upcoming_calendar_events WHERE contact_id = 'uuid-here';

-- Example 5: Search for contacts by email
-- SELECT * FROM contacts WHERE email ILIKE '%john%' OR first_name ILIKE '%john%';

-- Example 6: Get all interactions with a specific person by name
-- SELECT * FROM interaction_log WHERE contact_name ILIKE '%John Smith%' ORDER BY interaction_date DESC;


-- ============================================================================
-- PART 10: ENABLE ROW LEVEL SECURITY (OPTIONAL)
-- ============================================================================
-- Uncomment if you want to enable RLS for multi-user access

-- ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY;

-- Example policies (adjust based on your auth setup):
-- CREATE POLICY "Service role full access emails" ON emails FOR ALL TO service_role USING (true);
-- CREATE POLICY "Service role full access calendar" ON calendar_events FOR ALL TO service_role USING (true);


-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Summary of changes:
-- 1. Enhanced contacts table with email fields and interaction tracking
-- 2. Created emails table for email communications
-- 3. Created calendar_events table for calendar integration
-- 4. Added cross-references between meetings, emails, and calendar events
-- 5. Created interaction_log view for unified timeline
-- 6. Created helper functions for contact matching
-- 7. Created triggers for automatic stat updates
-- 8. Created useful views for common queries
-- 
-- Next steps:
-- 1. Update Python database service to use new tables
-- 2. Add API endpoints for email and calendar operations
-- 3. Implement email/calendar sync integrations
-- 4. Test contact matching and linking
-- ============================================================================
