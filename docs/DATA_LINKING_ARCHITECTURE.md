# 🔗 Data Linking Architecture

## Overview

The Jarvis Intelligence Service implements a **comprehensive data linking architecture** that creates a fully interconnected knowledge graph of all interactions, communications, and events. This document explains how everything is linked together to enable powerful queries like "Show me everything about John Smith."

## 🎯 Key Goals

1. **Unified Contact View**: Query a person and get all meetings, emails, calendar events
2. **Automatic Linking**: Auto-link entities based on email addresses and names
3. **Relationship Tracking**: Maintain bidirectional links between related entities
4. **Interaction Timeline**: Chronological view of all interactions with any contact
5. **Flexible Querying**: Easy access to data through views and helper functions

---

## 📊 Database Schema

### Core Tables

#### 1. **contacts** (Enhanced)
The central hub for all person-related data.

**New/Enhanced Fields:**
- `email` - Primary email for reliable matching
- `alternative_emails[]` - Additional emails for the same person
- `last_interaction_date` - Auto-updated via triggers
- `total_interactions` - Auto-calculated count
- `interaction_summary` - Text summary of relationship

**Purpose:** Central registry of all people you interact with

#### 2. **emails** (New)
Complete email communication history.

**Key Fields:**
- `subject`, `body_text`, `body_html`
- `from_email`, `to_emails[]`, `cc_emails[]`
- `direction` - 'inbound' or 'outbound'
- `thread_id` - Groups conversation threads
- `contact_id` → contacts - Auto-linked via email matching
- `meeting_id` → meetings - Link follow-up emails to meetings

**Purpose:** Track all email communications with automatic contact linking

#### 3. **calendar_events** (New)
Calendar events and scheduled meetings.

**Key Fields:**
- `title`, `description`, `location`
- `start_time`, `end_time`, `all_day`
- `organizer_email`, `attendees[]`
- `contact_id` → contacts - Auto-linked via organizer email
- `meeting_id` → meetings - Link to meeting notes after event
- `email_id` → emails - Link to invitation email

**Purpose:** Track scheduled events with automatic contact linking

#### 4. **meetings** (Enhanced)
Meeting notes and summaries.

**New Fields:**
- `contact_email` - Email for matching
- `calendar_event_id` → calendar_events - Link to scheduled event

**Purpose:** Meeting notes linked to contacts and calendar events

#### 5. **transcripts**, **reflections**, **journals**, **tasks**
Existing tables remain unchanged but benefit from better contact linking.

---

## 🔗 Linking Strategy

### 1. Email-Based Linking (Primary)
**Most Reliable:** Email addresses are unique identifiers.

```python
# Automatic linking when creating email
email_id = db.create_email(
    subject="Project Update",
    from_email="john.smith@example.com",  # Auto-links to contact
    to_emails=["aaron@jarvis.ai"],
    direction="inbound"
)
# System automatically finds contact with matching email
```

**Matching Logic:**
1. Check primary `email` field (exact match, case-insensitive)
2. Check `alternative_emails[]` array
3. If found, link automatically; if not, store email for manual linking

### 2. Name-Based Linking (Secondary)
**Less Reliable:** Used when email not available.

```python
# Fuzzy name matching
contact, suggestions = db.find_contact_by_name("John Smith")
if contact:
    # Exact match found
elif suggestions:
    # Multiple matches - user should choose
```

**Matching Logic:**
1. Exact first + last name match (case-insensitive)
2. Partial name matches with scoring
3. Return suggestions if ambiguous

### 3. Manual Linking (Fallback)
When automatic linking fails or needs correction.

```python
# Link email to contact manually
PATCH /emails/{email_id}/link
{
    "contact_id": "uuid-123",
    "meeting_id": "uuid-456"  # Optional
}
```

---

## 🔄 Data Flow Examples

### Example 1: Processing an Email
```
1. New email received from john.smith@example.com
   ↓
2. System calls db.create_email(from_email="john.smith@example.com")
   ↓
3. Auto-match: Search contacts where email = "john.smith@example.com"
   ↓
4. Match found! Link email to contact automatically
   ↓
5. Trigger updates contact.last_interaction_date
   ↓
6. Contact now shows email in interaction timeline
```

### Example 2: Creating Calendar Event
```
1. Calendar sync imports event
   Title: "Meeting with Sarah Chen"
   Organizer: sarah.chen@company.com
   ↓
2. System calls db.create_calendar_event(organizer_email="sarah.chen@company.com")
   ↓
3. Auto-match: Find contact by email
   ↓
4. Link event to contact
   ↓
5. After meeting, create meeting notes
   ↓
6. Link meeting notes back to calendar event
   ↓
7. Full chain: Contact ← Calendar Event ← Meeting Notes
```

### Example 3: Comprehensive Contact Query
```python
# Get everything about John Smith
GET /contacts/{contact_id}/summary

Response:
{
    "contact": {
        "id": "uuid-123",
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "company": "Acme Corp",
        "total_interactions": 47,
        "last_interaction_date": "2024-12-19"
    },
    "interaction_counts": {
        "meetings": 12,
        "emails": 28,
        "calendar_events": 7
    },
    "recent_interactions": [
        {
            "type": "email",
            "title": "Re: Project proposal",
            "date": "2024-12-19",
            "description": "Thanks for the update..."
        },
        {
            "type": "meeting",
            "title": "Quarterly Review",
            "date": "2024-12-15",
            "summary": "Discussed Q4 goals..."
        }
    ],
    "upcoming_events": [
        {
            "title": "Follow-up call",
            "start_time": "2024-12-22T14:00:00Z"
        }
    ]
}
```

---

## 🔍 Querying the Data

### 1. Interaction Log View
**Unified timeline of all interactions**

```sql
-- Get all interactions with a contact
SELECT * FROM interaction_log 
WHERE contact_id = 'uuid-123' 
ORDER BY interaction_date DESC;

-- Result includes meetings, emails, calendar events in one view
```

**View Structure:**
```
interaction_log
├── interaction_type (meeting|email|calendar_event)
├── interaction_id
├── contact_id
├── contact_name
├── title
├── description
├── interaction_date
├── location
├── metadata (jsonb)
└── source
```

### 2. Contact Summary View
**Quick stats for each contact**

```sql
-- Get contact with interaction counts
SELECT * FROM contact_summary 
WHERE email = 'john@example.com';

-- Returns: contact info + meeting_count, email_count, etc.
```

### 3. Email Threads
**Grouped conversation threads**

```python
# Get all emails in a conversation
emails = db.get_emails_by_thread("thread-abc-123")
# Returns chronologically ordered emails
```

### 4. Upcoming Events
**Future calendar events**

```sql
SELECT * FROM upcoming_calendar_events 
WHERE contact_id = 'uuid-123'
ORDER BY start_time;
```

---

## 🤖 Automatic Updates

### Triggers
The system uses PostgreSQL triggers to keep data synchronized:

```sql
-- When new interaction added → Update contact stats
CREATE TRIGGER trigger_meetings_update_contact_stats
AFTER INSERT OR UPDATE ON meetings
FOR EACH ROW
EXECUTE FUNCTION trigger_update_contact_stats();

-- Same triggers on: emails, calendar_events
```

**What Gets Updated:**
- `contacts.last_interaction_date` - Most recent interaction
- `contacts.total_interactions` - Count of all interactions
- `contacts.updated_at` - Timestamp

### Helper Functions
```sql
-- Find contact by email (checks primary + alternatives)
SELECT find_contact_by_email('john@example.com');

-- Update interaction stats manually (if needed)
SELECT update_contact_interaction_stats('uuid-123');
```

---

## 📡 API Endpoints

### Email Operations

```http
POST /api/v1/emails
{
    "subject": "Project Update",
    "from_email": "john@example.com",
    "to_emails": ["aaron@jarvis.ai"],
    "body_text": "Here's the latest...",
    "direction": "inbound",
    "sent_at": "2024-12-20T10:30:00Z"
}
```

```http
PATCH /api/v1/emails/{email_id}/link
{
    "contact_id": "uuid-123",
    "meeting_id": "uuid-456"
}
```

```http
GET /api/v1/emails/thread/{thread_id}
```

### Calendar Event Operations

```http
POST /api/v1/calendar-events
{
    "title": "Meeting with John",
    "start_time": "2024-12-22T14:00:00Z",
    "end_time": "2024-12-22T15:00:00Z",
    "organizer_email": "john@example.com",
    "location": "Conference Room A"
}
```

```http
PATCH /api/v1/calendar-events/{event_id}/link
{
    "meeting_id": "uuid-789"
}
```

```http
GET /api/v1/calendar-events/upcoming
```

### Contact Interaction Queries

```http
GET /api/v1/contacts/{contact_id}/interactions?limit=50
# Returns unified timeline of all interactions
```

```http
GET /api/v1/contacts/{contact_id}/summary
# Returns comprehensive contact summary with stats
```

---

## 🔐 Best Practices

### 1. Always Provide Emails When Available
```python
# ✅ Good - Email enables automatic linking
db.create_meeting(
    meeting_data={
        "title": "Strategy Discussion",
        "person_name": "John Smith"
    },
    contact_email="john.smith@example.com"  # Add this!
)

# ❌ Less reliable - Only name-based matching
db.create_meeting(
    meeting_data={
        "title": "Strategy Discussion",
        "person_name": "John Smith"
    }
)
```

### 2. Link Related Entities
```python
# Create email about a meeting
email_id = db.create_email(
    subject="Meeting notes",
    from_email="john@example.com",
    meeting_id=meeting_id  # Link to meeting
)

# Create meeting notes for calendar event
meeting_id = db.create_meeting(
    calendar_event_id=event_id  # Link to calendar
)
```

### 3. Use Views for Queries
```python
# ✅ Use interaction_log view
interactions = db.get_contact_interactions(contact_id)

# ❌ Don't manually query each table
meetings = db.get_meetings_by_contact(contact_id)
emails = db.get_emails_by_contact(contact_id)
events = db.get_calendar_events_by_contact(contact_id)
```

### 4. Validate Links
```python
# After auto-linking, provide feedback to user
if contact_match_info["matched"]:
    print(f"✓ Linked to {contact_match_info['linked_contact']['name']}")
elif contact_match_info["suggestions"]:
    print(f"? Multiple matches found. Please select:")
    for suggestion in contact_match_info["suggestions"]:
        print(f"  - {suggestion['name']} at {suggestion['company']}")
```

---

## 🚀 Integration Examples

### Email Service Integration

```python
# Sync emails from Gmail
for email in gmail_api.get_emails():
    db.create_email(
        subject=email.subject,
        from_email=email.sender,
        to_emails=email.recipients,
        body_text=email.body,
        direction="inbound" if email.sender != "aaron@jarvis.ai" else "outbound",
        sent_at=email.timestamp,
        message_id=email.id,
        thread_id=email.thread_id,
        source_provider="gmail"
    )
    # Auto-links to contacts via email matching
```

### Calendar Sync Integration

```python
# Sync events from Google Calendar
for event in calendar_api.get_events():
    db.create_calendar_event(
        title=event.summary,
        start_time=event.start,
        end_time=event.end,
        organizer_email=event.organizer.email,
        attendees=event.attendees,
        location=event.location,
        source_provider="google_calendar",
        source_event_id=event.id
    )
    # Auto-links to contacts via organizer email
```

---

## 📈 Analytics Queries

### Most Active Contacts
```sql
SELECT 
    first_name || ' ' || last_name as name,
    company,
    total_interactions,
    last_interaction_date
FROM contacts
WHERE deleted_at IS NULL
ORDER BY total_interactions DESC
LIMIT 10;
```

### Interaction Breakdown by Type
```sql
SELECT 
    interaction_type,
    COUNT(*) as count,
    DATE_TRUNC('month', interaction_date) as month
FROM interaction_log
WHERE interaction_date >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY interaction_type, month
ORDER BY month DESC, interaction_type;
```

### Contacts to Follow Up
```sql
-- Contacts with no interaction in 30+ days
SELECT 
    first_name || ' ' || last_name as name,
    email,
    company,
    last_interaction_date,
    CURRENT_DATE - last_interaction_date as days_since_contact
FROM contacts
WHERE deleted_at IS NULL
AND last_interaction_date < CURRENT_DATE - INTERVAL '30 days'
ORDER BY last_interaction_date;
```

---

## 🔄 Migration Path

### For Existing Data

1. **Run the SQL migration:**
   ```sql
   -- Execute in Supabase SQL Editor
   \i migrations/add_comprehensive_data_linking.sql
   ```

2. **Backfill contact emails:**
   ```python
   # Add emails to existing contacts
   for meeting in meetings:
       if meeting.contact_id and meeting.contact_email:
           db.client.table("contacts").update({
               "email": meeting.contact_email
           }).eq("id", meeting.contact_id).execute()
   ```

3. **Verify triggers are working:**
   ```sql
   -- Create test interaction
   INSERT INTO emails (...) VALUES (...);
   
   -- Check contact was updated
   SELECT total_interactions, last_interaction_date 
   FROM contacts WHERE id = 'test-contact-id';
   ```

---

## 🎯 Future Enhancements

1. **AI-Powered Relationship Scoring**
   - Analyze interaction frequency, recency, sentiment
   - Surface contacts that need attention

2. **Duplicate Detection**
   - Find and merge duplicate contacts
   - Consolidate interaction history

3. **Smart Suggestions**
   - "You haven't talked to Sarah in 2 months, send a follow-up?"
   - "John mentioned project X in 3 different meetings"

4. **Network Visualization**
   - Graph view of contact relationships
   - Who introduced you to whom?

5. **Cross-Reference Search**
   - "Find all meetings where we discussed climate tech with biotech contacts"
   - "Show emails and meetings with startup founders in Singapore"

---

## 📚 Reference

### Key Database Objects

**Tables:**
- `contacts` (enhanced)
- `emails` (new)
- `calendar_events` (new)
- `meetings` (enhanced)

**Views:**
- `interaction_log` - Unified timeline
- `contact_summary` - Stats per contact
- `recent_interactions` - Last 30 days
- `upcoming_calendar_events` - Future events

**Functions:**
- `find_contact_by_email(email)` - Email-based lookup
- `update_contact_interaction_stats(contact_id)` - Refresh stats

**Triggers:**
- Auto-update contact stats on new interactions

### API Routes

**Emails:**
- `POST /api/v1/emails` - Create email
- `PATCH /api/v1/emails/{id}/link` - Link to meeting/contact
- `GET /api/v1/emails/thread/{thread_id}` - Get thread

**Calendar:**
- `POST /api/v1/calendar-events` - Create event
- `PATCH /api/v1/calendar-events/{id}/link` - Link to meeting/contact
- `GET /api/v1/calendar-events/upcoming` - Future events

**Interactions:**
- `GET /api/v1/contacts/{id}/interactions` - All interactions
- `GET /api/v1/contacts/{id}/summary` - Full summary

---

## 💡 Summary

The comprehensive data linking architecture transforms Jarvis from a collection of isolated records into a **fully interconnected knowledge graph**. Every meeting, email, and calendar event automatically links to contacts, creating a complete interaction history that enables powerful queries and insights.

**Key Benefits:**
- 🔍 **Unified View:** See everything about a person in one place
- 🤖 **Automatic Linking:** Email-based matching reduces manual work
- 📊 **Rich Analytics:** Understand interaction patterns
- 🔗 **Bidirectional Links:** Navigate between related entities easily
- 🚀 **Future-Proof:** Foundation for AI-powered relationship management
