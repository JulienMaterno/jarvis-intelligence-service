"""Debug memory payloads."""
from dotenv import load_dotenv
load_dotenv()
import os
import json
from supabase import create_client

db = create_client(
    os.environ.get('SUPABASE_URL'),
    os.environ.get('SUPABASE_KEY')
)

result = db.table('mem0_memories').select('*').limit(5).execute()
for m in result.data:
    print('---')
    print(json.dumps(m, indent=2, default=str))
