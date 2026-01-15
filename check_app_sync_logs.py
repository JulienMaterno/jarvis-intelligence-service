"""Check sync logs for applications."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Check sync logs for applications
print('=== RECENT APPLICATION SYNC LOGS ===\n')
result = supabase.table('sync_logs').select('*').like('event_type', '%pplication%').order('created_at', desc=True).limit(20).execute()

if not result.data:
    print('No application sync logs found!')
else:
    for log in result.data:
        created = log.get('created_at', '')[:19] if log.get('created_at') else 'N/A'
        event = log.get('event_type', 'N/A')
        status = log.get('status', 'N/A')
        msg = (log.get('message') or 'No message')[:120]
        details = log.get('details', {})
        print(f'{created} | {event} | {status}')
        print(f'  Message: {msg}')
        if details:
            print(f'  Details: {str(details)[:150]}')
        print()
