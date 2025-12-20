import os
import anthropic
import sys

# Try to get key from env var, otherwise print error
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("ANTHROPIC_API_KEY not found in environment.")
    # Try to see if we can find it in a local file that might have been missed or just ask user
    # But for now, let's assume the user might have it in their terminal session or I can't run it.
    sys.exit(1)

try:
    client = anthropic.Anthropic(api_key=api_key)
    print("Fetching models...")
    models = client.models.list()
    found_4_5 = False
    for m in models:
        if "4-5" in m.id or "sonnet" in m.id:
            print(f"Found model: {m.id}")
            if "4-5" in m.id:
                found_4_5 = True
    
    if not found_4_5:
        print("No explicit '4-5' model found. Listing all:")
        for m in models:
            print(m.id)

except Exception as e:
    print(f"Error: {e}")
