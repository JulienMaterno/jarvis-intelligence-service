"""Quick script to check recent transcripts processed via Telegram."""
import os
from supabase import create_client

client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

# Get recent transcripts (exclude Screenpipe ones)
result = client.table('transcripts').select(
    'id, source_file, audio_duration_seconds, language, full_text, speakers, created_at'
).order('created_at', desc=True).limit(25).execute()

print("\n" + "=" * 80)
print("RECENT TELEGRAM VOICE MEMO TRANSCRIPTS")
print("=" * 80)

count = 0
for r in result.data:
    source = r.get('source_file', '') or ''
    # Skip Screenpipe transcripts
    if 'screenpipe' in source.lower() or 'meeting_' in source.lower():
        continue
    
    count += 1
    if count > 10:
        break
    
    text = (r.get('full_text') or '')[:800].replace('\n', ' ').replace('\r', ' ')
    created = (r.get('created_at') or '')[:16]
    duration = int(r.get('audio_duration_seconds') or 0)
    tid = (r.get('id') or '')[:8]
    lang = r.get('language') or 'auto'
    
    print(f"\n{'='*60}")
    print(f"[{count}] Transcript {tid} - {created}")
    print(f"File: {source}")
    print(f"Duration: {duration}s | Language: {lang} | Chars: {len(r.get('full_text') or '')}")
    print(f"{'='*60}")
    print(f"CONTENT:\n{text}")
    if len(r.get('full_text') or '') > 800:
        print("... [truncated]")
    print()

