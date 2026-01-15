"""Test transcript search."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Test search with different terms
searches = ['exploring out 5', 'exploring out five', 'exploring', 'reflection']
for term in searches:
    result = supabase.table('transcripts').select('id, source_file').ilike('full_text', f'%{term}%').limit(3).execute()
    print(f'Search "{term}": {len(result.data)} results')
    for t in result.data[:2]:
        print(f'  - {t.get("source_file")}')
    print()
