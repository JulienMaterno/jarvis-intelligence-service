from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

c = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
r = c.table('documents').select('id,title,type').execute()
print('ACTUAL DOCUMENTS IN DATABASE:')
print('=' * 60)
for d in r.data:
    print(f'  - {d["title"]}')
    print(f'    Type: {d["type"]}')
    print(f'    ID: {d["id"]}')
    print()
print(f'Total: {len(r.data)} documents')
