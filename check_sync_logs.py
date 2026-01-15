"""Check sync logs."""
from app.core.database import supabase

# Check sync logs for documents
result = supabase.table('sync_logs').select(
    'event_type, status, message, created_at'
).ilike('event_type', '%document%').order('created_at', desc=True).limit(10).execute()

print('=== DOCUMENT SYNC LOGS ===')
for log in result.data:
    created = log.get('created_at', '')
    event = log.get('event_type', '')
    status = log.get('status', '')
    msg = (log.get('message') or '')[:60]
    print(f'{created} | {event} | {status} | {msg}')

# Also check general sync logs
print('\n=== RECENT SYNC LOGS ===')
result2 = supabase.table('sync_logs').select(
    'event_type, status, message, created_at'
).order('created_at', desc=True).limit(15).execute()

for log in result2.data:
    created = log.get('created_at', '')
    event = log.get('event_type', '')
    status = log.get('status', '')
    msg = (log.get('message') or '')[:50]
    print(f'{created} | {event} | {status} | {msg}')
