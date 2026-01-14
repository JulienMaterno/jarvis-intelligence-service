#!/usr/bin/env python3
"""
Dry-run test for Stage 1 context gathering.

Tests that context_gatherer.py fetches from ALL sources:
- Contacts, Meetings, Reflections, Tasks, Journals
- Calendar, Applications, Emails
- Memories (Mem0), RAG/Knowledge chunks

Run: python test_stage1_dry_run.py
"""
import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Fix Windows terminal encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Load env vars
load_dotenv()

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.features.analysis.context_gatherer import gather_context_for_transcript
from app.services.database import SupabaseMultiDatabase


async def run_dry_test():
    """Run a dry test of Stage 1 context gathering."""
    
    # Test transcript - mentions specific people and topics
    test_transcript = """
    So I had a really good conversation with Kerem today about the new startup idea.
    We discussed the Istanbul market and how to approach investors there.
    Also need to remember to follow up with Jenny about the legal documents.
    Been thinking a lot about my health lately, specifically about sleep and exercise.
    Tomorrow I want to focus on finishing the Jarvis voice processing feature.
    Oh and I have that meeting with Enver coming up, need to prepare for that.
    """
    
    print("=" * 60)
    print("🧪 STAGE 1 DRY RUN TEST")
    print("=" * 60)
    print("\n📝 Test Transcript:")
    print("-" * 40)
    print(test_transcript.strip())
    print("-" * 40)
    
    # Initialize database
    db = SupabaseMultiDatabase()
    
    print("\n🔄 Running context gathering (Stage 1)...")
    print("   This uses Claude Haiku for entity extraction,")
    print("   then queries 10 different data sources.\n")
    
    # Run context gathering
    result = await gather_context_for_transcript(
        transcript=test_transcript,
        filename="test_dry_run.ogg",
        db=db,
        recording_date=None
    )
    
    # Display results
    print("\n" + "=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    
    # 1. Extracted entities
    entities = result.get("entities", {})
    print("\n🏷️  EXTRACTED ENTITIES (from Haiku):")
    print(f"   People: {entities.get('people', [])}")
    print(f"   Topics: {entities.get('topics', [])}")
    print(f"   Dates: {entities.get('dates', [])}")
    print(f"   Tasks: {entities.get('potential_tasks', [])}")
    
    # 2. Rich context from each source
    rich_context = result.get("rich_context", {})
    
    print("\n📦 CONTEXT FROM EACH SOURCE:")
    
    # Contacts
    contacts = rich_context.get("contacts", [])
    print(f"\n   👤 Contacts: {len(contacts)} found")
    for c in contacts[:3]:
        print(f"      - {c.get('first_name', '')} {c.get('last_name', '')} ({c.get('company', 'no company')})")
    
    # Meetings
    meetings = rich_context.get("meetings", [])
    print(f"\n   📅 Meetings: {len(meetings)} found")
    for m in meetings[:3]:
        print(f"      - {m.get('title', 'untitled')} ({m.get('date', 'no date')[:10] if m.get('date') else 'no date'})")
    
    # Reflections
    reflections = rich_context.get("reflections", [])
    print(f"\n   💭 Reflections: {len(reflections)} found")
    for r in reflections[:3]:
        print(f"      - {r.get('title', 'untitled')}")
    
    # Tasks
    tasks = rich_context.get("tasks", [])
    print(f"\n   ✅ Tasks: {len(tasks)} found")
    for t in tasks[:3]:
        status = t.get('status', 'unknown')
        print(f"      - [{status}] {t.get('title', 'untitled')[:50]}")
    
    # Journals
    journals = rich_context.get("journals", [])
    print(f"\n   📓 Journals: {len(journals)} found")
    for j in journals[:3]:
        print(f"      - {j.get('date', 'no date')} - {j.get('title', 'untitled')[:40]}")
    
    # Calendar
    calendar = rich_context.get("calendar", [])
    print(f"\n   🗓️  Calendar: {len(calendar)} events found")
    for e in calendar[:3]:
        print(f"      - {e.get('summary', 'untitled')} ({e.get('start_time', '')[:10] if e.get('start_time') else '?'})")
    
    # Emails
    emails = rich_context.get("emails", [])
    print(f"\n   📧 Emails: {len(emails)} found")
    for e in emails[:3]:
        print(f"      - From: {e.get('sender', '?')[:30]} - {e.get('subject', 'no subject')[:30]}")
    
    # Applications
    applications = rich_context.get("applications", [])
    print(f"\n   💼 Applications: {len(applications)} found")
    for a in applications[:3]:
        print(f"      - {a.get('company_name', '?')} - {a.get('position', '?')}")
    
    # Memories (Mem0)
    memories = rich_context.get("memories", [])
    print(f"\n   🧠 Memories (Mem0): {len(memories)} found")
    for m in memories[:5]:
        content = m.get("content", "")[:80]
        category = m.get("category", "")
        print(f"      - [{category}] {content}...")
    
    # RAG / Knowledge Base
    knowledge = rich_context.get("knowledge_base", [])
    print(f"\n   🔮 Knowledge Base (RAG): {len(knowledge)} chunks found")
    for k in knowledge[:5]:
        source_type = k.get("source_type", "unknown")
        similarity = k.get("similarity", 0)
        content = k.get("content", "")[:60]
        print(f"      - [{source_type}] (sim: {similarity:.2f}) {content}...")
    
    # 3. Token usage estimate
    print("\n" + "=" * 60)
    print("📏 TOKEN BUDGET CHECK")
    print("=" * 60)
    
    # Estimate context size
    context_json = json.dumps(rich_context, default=str)
    context_chars = len(context_json)
    context_tokens_est = context_chars // 4  # rough estimate
    
    print(f"\n   Context size: {context_chars:,} characters")
    print(f"   Estimated tokens: ~{context_tokens_est:,}")
    print(f"   MAX_CONTEXT_CHARS: 100,000")
    print(f"   Sonnet context window: 200,000 tokens")
    
    if context_chars > 100000:
        print(f"\n   ⚠️  WARNING: Context exceeds MAX_CONTEXT_CHARS!")
        print(f"   Will be truncated to 100,000 chars")
    else:
        remaining = 100000 - context_chars
        print(f"\n   ✅ Within budget. Room for {remaining:,} more chars")
    
    # 4. Summary
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    
    sources_with_data = sum([
        1 if contacts else 0,
        1 if meetings else 0,
        1 if reflections else 0,
        1 if tasks else 0,
        1 if journals else 0,
        1 if calendar else 0,
        1 if emails else 0,
        1 if applications else 0,
        1 if memories else 0,
        1 if knowledge else 0,
    ])
    
    print(f"\n   Data sources checked: 10")
    print(f"   Sources with data: {sources_with_data}/10")
    print(f"   Total items fetched: {len(contacts) + len(meetings) + len(reflections) + len(tasks) + len(journals) + len(calendar) + len(emails) + len(applications) + len(memories) + len(knowledge)}")
    
    if sources_with_data >= 7:
        print("\n   ✅ Stage 1 is working well - fetching from multiple sources!")
    elif sources_with_data >= 4:
        print("\n   ⚠️  Partial success - some sources returned data")
    else:
        print("\n   ❌ Issue: Very few sources returned data")
    
    return result


if __name__ == "__main__":
    result = asyncio.run(run_dry_test())
