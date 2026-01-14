#!/usr/bin/env python3
"""
Direct database test for Stage 1 context sources.

Tests each data source WITHOUT calling Anthropic.
This helps verify DB queries work before testing full pipeline.

Run: python test_db_sources.py
"""
import os
import sys
from dotenv import load_dotenv

# Fix Windows terminal encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))

from app.services.database import SupabaseMultiDatabase


def test_all_sources():
    """Test all 10 data sources directly."""
    db = SupabaseMultiDatabase()
    
    print("=" * 60)
    print("DATABASE SOURCE TEST (No Anthropic API needed)")
    print("=" * 60)
    
    results = {}
    
    # 1. Contacts
    print("\n1. CONTACTS...")
    try:
        r = db.client.table("contacts").select(
            "id, first_name, last_name, company"
        ).limit(5).execute()
        results["contacts"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['contacts']} contacts found")
        if r.data:
            print(f"   Sample: {r.data[0].get('first_name')} {r.data[0].get('last_name')}")
    except Exception as e:
        results["contacts"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 2. Meetings
    print("\n2. MEETINGS...")
    try:
        r = db.client.table("meetings").select(
            "id, title, date, contact_id"
        ).is_("deleted_at", "null").order("date", desc=True).limit(5).execute()
        results["meetings"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['meetings']} meetings found")
        if r.data:
            print(f"   Sample: {r.data[0].get('title')}")
    except Exception as e:
        results["meetings"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 3. Reflections
    print("\n3. REFLECTIONS...")
    try:
        r = db.client.table("reflections").select(
            "id, title, topic_key, tags"
        ).is_("deleted_at", "null").order("created_at", desc=True).limit(5).execute()
        results["reflections"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['reflections']} reflections found")
        if r.data:
            print(f"   Sample: {r.data[0].get('title')}")
    except Exception as e:
        results["reflections"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 4. Tasks
    print("\n4. TASKS...")
    try:
        r = db.client.table("tasks").select(
            "id, title, status, priority"
        ).neq("status", "Done").is_("deleted_at", "null").limit(5).execute()
        results["tasks"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['tasks']} open tasks found")
        if r.data:
            print(f"   Sample: [{r.data[0].get('status')}] {r.data[0].get('title')[:50]}")
    except Exception as e:
        results["tasks"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 5. Journals
    print("\n5. JOURNALS...")
    try:
        r = db.client.table("journals").select(
            "id, date, title, mood, summary, tomorrow_focus"
        ).order("date", desc=True).limit(5).execute()
        results["journals"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['journals']} journals found")
        if r.data:
            print(f"   Sample: {r.data[0].get('date')} - {r.data[0].get('title')[:40]}")
    except Exception as e:
        results["journals"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 6. Calendar
    print("\n6. CALENDAR EVENTS...")
    try:
        r = db.client.table("calendar_events").select(
            "id, summary, start_time, end_time"
        ).order("start_time", desc=True).limit(5).execute()
        results["calendar"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['calendar']} calendar events found")
        if r.data:
            print(f"   Sample: {r.data[0].get('summary')}")
    except Exception as e:
        results["calendar"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 7. Emails
    print("\n7. EMAILS...")
    try:
        r = db.client.table("emails").select(
            "id, subject, sender, date"
        ).order("date", desc=True).limit(5).execute()
        results["emails"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['emails']} emails found")
        if r.data:
            print(f"   Sample: {r.data[0].get('subject')[:50]}")
    except Exception as e:
        results["emails"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 8. Applications
    print("\n8. APPLICATIONS...")
    try:
        r = db.client.table("applications").select(
            "id, name, institution, status"
        ).order("updated_at", desc=True).limit(5).execute()
        results["applications"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['applications']} applications found")
        if r.data:
            print(f"   Sample: {r.data[0].get('name')} - {r.data[0].get('institution')}")
    except Exception as e:
        results["applications"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 9. Knowledge Chunks (RAG)
    print("\n9. KNOWLEDGE CHUNKS (RAG)...")
    try:
        r = db.client.table("knowledge_chunks").select(
            "id, source_type, content"
        ).limit(5).execute()
        results["knowledge_chunks"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['knowledge_chunks']} knowledge chunks found")
    except Exception as e:
        results["knowledge_chunks"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # 10. Memories (Mem0)
    print("\n10. MEMORIES (Mem0)...")
    try:
        r = db.client.table("mem0_memories").select(
            "id, payload"
        ).limit(5).execute()
        results["memories"] = len(r.data) if r.data else 0
        print(f"   ✅ {results['memories']} memories found")
        if r.data:
            payload = r.data[0].get('payload', {})
            content = payload.get('data', payload.get('content', ''))[:50]
            print(f"   Sample: {content}...")
    except Exception as e:
        results["memories"] = f"ERROR: {e}"
        print(f"   ❌ Error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    working = sum(1 for v in results.values() if isinstance(v, int) and v > 0)
    total = len(results)
    
    print(f"\n   Sources with data: {working}/{total}")
    
    for source, count in results.items():
        if isinstance(count, int):
            status = "✅" if count > 0 else "⚪"
            print(f"   {status} {source}: {count}")
        else:
            print(f"   ❌ {source}: {count}")
    
    return results


if __name__ == "__main__":
    test_all_sources()
