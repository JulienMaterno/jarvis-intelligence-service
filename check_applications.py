#!/usr/bin/env python3
"""Check application fields for RAG indexing."""

import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get application sample
apps = client.table('applications').select('*').limit(5).execute()

print(f"Total applications checked: {len(apps.data)}")
print("=" * 60)

for app in apps.data:
    print(f"\nApplication: {app.get('name', 'N/A')}")
    print(f"  Institution: {app.get('institution', 'N/A')}")
    print(f"  Type: {app.get('application_type', 'N/A')}")
    print(f"  Context: {len(str(app.get('context') or ''))} chars")
    print(f"  Content: {len(str(app.get('content') or ''))} chars")
    print(f"  Notes: {len(str(app.get('notes') or ''))} chars")
    
    qa = app.get('qa_pairs')
    if qa:
        if isinstance(qa, list):
            print(f"  QA Pairs: {len(qa)} items")
            for i, item in enumerate(qa[:2]):
                print(f"    [{i}] {str(item)[:100]}...")
        else:
            print(f"  QA Pairs: {type(qa)}")
    else:
        print("  QA Pairs: None")

print("\n" + "=" * 60)
print("\nChecking transcripts chunking...")

# Check transcript lengths
transcripts = client.table('transcripts').select('id, source_file, full_text').limit(5).execute()

for t in transcripts.data:
    text_len = len(t.get('full_text') or '')
    print(f"\n{t.get('source_file', 'Unknown')}: {text_len} chars (~{text_len//4} tokens)")
    
# Check how many transcripts have segments
segments_check = client.table('transcripts').select('id, segments').limit(10).execute()
with_segments = sum(1 for t in segments_check.data if t.get('segments'))
print(f"\nTranscripts with segments: {with_segments}/{len(segments_check.data)}")
