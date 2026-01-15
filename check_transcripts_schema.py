"""Check recent transcripts and schema."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get recent transcripts
result = supabase.table('transcripts').select('id, source_file, full_text, created_at, language').order('created_at', desc=True).limit(5).execute()
print('RECENT TRANSCRIPTS:')
for t in result.data:
    source = t.get('source_file', 'Unknown')
    created = t.get('created_at', '')[:19] if t.get('created_at') else 'N/A'
    lang = t.get('language', 'N/A')
    text_preview = (t.get('full_text') or '')[:100]
    print(f"  - {source}")
    print(f"    Created: {created}")
    print(f"    Lang: {lang}")
    print(f"    Preview: {text_preview}...")
    print()
