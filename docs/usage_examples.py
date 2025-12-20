"""
Usage Examples for Data Linking Architecture

This file demonstrates how to use the new email, calendar event, and 
contact interaction features in the Jarvis Intelligence Service.
"""

from app.services.database import SupabaseMultiDatabase
from datetime import datetime, timedelta

# Initialize database service
db = SupabaseMultiDatabase()

# ============================================================================
# EXAMPLE 1: Creating and Auto-Linking an Email
# ============================================================================
print("Example 1: Creating an email with automatic contact linking")

# Create an email - system will auto-link to contact via email address
email_id, email_url = db.create_email(
    subject="Project Update - Q4 Progress",
    from_email="john.smith@example.com",  # Auto-links to contact if exists
    to_emails=["aaron@jarvis.ai"],
    body_text="Hi Aaron, here's the latest update on our Q4 progress...",
    direction="inbound",
    sent_at="2024-12-20T10:30:00Z",
    category="work",
    tags=["project-update", "q4"],
    source_provider="gmail"
)

print(f"✓ Email created: {email_id}")
print(f"  URL: {email_url}")
print(f"  System automatically linked to contact with email: john.smith@example.com")
print()

# ============================================================================
# EXAMPLE 2: Creating a Calendar Event
# ============================================================================
print("Example 2: Creating a calendar event with automatic contact linking")

# Create a calendar event - auto-links via organizer email
event_id, event_url = db.create_calendar_event(
    title="Strategy Discussion with Sarah",
    start_time="2024-12-22T14:00:00Z",
    end_time="2024-12-22T15:00:00Z",
    description="Quarterly planning and goal setting",
    location="Conference Room A",
    organizer_email="sarah.chen@company.com",  # Auto-links to contact
    organizer_name="Sarah Chen",
    attendees=[
        {"email": "aaron@jarvis.ai", "name": "Aaron", "response_status": "accepted"},
        {"email": "sarah.chen@company.com", "name": "Sarah Chen", "response_status": "accepted"}
    ],
    event_type="meeting",
    meeting_url="https://zoom.us/j/123456789",
    tags=["strategy", "planning"],
    source_provider="google_calendar"
)

print(f"✓ Calendar event created: {event_id}")
print(f"  URL: {event_url}")
print(f"  System automatically linked to contact with email: sarah.chen@company.com")
print()

# ============================================================================
# EXAMPLE 3: Finding Contacts by Email
# ============================================================================
print("Example 3: Finding contacts by email address")

# Find a contact by email (checks primary and alternative emails)
contact = db.find_contact_by_email("john.smith@example.com")

if contact:
    print(f"✓ Found contact:")
    print(f"  Name: {contact['first_name']} {contact.get('last_name', '')}")
    print(f"  Company: {contact.get('company')}")
    print(f"  Email: {contact.get('email')}")
    print(f"  Total interactions: {contact.get('total_interactions', 0)}")
else:
    print("✗ Contact not found")
print()

# ============================================================================
# EXAMPLE 4: Getting All Interactions for a Contact
# ============================================================================
print("Example 4: Getting unified interaction timeline for a contact")

# Assuming we have a contact_id from above
if contact:
    contact_id = contact['id']
    
    # Get all interactions (meetings, emails, calendar events)
    interactions = db.get_contact_interactions(contact_id, limit=10)
    
    print(f"✓ Found {len(interactions)} interactions with {contact['first_name']}:")
    for interaction in interactions[:5]:  # Show first 5
        print(f"  - {interaction['interaction_type']:15} | {interaction['interaction_date']} | {interaction['title']}")
    
    # Count by type
    counts = {}
    for i in interactions:
        itype = i['interaction_type']
        counts[itype] = counts.get(itype, 0) + 1
    
    print(f"\n  Breakdown: {counts}")
print()

# ============================================================================
# EXAMPLE 5: Linking Email to Meeting
# ============================================================================
print("Example 5: Linking an email to a meeting")

# Suppose you receive a follow-up email about a meeting
# Link the email to the meeting for complete context

meeting_id = "some-meeting-uuid"  # From previous meeting creation
email_id = "some-email-uuid"      # From email creation above

# Link them together
db.link_email_to_meeting(email_id, meeting_id)

print(f"✓ Linked email {email_id} to meeting {meeting_id}")
print(f"  Now when viewing the meeting, you can see related email correspondence")
print()

# ============================================================================
# EXAMPLE 6: Linking Calendar Event to Meeting Notes
# ============================================================================
print("Example 6: Linking calendar event to meeting notes")

# After a calendar event happens, you create meeting notes
# Link them together for complete history

event_id = "some-event-uuid"    # Calendar event
meeting_id = "some-meeting-uuid"  # Meeting notes created after

# Create bidirectional link
db.link_calendar_event_to_meeting(event_id, meeting_id)

print(f"✓ Linked calendar event {event_id} to meeting {meeting_id}")
print(f"  Timeline: Calendar Invite → Event Happens → Meeting Notes Created")
print()

# ============================================================================
# EXAMPLE 7: Getting Upcoming Events
# ============================================================================
print("Example 7: Getting upcoming calendar events")

upcoming_events = db.get_upcoming_events(limit=5)

print(f"✓ Found {len(upcoming_events)} upcoming events:")
for event in upcoming_events:
    start_time = event['start_time']
    print(f"  - {start_time} | {event['title']}")
    if event.get('contact_id'):
        print(f"    with contact: {event.get('contact_name')}")
print()

# ============================================================================
# EXAMPLE 8: Finding Contact by Name or Email
# ============================================================================
print("Example 8: Smart contact matching by name or email")

# Try to find contact by both name and email
contact, suggestions = db.find_contact_by_name_or_email(
    name="John Smith",
    email="john.smith@example.com"
)

if contact:
    print(f"✓ Found exact match:")
    print(f"  {contact['first_name']} {contact.get('last_name')} <{contact.get('email')}>")
elif suggestions:
    print(f"? Found {len(suggestions)} possible matches:")
    for s in suggestions:
        print(f"  - {s['first_name']} {s.get('last_name')} at {s.get('company')}")
else:
    print("✗ No matches found")
print()

# ============================================================================
# EXAMPLE 9: Getting Email Thread
# ============================================================================
print("Example 9: Getting all emails in a conversation thread")

thread_id = "thread-abc-123"
thread_emails = db.get_emails_by_thread(thread_id)

print(f"✓ Found {len(thread_emails)} emails in thread:")
for email in thread_emails:
    print(f"  - {email['sent_at']} | From: {email['from_email']}")
    print(f"    Subject: {email['subject']}")
print()

# ============================================================================
# EXAMPLE 10: Manual Contact Stat Update
# ============================================================================
print("Example 10: Manually updating contact interaction statistics")

# Usually done automatically by triggers, but can be called manually
contact_id = "some-contact-uuid"
db.update_contact_interaction_stats(contact_id)

print(f"✓ Updated interaction stats for contact {contact_id}")
print(f"  Recalculated: total_interactions, last_interaction_date")
print()

# ============================================================================
# EXAMPLE 11: API Usage - Create Email via HTTP
# ============================================================================
print("Example 11: Creating email via API endpoint")
print("""
POST /api/v1/emails
Content-Type: application/json

{
    "subject": "Project Update",
    "from_email": "john.smith@example.com",
    "to_emails": ["aaron@jarvis.ai"],
    "body_text": "Here's the latest update...",
    "direction": "inbound",
    "sent_at": "2024-12-20T10:30:00Z",
    "category": "work",
    "tags": ["project"]
}

Response:
{
    "status": "success",
    "email_id": "uuid-123",
    "email_url": "supabase://emails/uuid-123",
    "contact_id": "uuid-456",
    "contact_name": "John Smith"
}
""")
print()

# ============================================================================
# EXAMPLE 12: API Usage - Get Contact Summary
# ============================================================================
print("Example 12: Getting comprehensive contact summary via API")
print("""
GET /api/v1/contacts/{contact_id}/summary

Response:
{
    "status": "success",
    "contact": {
        "id": "uuid-456",
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
            "interaction_type": "email",
            "title": "Re: Project proposal",
            "interaction_date": "2024-12-19T10:30:00Z",
            "description": "Thanks for the update..."
        },
        {
            "interaction_type": "meeting",
            "title": "Quarterly Review",
            "interaction_date": "2024-12-15T14:00:00Z",
            "summary": "Discussed Q4 goals..."
        }
    ],
    "upcoming_events": [
        {
            "title": "Follow-up call",
            "start_time": "2024-12-22T14:00:00Z",
            "location": "Zoom"
        }
    ]
}
""")
print()

# ============================================================================
# EXAMPLE 13: SQL Query - Get All Interactions for a Contact
# ============================================================================
print("Example 13: Direct SQL query for interactions")
print("""
-- Get all interactions with a specific contact
SELECT * FROM interaction_log 
WHERE contact_id = 'uuid-456' 
ORDER BY interaction_date DESC 
LIMIT 50;

-- Result includes meetings, emails, and calendar events in one unified view
-- Columns: interaction_type, interaction_id, contact_id, contact_name, 
--          title, description, interaction_date, location, metadata
""")
print()

# ============================================================================
# EXAMPLE 14: SQL Query - Find Contacts to Follow Up With
# ============================================================================
print("Example 14: Finding contacts that need follow-up")
print("""
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
""")
print()

print("=" * 70)
print("All examples completed!")
print("=" * 70)
print("\nKey Features:")
print("✓ Automatic contact linking via email addresses")
print("✓ Unified interaction timeline (meetings, emails, calendar)")
print("✓ Bidirectional relationships between entities")
print("✓ Automatic stat updates via database triggers")
print("✓ Rich querying via views and API endpoints")
print("\nFor more information, see: docs/DATA_LINKING_ARCHITECTURE.md")
