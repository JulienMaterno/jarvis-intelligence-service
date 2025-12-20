# SQL Query Quick Reference

Common SQL queries for working with the interconnected data model.

## 🔍 Finding Contacts

### Search by Email
```sql
-- Find contact by primary email
SELECT * FROM contacts 
WHERE LOWER(email) = LOWER('john@example.com')
AND deleted_at IS NULL;

-- Find contact by email (using helper function)
SELECT find_contact_by_email('john@example.com');
```

### Search by Name
```sql
-- Exact name match
SELECT * FROM contacts 
WHERE LOWER(first_name) = 'john' 
AND LOWER(last_name) = 'smith'
AND deleted_at IS NULL;

-- Fuzzy name search
SELECT * FROM contacts 
WHERE first_name ILIKE '%john%' 
OR last_name ILIKE '%smith%'
AND deleted_at IS NULL
LIMIT 10;
```

### Get Contact Summary
```sql
-- Complete contact info with interaction counts
SELECT * FROM contact_summary 
WHERE email = 'john@example.com';
```

## 📊 Interaction Queries

### Get All Interactions for a Contact
```sql
-- Unified timeline (meetings, emails, calendar events)
SELECT * FROM interaction_log 
WHERE contact_id = 'uuid-123' 
ORDER BY interaction_date DESC 
LIMIT 50;
```

### Recent Interactions (Last 30 Days)
```sql
-- All recent interactions
SELECT * FROM recent_interactions 
WHERE contact_id = 'uuid-123';

-- Or direct query
SELECT * FROM interaction_log 
WHERE contact_id = 'uuid-123'
AND interaction_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY interaction_date DESC;
```

### Count Interactions by Type
```sql
SELECT 
    interaction_type,
    COUNT(*) as count
FROM interaction_log
WHERE contact_id = 'uuid-123'
GROUP BY interaction_type;
```

## 📧 Email Queries

### Get All Emails with a Contact
```sql
SELECT * FROM emails 
WHERE contact_id = 'uuid-123'
AND deleted_at IS NULL
ORDER BY sent_at DESC;
```

### Get Email Thread
```sql
-- All emails in a conversation
SELECT * FROM emails 
WHERE thread_id = 'thread-abc-123'
AND deleted_at IS NULL
ORDER BY sent_at ASC;
```

### Find Emails by Subject
```sql
-- Full text search on subject
SELECT * FROM emails 
WHERE to_tsvector('english', subject) @@ to_tsquery('english', 'project & update')
AND deleted_at IS NULL
ORDER BY sent_at DESC;
```

### Emails Linked to Meetings
```sql
-- Find emails that reference a specific meeting
SELECT e.*, m.title as meeting_title
FROM emails e
JOIN meetings m ON e.meeting_id = m.id
WHERE m.id = 'meeting-uuid-123'
AND e.deleted_at IS NULL;
```

## 📅 Calendar Event Queries

### Upcoming Events
```sql
-- Next 20 events
SELECT * FROM upcoming_calendar_events 
ORDER BY start_time 
LIMIT 20;

-- Or direct query
SELECT * FROM calendar_events 
WHERE start_time >= CURRENT_TIMESTAMP
AND status != 'cancelled'
AND deleted_at IS NULL
ORDER BY start_time ASC;
```

### Events with a Specific Contact
```sql
SELECT * FROM calendar_events 
WHERE contact_id = 'uuid-123'
AND deleted_at IS NULL
ORDER BY start_time DESC;
```

### Events This Week
```sql
SELECT * FROM calendar_events 
WHERE start_time >= DATE_TRUNC('week', CURRENT_TIMESTAMP)
AND start_time < DATE_TRUNC('week', CURRENT_TIMESTAMP) + INTERVAL '1 week'
AND deleted_at IS NULL
ORDER BY start_time;
```

### Events Linked to Meetings
```sql
-- Calendar events that have meeting notes
SELECT ce.*, m.summary
FROM calendar_events ce
JOIN meetings m ON ce.meeting_id = m.id
WHERE ce.contact_id = 'uuid-123'
AND ce.deleted_at IS NULL;
```

## 🤝 Meeting Queries

### Meetings with a Contact
```sql
SELECT * FROM meetings 
WHERE contact_id = 'uuid-123'
AND deleted_at IS NULL
ORDER BY date DESC;
```

### Meetings Linked to Calendar Events
```sql
-- Meetings that came from scheduled events
SELECT m.*, ce.title as event_title, ce.start_time
FROM meetings m
JOIN calendar_events ce ON m.calendar_event_id = ce.id
WHERE m.contact_id = 'uuid-123'
AND m.deleted_at IS NULL;
```

### Meetings with Follow-up Emails
```sql
-- Meetings that have related email correspondence
SELECT m.*, COUNT(e.id) as email_count
FROM meetings m
LEFT JOIN emails e ON e.meeting_id = m.id AND e.deleted_at IS NULL
WHERE m.contact_id = 'uuid-123'
AND m.deleted_at IS NULL
GROUP BY m.id
ORDER BY m.date DESC;
```

## 📈 Analytics Queries

### Most Active Contacts
```sql
SELECT 
    first_name || ' ' || COALESCE(last_name, '') as name,
    email,
    company,
    total_interactions,
    last_interaction_date
FROM contacts
WHERE deleted_at IS NULL
ORDER BY total_interactions DESC
LIMIT 20;
```

### Interaction Breakdown by Month
```sql
SELECT 
    DATE_TRUNC('month', interaction_date) as month,
    interaction_type,
    COUNT(*) as count
FROM interaction_log
WHERE interaction_date >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY month, interaction_type
ORDER BY month DESC, interaction_type;
```

### Contacts Needing Follow-Up
```sql
-- No interaction in 30+ days
SELECT 
    first_name || ' ' || COALESCE(last_name, '') as name,
    email,
    company,
    last_interaction_date,
    CURRENT_DATE - last_interaction_date as days_since_contact
FROM contacts
WHERE deleted_at IS NULL
AND last_interaction_date IS NOT NULL
AND last_interaction_date < CURRENT_DATE - INTERVAL '30 days'
ORDER BY last_interaction_date;
```

### Email Response Rate
```sql
-- Ratio of inbound to outbound emails per contact
SELECT 
    c.first_name || ' ' || COALESCE(c.last_name, '') as name,
    COUNT(CASE WHEN e.direction = 'inbound' THEN 1 END) as emails_received,
    COUNT(CASE WHEN e.direction = 'outbound' THEN 1 END) as emails_sent,
    ROUND(
        COUNT(CASE WHEN e.direction = 'outbound' THEN 1 END)::numeric / 
        NULLIF(COUNT(CASE WHEN e.direction = 'inbound' THEN 1 END), 0),
        2
    ) as response_ratio
FROM contacts c
LEFT JOIN emails e ON e.contact_id = c.id AND e.deleted_at IS NULL
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.first_name, c.last_name
HAVING COUNT(e.id) > 0
ORDER BY response_ratio DESC;
```

### Meeting Frequency Analysis
```sql
-- Average days between meetings per contact
SELECT 
    c.first_name || ' ' || COALESCE(c.last_name, '') as name,
    c.company,
    COUNT(m.id) as total_meetings,
    MIN(m.date) as first_meeting,
    MAX(m.date) as last_meeting,
    CASE 
        WHEN COUNT(m.id) > 1 THEN
            ROUND((MAX(m.date) - MIN(m.date)) / NULLIF(COUNT(m.id) - 1, 0))
        ELSE NULL
    END as avg_days_between_meetings
FROM contacts c
LEFT JOIN meetings m ON m.contact_id = c.id AND m.deleted_at IS NULL
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.first_name, c.last_name, c.company
HAVING COUNT(m.id) > 1
ORDER BY total_meetings DESC;
```

## 🔗 Relationship Queries

### Complete Contact Relationship Graph
```sql
-- Everything connected to a contact
SELECT 
    'contact' as entity_type,
    c.id,
    c.first_name || ' ' || COALESCE(c.last_name, '') as title,
    NULL as related_to
FROM contacts c
WHERE c.id = 'uuid-123'

UNION ALL

SELECT 
    'meeting' as entity_type,
    m.id,
    m.title,
    m.contact_id as related_to
FROM meetings m
WHERE m.contact_id = 'uuid-123' AND m.deleted_at IS NULL

UNION ALL

SELECT 
    'email' as entity_type,
    e.id,
    e.subject,
    e.contact_id as related_to
FROM emails e
WHERE e.contact_id = 'uuid-123' AND e.deleted_at IS NULL

UNION ALL

SELECT 
    'calendar_event' as entity_type,
    ce.id,
    ce.title,
    ce.contact_id as related_to
FROM calendar_events ce
WHERE ce.contact_id = 'uuid-123' AND ce.deleted_at IS NULL;
```

### Cross-Reference: Meetings and Emails
```sql
-- Find emails that reference meetings
SELECT 
    m.title as meeting_title,
    m.date as meeting_date,
    e.subject as email_subject,
    e.sent_at as email_date,
    e.direction
FROM meetings m
LEFT JOIN emails e ON e.meeting_id = m.id AND e.deleted_at IS NULL
WHERE m.contact_id = 'uuid-123'
AND m.deleted_at IS NULL
ORDER BY m.date DESC, e.sent_at;
```

### Timeline: From Calendar Invite to Meeting Notes
```sql
-- Complete event lifecycle
SELECT 
    ce.title as event_title,
    ce.start_time,
    ce.source_event_id as calendar_id,
    m.title as meeting_notes_title,
    m.summary,
    e.subject as related_email
FROM calendar_events ce
LEFT JOIN meetings m ON m.calendar_event_id = ce.id AND m.deleted_at IS NULL
LEFT JOIN emails e ON e.email_id = ce.email_id AND e.deleted_at IS NULL
WHERE ce.contact_id = 'uuid-123'
AND ce.deleted_at IS NULL
ORDER BY ce.start_time DESC;
```

## 🔧 Maintenance Queries

### Update Contact Stats Manually
```sql
-- Refresh interaction counts for a specific contact
SELECT update_contact_interaction_stats('uuid-123');

-- Refresh all contacts (run periodically if triggers fail)
DO $$
DECLARE
    contact_record RECORD;
BEGIN
    FOR contact_record IN 
        SELECT id FROM contacts WHERE deleted_at IS NULL
    LOOP
        PERFORM update_contact_interaction_stats(contact_record.id);
    END LOOP;
END $$;
```

### Find Unlinked Entities
```sql
-- Emails without contact links
SELECT id, subject, from_email 
FROM emails 
WHERE contact_id IS NULL 
AND deleted_at IS NULL
LIMIT 20;

-- Calendar events without contact links
SELECT id, title, organizer_email 
FROM calendar_events 
WHERE contact_id IS NULL 
AND deleted_at IS NULL
LIMIT 20;

-- Meetings without contact links
SELECT id, title, contact_name 
FROM meetings 
WHERE contact_id IS NULL 
AND contact_name IS NOT NULL
AND deleted_at IS NULL
LIMIT 20;
```

### Duplicate Detection
```sql
-- Find potential duplicate contacts by email
SELECT email, COUNT(*) as count, STRING_AGG(id::text, ', ') as ids
FROM contacts
WHERE deleted_at IS NULL AND email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;

-- Find potential duplicate contacts by name
SELECT 
    first_name, 
    last_name, 
    COUNT(*) as count, 
    STRING_AGG(email, ', ') as emails,
    STRING_AGG(id::text, ', ') as ids
FROM contacts
WHERE deleted_at IS NULL
GROUP BY first_name, last_name
HAVING COUNT(*) > 1;
```

## 🎯 Advanced Queries

### Network Analysis: Who Introduced You?
```sql
-- People mentioned in meetings with other contacts
SELECT 
    c1.first_name || ' ' || COALESCE(c1.last_name, '') as primary_contact,
    unnest(m.people_mentioned) as person_mentioned,
    COUNT(*) as mention_count
FROM meetings m
JOIN contacts c1 ON m.contact_id = c1.id
WHERE m.deleted_at IS NULL
AND c1.deleted_at IS NULL
GROUP BY c1.id, c1.first_name, c1.last_name, person_mentioned
HAVING COUNT(*) > 1
ORDER BY mention_count DESC;
```

### Topic Analysis Across Contacts
```sql
-- What topics do you discuss with each contact?
SELECT 
    c.first_name || ' ' || COALESCE(c.last_name, '') as contact_name,
    unnest(m.tags) as tag,
    COUNT(*) as frequency
FROM contacts c
JOIN meetings m ON m.contact_id = c.id AND m.deleted_at IS NULL
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.first_name, c.last_name, tag
ORDER BY contact_name, frequency DESC;
```

### Engagement Score
```sql
-- Calculate engagement score based on interaction frequency and recency
SELECT 
    c.first_name || ' ' || COALESCE(c.last_name, '') as name,
    c.company,
    c.total_interactions,
    c.last_interaction_date,
    -- Score: interactions * recency weight
    ROUND(
        c.total_interactions * 
        (1.0 / GREATEST(1, CURRENT_DATE - c.last_interaction_date))
    , 2) as engagement_score
FROM contacts c
WHERE c.deleted_at IS NULL
AND c.total_interactions > 0
ORDER BY engagement_score DESC
LIMIT 20;
```

---

## 💡 Tips

1. **Use Views**: `interaction_log`, `contact_summary`, `recent_interactions`, `upcoming_calendar_events` for common queries
2. **Use Indexes**: Queries on `contact_id`, `email`, `thread_id`, `start_time` are optimized
3. **Check Deleted**: Always add `AND deleted_at IS NULL` for soft-deleted records
4. **Use Helper Functions**: `find_contact_by_email()`, `update_contact_interaction_stats()`
5. **Batch Updates**: For large data migrations, use transactions and batch processing

---

For more information, see [Data Linking Architecture](./DATA_LINKING_ARCHITECTURE.md)
