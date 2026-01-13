"""Quick script to check recent transcripts and meetings."""
import os
from supabase import create_client

client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

# Get recent transcripts
result = client.table('transcripts').select(
    'id,source_file,audio_duration_seconds,language,full_text,speakers'
).order('created_at', desc=True).limit(10).execute()

print("\n=== Recent Transcripts ===")
print(f"{'ID':10} | {'Source File':45} | {'Lang':5} | {'Dur':6} | {'Chars':6} | Speakers")
print("-" * 100)

for r in result.data:
    print(f"{r['id'][:8]:10} | {str(r.get('source_file','??'))[:45]:45} | {str(r.get('language','??')):5} | {str(int(r.get('audio_duration_seconds',0) or 0))+'s':6} | {len(r.get('full_text','') or ''):6} | {r.get('speakers',[])}")

# Check meetings with Jonas
print("\n=== Meetings with Jonas ===")
meetings = client.table('meetings').select('id,title,date,contact_id,summary').ilike('title', '%jonas%').execute()
print(f"Found {len(meetings.data)} meetings")
for m in meetings.data[:5]:
    print(f"  {m['id'][:8]} | {m.get('title','')[:50]} | {m.get('date')}")
    if m.get('summary'):
        print(f"    Summary: {m.get('summary','')[:200]}...")

# Check meetings linked to Jonas contact
print("\n=== Meetings linked to Jonas contact ===")
# Find Jonas contact
contacts = client.table('contacts').select('id,first_name,last_name').ilike('first_name', '%jonas%').execute()
if contacts.data:
    jonas_id = contacts.data[0]['id']
    print(f"Jonas contact ID: {jonas_id}")
    linked = client.table('meetings').select('id,title,date').eq('contact_id', jonas_id).execute()
    print(f"Found {len(linked.data)} meetings linked to Jonas")
    for m in linked.data[:5]:
        print(f"  {m['id'][:8]} | {m.get('title','')[:50]} | {m.get('date')}")
