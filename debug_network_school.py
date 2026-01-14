#!/usr/bin/env python3
"""Debug Network School email in RAG."""
import os
from dotenv import load_dotenv
load_dotenv()

from app.services.database import SupabaseMultiDatabase

db = SupabaseMultiDatabase()

print("=== Checking RAG for Network School ===\n")

# 1. Check if Network School is in knowledge_chunks
r = db.client.table("knowledge_chunks").select(
    "id, source_type, content, source_id"
).ilike("content", "%Network School%").limit(10).execute()

print(f"RAG chunks containing 'Network School': {len(r.data)}")
for c in r.data:
    print(f"  Type: {c['source_type']}")
    print(f"  Source ID: {c['source_id']}")
    print(f"  Content: {c['content'][:200]}...")
    print()

# 2. Check specific email
print("\n=== Checking emails table ===\n")
r2 = db.client.table("emails").select("id, subject, sender, body_text").ilike(
    "sender", "%network%"
).execute()
print(f"Emails from Network School: {len(r2.data)}")
for e in r2.data:
    print(f"  ID: {e['id']}")
    print(f"  Subject: {e['subject']}")
    print(f"  Sender: {e['sender']}")
    body = e.get('body_text') or ''
    print(f"  Body length: {len(body)} chars")
    print()

# 3. Check if those email IDs are indexed
print("\n=== Checking if emails are indexed ===\n")
for e in r2.data:
    email_id = e['id']
    indexed = db.client.table("knowledge_chunks").select("id").eq(
        "source_id", email_id
    ).eq("source_type", "email").execute()
    print(f"Email {e['subject'][:40]}: {'✅ INDEXED' if indexed.data else '❌ NOT INDEXED'}")
