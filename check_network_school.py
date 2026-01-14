#!/usr/bin/env python3
"""Quick check for Network School emails."""
import os
from dotenv import load_dotenv
load_dotenv()

from app.services.database import SupabaseMultiDatabase

db = SupabaseMultiDatabase()

# Try different search patterns
print("=== Searching for Network School emails ===\n")

# Pattern 1: network school
r = db.client.table("emails").select("id, subject, sender, snippet").or_(
    "subject.ilike.%network%,subject.ilike.%school%,sender.ilike.%network%"
).limit(10).execute()
print(f"Pattern 1 (network OR school): {len(r.data)} results")
for e in r.data or []:
    print(f"  From: {e['sender'][:40]}")
    print(f"  Subject: {e['subject'][:60]}")
    print()

# Check total emails
r2 = db.client.table("emails").select("id", count="exact").execute()
print(f"\nTotal emails in DB: {r2.count}")

# Check if emails are in knowledge_chunks
r3 = db.client.table("knowledge_chunks").select("id").eq("source_type", "email").execute()
print(f"Emails indexed in RAG: {len(r3.data)}")
