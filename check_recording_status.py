"""Check specific recording status."""
import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

s = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Recording IDs to check
recordings = ['131528', '150245']

for rec_id in recordings:
    print(f"\n{'='*60}")
    print(f"Recording: {rec_id}")
    print("="*60)
    
    # Check transcript
    t = s.table('transcripts').select('id,source_file,full_text').ilike('source_file', f'%{rec_id}%').execute()
    print(f"Transcripts found: {len(t.data)}")
    if t.data:
        text = t.data[0]['full_text']
        print(f"  Transcript length: {len(text)} chars")
        print(f"  ID: {t.data[0]['id']}")
    
    # Check meeting  
    m = s.table('meetings').select('id,title,contact_id,contact_name,created_at').ilike('source_file', f'%{rec_id}%').execute()
    print(f"Meetings found: {len(m.data)}")
    for mtg in m.data:
        print(f"  Title: {mtg['title']}")
        print(f"  Contact: {mtg['contact_name'] or 'None'} (linked: {'Yes' if mtg['contact_id'] else 'No'})")

# Also check what files exist locally
import glob
import pathlib

print(f"\n{'='*60}")
print("Local files needing reprocess:")
print("="*60)

recordings_path = pathlib.Path.home() / ".jarvis" / "meeting_recordings"
for rec_id in recordings:
    files = list(recordings_path.glob(f"*{rec_id}*"))
    if files:
        print(f"\n{rec_id}:")
        for f in files:
            size_mb = f.stat().st_size / (1024*1024)
            print(f"  {f.name}: {size_mb:.1f} MB")
