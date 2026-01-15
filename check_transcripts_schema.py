"""Check transcripts table schema."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get actual columns in transcripts table
result = supabase.table('transcripts').select('*').limit(1).execute()
if result.data:
    print('ACTUAL COLUMNS IN TRANSCRIPTS TABLE:')
    for col in sorted(result.data[0].keys()):
        val = result.data[0][col]
        val_type = type(val).__name__
        val_preview = str(val)[:50] if val else 'None'
        print(f'  - {col}: {val_type} = {val_preview}')
else:
    print('No transcripts found')
