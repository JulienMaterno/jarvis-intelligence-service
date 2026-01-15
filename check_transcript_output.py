"""Check what was created from a transcript."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

# Get most recent transcripts
transcripts = supabase.table('transcripts').select('id,source_file,created_at,full_text').order('created_at', desc=True).limit(3).execute()

for transcript in transcripts.data:
    tid = transcript['id']
    print(f"\n{'='*60}")
    print(f"Transcript: {transcript['source_file']}")
    print(f"ID: {tid}")
    print(f"Created: {transcript['created_at'][:16]}")
    text_preview = transcript.get('full_text', '')[:200]
    print(f"Preview: {text_preview}...")
    
    # Check meetings
    meetings = supabase.table('meetings').select('id,title').eq('source_transcript_id', tid).execute()
    print(f"\nMeetings created: {len(meetings.data)}")
    for m in meetings.data:
        print(f"  - {m['title']}")
    
    # Check journals (no source_transcript_id - check by date/time proximity)
    # Journals are daily, so we check for journals on the same day
    journal_date = transcript['created_at'][:10]  # YYYY-MM-DD
    journals = supabase.table('journals').select('id,title,date').eq('date', journal_date).execute()
    print(f"\nJournals on same date ({journal_date}): {len(journals.data)}")
    for j in journals.data:
        print(f"  - {j['title']} ({j.get('date', 'no date')})")
    
    # Check reflections
    reflections = supabase.table('reflections').select('id,title').eq('source_transcript_id', tid).execute()
    print(f"\nReflections created: {len(reflections.data)}")
    for r in reflections.data:
        print(f"  - {r['title']}")
    
    # Check tasks linked to any of these
    origin_ids = [x['id'] for x in meetings.data] + [x['id'] for x in journals.data] + [x['id'] for x in reflections.data]
    if origin_ids:
        task_count = 0
        for oid in origin_ids:
            tasks = supabase.table('tasks').select('id,title,origin_type').eq('origin_id', oid).execute()
            task_count += len(tasks.data)
            for t in tasks.data:
                print(f"  - Task: {t['title']} (from {t['origin_type']})")
        print(f"\nTotal tasks: {task_count}")
    else:
        print("\nNo tasks (no origin records to link to)")
