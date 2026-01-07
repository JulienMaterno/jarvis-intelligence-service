"""Search for CV-specific memories."""
from dotenv import load_dotenv
load_dotenv()
import os
from supabase import create_client

db = create_client(
    os.environ.get('SUPABASE_URL'),
    os.environ.get('SUPABASE_KEY')
)

result = db.table('mem0_memories').select('payload').execute()

# Find memories mentioning CV-specific things
cv_keywords = ['Tsinghua', 'Roland Berger', 'Deloitte', 'Bayer', 'Porsche', 'RWTH', 'Toastmaster', 'Bachelor', 'Master', 'CSC scholarship', 'military', 'Augustdorf']

print(f"Total memories: {len(result.data)}")
print(f"\nSearching for CV-specific keywords: {cv_keywords}\n")

found = []
for m in result.data:
    content = m.get('payload', {}).get('data', '')
    source = m.get('payload', {}).get('source', '?')
    for kw in cv_keywords:
        if kw.lower() in content.lower():
            found.append({
                'keyword': kw,
                'content': content,
                'source': source
            })
            break

print(f"Found {len(found)} memories with CV keywords:\n")
for f in found:
    print(f"[{f['keyword']}] {f['content'][:100]}...")
    print(f"    Source: {f['source']}\n")
