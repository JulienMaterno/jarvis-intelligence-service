"""Check all table schemas."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

tables = ['transcripts', 'meetings', 'journals', 'reflections', 'tasks', 'contacts', 'applications', 'documents']

for table in tables:
    try:
        result = supabase.table(table).select('*').limit(1).execute()
        if result.data:
            cols = sorted(result.data[0].keys())
            print(f'{table}: {len(cols)} columns')
            print(f'  {", ".join(cols)}')
        else:
            print(f'{table}: No data')
    except Exception as e:
        print(f'{table}: ERROR - {str(e)[:80]}')
    print()
