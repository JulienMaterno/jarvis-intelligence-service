import httpx
import json

# List available datasets
r = httpx.get(
    'https://api.brightdata.com/datasets/v3/datasets',
    headers={'Authorization': 'Bearer 8b632e7e-bda6-4d2b-91fd-25de30d60c9d'}
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
