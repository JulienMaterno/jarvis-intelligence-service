"""Check documents sync status."""
from app.core.database import supabase

# Check documents table
result = supabase.table('documents').select(
    'id, title, created_at, last_sync_source, notion_page_id'
).order('created_at', desc=True).limit(10).execute()

print('=== RECENT DOCUMENTS IN SUPABASE ===')
print(f'Found: {len(result.data)} documents\n')

for d in result.data:
    title = (d.get('title') or 'N/A')[:50]
    created = d.get('created_at')
    sync_source = d.get('last_sync_source')
    notion_id = d.get('notion_page_id')
    print(f'Title: {title}')
    print(f'Created: {created}')
    print(f'Sync source: {sync_source}')
    print(f'Notion ID: {notion_id[:20] if notion_id else "None"}...')
    print('---')
