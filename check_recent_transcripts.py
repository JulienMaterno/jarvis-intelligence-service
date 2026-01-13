"""Check recent transcripts in database."""
import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

s = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get recent transcripts
r = s.table('transcripts').select(
    'id,source_file,created_at'
).order('created_at', desc=True).limit(20).execute()

print("Recent transcripts:")
print("-" * 80)
for x in r.data:
    filename = x['source_file'][:60] if x['source_file'] else 'N/A'
    created = x['created_at'][:16] if x['created_at'] else 'N/A'
    print(f"{filename}: {created}")

# Check meetings created from these transcripts
print("\n\nRecent meetings:")
print("-" * 80)
m = s.table('meetings').select(
    'id,title,date,source_file,contact_id,contact_name,created_at'
).order('created_at', desc=True).limit(15).execute()

for x in m.data:
    title = x['title'][:40] if x['title'] else 'N/A'
    src = x['source_file'][:30] if x['source_file'] else 'N/A'
    contact = x['contact_name'] or 'No contact'
    linked = "✓" if x['contact_id'] else "✗"
    print(f"{linked} {title}: {contact} ({src})")

# Check tasks created from meetings
print("\n\nRecent tasks from meetings:")
print("-" * 80)
t = s.table('tasks').select(
    'id,title,origin_type,origin_id,status,created_at'
).eq('origin_type', 'meeting').order('created_at', desc=True).limit(10).execute()

for x in t.data:
    title = x['title'][:50] if x['title'] else 'N/A'
    status = x['status'] or 'pending'
    print(f"  [{status}] {title}")
