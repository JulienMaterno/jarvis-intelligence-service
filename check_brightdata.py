import httpx
import json
import os

# Get API key from environment
api_key = os.getenv("BRIGHTDATA_API_KEY")
if not api_key:
    print("ERROR: Set BRIGHTDATA_API_KEY environment variable")
    print("  PowerShell: $env:BRIGHTDATA_API_KEY='your-key'")
    exit(1)

# List available datasets
r = httpx.get(
    'https://api.brightdata.com/datasets/v3/datasets',
    headers={'Authorization': f'Bearer {api_key}'}
)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    linkedin = [d for d in data if 'linkedin' in d.get('name', '').lower()]
    print(f"\nLinkedIn datasets ({len(linkedin)}):")
    for d in linkedin[:15]:
        print(f"  {d.get('id')}: {d.get('name')}")
        if d.get('input'):
            print(f"    Input: {d.get('input')}")
else:
    print(r.text)
