"""Check the newly uploaded CV."""
from dotenv import load_dotenv
load_dotenv()
import os
from supabase import create_client

db = create_client(
    os.environ.get('SUPABASE_URL'),
    os.environ.get('SUPABASE_KEY')
)

# Get latest document
result = db.table('documents').select('*').order('created_at', desc=True).limit(1).execute()
doc = result.data[0] if result.data else None

if doc:
    print(f"Title: {doc['title']}")
    print(f"Chars: {doc['char_count']} | Words: {doc['word_count']}")
    print(f"File URL: {doc['file_url']}")
    print(f"ID: {doc['id']}")

# Check ALL memories
print(f"\n{'='*60}")
result = db.table('mem0_memories').select('*').execute()
print(f"Total memories: {len(result.data)}")

# Find document-sourced memories
doc_mems = []
for m in result.data:
    payload = m.get('payload', {})
    source = str(payload.get('source', ''))
    if 'document' in source.lower():
        doc_mems.append({
            'source': source,
            'data': payload.get('data', ''),
            'type': payload.get('type', '?')
        })

print(f"Document-sourced memories: {len(doc_mems)}")
for dm in doc_mems:
    print(f"  [{dm['type']}] {dm['data'][:80]}...")
    print(f"       Source: {dm['source']}")
