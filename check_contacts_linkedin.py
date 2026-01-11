"""Quick script to check contacts with LinkedIn URLs."""
from supabase import create_client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ojnllduebzfxqmiyinhx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_KEY:
    print("Set SUPABASE_KEY environment variable")
    exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get contacts with LinkedIn URL
r = sb.table('contacts').select('id,first_name,last_name,linkedin_url').not_.is_('linkedin_url', 'null').limit(15).execute()
print("=== CONTACTS WITH LINKEDIN URL ===")
for c in r.data:
    name = f"{c['first_name']} {c['last_name']}"
    url = c['linkedin_url'][:50] if c['linkedin_url'] else 'None'
    print(f"  {name}: {url}...")

# Count total with URL
r_count = sb.table('contacts').select('id', count='exact').not_.is_('linkedin_url', 'null').execute()
print(f"\nTotal contacts with LinkedIn URL: {r_count.count}")

# Count total active contacts
r_total = sb.table('contacts').select('id', count='exact').is_('deleted_at', 'null').execute()
print(f"Total active contacts: {r_total.count}")

# Check a contact named Jenny
print("\n=== SEARCH FOR JENNY ===")
r_jenny = sb.table('contacts').select('id,first_name,last_name,company,email').ilike('first_name', '%jenny%').execute()
if r_jenny.data:
    for c in r_jenny.data:
        print(f"  {c['first_name']} {c['last_name']} - {c.get('company', 'N/A')} - {c.get('email', 'N/A')}")
else:
    print("  No contacts named Jenny found")
