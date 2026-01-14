"""Check existing reflection topics to understand routing."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

print("=" * 80)
print("EXISTING REFLECTION TOPIC_KEYS (high-level buckets)")
print("=" * 80)

# Get unique topic_keys with their titles
r = sb.table('reflections').select('topic_key, title').order('created_at', desc=True).limit(50).execute()

# Group by topic_key
topics = {}
for x in r.data:
    key = x.get('topic_key', '')
    if key and key not in topics:
        topics[key] = x.get('title', '')

print("\nUnique topic_keys found:")
for key, title in sorted(topics.items()):
    print(f"  • {key:45} → {title[:50]}")

print("\n" + "=" * 80)
print("RECENT 10 REFLECTIONS (to see what's being created)")
print("=" * 80)

recent = sb.table('reflections').select('topic_key, title, created_at').order('created_at', desc=True).limit(10).execute()
for x in recent.data:
    date = x.get('created_at', '')[:10]
    key = x.get('topic_key', 'NO-KEY')
    title = x.get('title', '')[:55]
    print(f"  {date} | {key:35} | {title}")
