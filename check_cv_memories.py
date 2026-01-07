"""Check what memories were seeded from the CV."""
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client

db = create_client(
    os.environ.get('SUPABASE_URL'),
    os.environ.get('SUPABASE_KEY')
)

# Get all memories
result = db.table('mem0_memories').select('*').execute()
print(f"Total memories: {len(result.data)}")

# Look for CV-sourced memories
cv_memories = []
aaron_memories = []

for m in result.data:
    payload = m.get('payload', {})
    content = payload.get('data', '')
    source = payload.get('source', '')
    
    if 'document' in source.lower():
        cv_memories.append({
            'content': content,
            'source': source,
            'type': payload.get('type', '?')
        })
    
    if 'Aaron' in content or 'aaron' in content.lower():
        aaron_memories.append({
            'content': content,
            'source': source,
            'type': payload.get('type', '?')
        })

print(f"\n=== CV/Document Sourced Memories ({len(cv_memories)}) ===")
for m in cv_memories:
    print(f"  [{m['type']}] {m['content'][:100]}")
    print(f"         Source: {m['source']}")

print(f"\n=== Memories Mentioning Aaron ({len(aaron_memories)}) ===")
for m in aaron_memories:
    print(f"  [{m['type']}] {m['content'][:100]}")
    print(f"         Source: {m['source']}")
