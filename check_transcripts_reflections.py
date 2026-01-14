"""Check recent transcripts and reflections."""
from supabase import create_client
import os

db = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Get recent transcripts
print('=== RECENT TRANSCRIPTS ===')
transcripts = db.table('transcripts').select('id, source_file, full_text, created_at').order('created_at', desc=True).limit(3).execute()
for t in transcripts.data:
    print(f"\n--- {t['source_file']} ---")
    print(f"ID: {t['id']}")
    text = t['full_text'][:800] if t['full_text'] else 'None'
    print(f"Text: {text}")

# Get recent reflections
print('\n\n=== RECENT REFLECTIONS ===')
reflections = db.table('reflections').select('id, title, topic_key, tags, created_at').order('created_at', desc=True).limit(10).execute()
for r in reflections.data:
    topic = r.get('topic_key', 'None')
    tags = r.get('tags', [])
    print(f"- {r['title']}")
    print(f"  topic_key: {topic}")
    print(f"  tags: {tags}")
    print()

# Check existing high-level reflections
print('\n=== EXISTING HIGH-LEVEL TOPICS ===')
all_topics = db.table('reflections').select('topic_key, title').not_.is_('topic_key', 'null').execute()
unique_topics = set()
for r in all_topics.data:
    if r.get('topic_key'):
        unique_topics.add(r['topic_key'])
print("Unique topic_keys:", sorted(unique_topics))
