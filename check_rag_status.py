#!/usr/bin/env python3
"""Check RAG index status."""
import os
from dotenv import load_dotenv
load_dotenv()

from app.services.database import SupabaseMultiDatabase

db = SupabaseMultiDatabase()

# Get ALL unique source types with pagination
all_chunks = []
limit = 1000
offset = 0

while True:
    r = db.client.table('knowledge_chunks').select('source_type').range(offset, offset + limit - 1).execute()
    if not r.data:
        break
    all_chunks.extend(r.data)
    if len(r.data) < limit:
        break
    offset += limit

counts = {}
for c in all_chunks:
    t = c['source_type']
    counts[t] = counts.get(t, 0) + 1

print('ALL indexed types in RAG:')
for k,v in sorted(counts.items()):
    print(f'  {k}: {v}')
print(f'\nTotal chunks: {len(all_chunks)}')
