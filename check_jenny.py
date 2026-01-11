"""Test Jenny's contact history."""
from supabase import create_client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ojnllduebzfxqmiyinhx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_KEY:
    print("Set SUPABASE_KEY environment variable")
    exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get Jenny's contact
r = sb.table('contacts').select('id,first_name,last_name').ilike('first_name', '%jenny%').execute()
if r.data:
    contact = r.data[0]
    contact_id = contact['id']
    print(f"Jenny's contact ID: {contact_id}")
    
    # Check meetings with this contact
    m = sb.table('meetings').select('id,title,date').eq('contact_id', contact_id).limit(5).execute()
    print(f"\nMeetings: {len(m.data)} found")
    for meeting in m.data[:3]:
        print(f"  - {meeting.get('title', 'N/A')}: {meeting.get('date', 'N/A')}")
    
    # Check emails
    e = sb.table('emails').select('id,subject,date').eq('contact_id', contact_id).limit(5).execute()
    print(f"\nEmails: {len(e.data)} found")
    
    # Check if there's a meeting with contact_name instead
    m2 = sb.table('meetings').select('id,title,date,contact_id,contact_name').ilike('contact_name', '%jenny%').limit(5).execute()
    print(f"\nMeetings by name match: {len(m2.data)} found")
    for meeting in m2.data[:3]:
        print(f"  - {meeting.get('title', 'N/A')}: {meeting.get('date', 'N/A')} (contact_id: {meeting.get('contact_id')})")
else:
    print('Jenny not found')
