"""Debug applications table and tools."""
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Test 1: Get Z Fellows directly with ALL sync-related fields
print('=== TEST 1: Z Fellows Application ===')
result = supabase.table('applications').select('id,name,status,content,last_sync_source,notion_page_id,notion_updated_at,updated_at').ilike('name', '%z fellow%').execute()
for app in result.data:
    name = app.get('name')
    status = app.get('status')
    content = app.get('content') or ''
    last_sync = app.get('last_sync_source')
    notion_id = app.get('notion_page_id')
    notion_updated = app.get('notion_updated_at')
    updated_at = app.get('updated_at')
    print(f'Name: {name}')
    print(f'Status: {status}')
    print(f'Content length: {len(content)} chars')
    print(f'Last sync source: {last_sync}')
    print(f'Notion page ID: {notion_id}')
    print(f'Notion updated_at: {notion_updated}')
    print(f'Supabase updated_at: {updated_at}')
    print(f'Content preview:')
    print(content[:500] if content else "EMPTY")
    print()

# Test 2: Get Antler Singapore
print('=== TEST 2: Antler Singapore ===')
result2 = supabase.table('applications').select('id,name,status').ilike('name', '%antler%').execute()
for app in result2.data:
    print(f"Name: {app.get('name')} | Status: {app.get('status')}")

# Test 3: All distinct statuses
print()
print('=== TEST 3: All Status Values ===')
result3 = supabase.table('applications').select('status').execute()
statuses = set(app.get('status') for app in result3.data if app.get('status'))
print(f'Statuses: {sorted(statuses)}')

# Test 4: Check sync logs for applications
print()
print('=== TEST 4: Recent Application Sync Logs ===')
result4 = supabase.table('sync_logs').select('event_type,status,message,created_at').like('event_type', '%application%').order('created_at', desc=True).limit(10).execute()
for log in result4.data:
    created = log.get('created_at', '')[:19]
    event = log.get('event_type', '')
    status = log.get('status', '')
    msg = (log.get('message') or '')[:80]
    print(f'{created} | {event} | {status} | {msg}')
