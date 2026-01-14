"""
Dry-run test for smart context gatherer.

Tests that the gatherer only fetches what's relevant based on content.
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from app.features.analysis.context_gatherer import ContextGatherer
from app.services.database import SupabaseMultiDatabase

async def test_smart_gathering():
    """Test different transcript types to verify smart fetching."""
    
    db = SupabaseMultiDatabase()
    gatherer = ContextGatherer(db=db)
    
    test_cases = [
        {
            "name": "Simple Task",
            "transcript": "I need to remember to call the dentist tomorrow and also buy groceries.",
            "filename": "voice_20260114.ogg",
            "expected_contexts": ["open_tasks"],  # Should only fetch tasks
            "not_expected": ["documents", "applications", "relevant_emails"]
        },
        {
            "name": "Meeting with Person",
            "transcript": "I just had a great meeting with John about the new project. He mentioned Sarah might be interested too.",
            "filename": "meeting_20260114.ogg",
            "expected_contexts": ["contacts"],  # Should fetch contacts
            "not_expected": ["documents", "applications", "recent_journals"]
        },
        {
            "name": "Journal Entry",
            "transcript": "Today was a good day. This morning I woke up feeling grateful for the sunshine. My mood is great.",
            "filename": "Journal_20260114.ogg",
            "expected_contexts": ["recent_journals"],  # Should fetch journals
            "not_expected": ["applications", "relevant_emails", "calendar_events"]
        },
        {
            "name": "Job Application",
            "transcript": "I applied to the Antler fellowship program yesterday. Need to prepare for the interview next week.",
            "filename": "voice_20260114.ogg",
            "expected_contexts": ["applications", "calendar_events"],  # Jobs + calendar
            "not_expected": ["documents", "recent_journals"]  # No docs/journals needed
        },
        {
            "name": "CV Reference",
            "transcript": "I need to update my CV with my latest experience at Algenie. My resume should reflect my work history.",
            "filename": "voice_20260114.ogg",
            "expected_contexts": ["documents"],  # Should fetch documents
            "not_expected": ["calendar_events", "recent_journals", "applications"]
        },
        {
            "name": "Minimal transcript",
            "transcript": "Hello test.",
            "filename": "test.ogg",
            "expected_contexts": [],  # Very short, minimal context
            "not_expected": ["knowledge_base", "relevant_emails"]  # No RAG for short
        },
    ]
    
    print("=" * 70)
    print("SMART CONTEXT GATHERER - DRY RUN TEST")
    print("=" * 70)
    
    for tc in test_cases:
        print(f"\n{'='*70}")
        print(f"TEST: {tc['name']}")
        print(f"{'='*70}")
        print(f"Transcript: {tc['transcript'][:100]}...")
        print()
        
        # Gather context
        result = await gatherer.gather_context(
            transcript=tc["transcript"],
            filename=tc["filename"]
        )
        
        # Check what was fetched
        fetched_keys = [k for k in result.keys() if k != "extracted_entities" and result[k]]
        
        print(f"FETCHED CONTEXTS: {fetched_keys}")
        print(f"Context sizes:")
        for key in fetched_keys:
            if isinstance(result[key], list):
                print(f"  - {key}: {len(result[key])} items")
            else:
                print(f"  - {key}: {type(result[key]).__name__}")
        
        # Validate expectations
        print()
        print("VALIDATION:")
        all_passed = True
        
        for expected in tc["expected_contexts"]:
            if expected in result and result[expected]:
                print(f"  ✅ {expected} - correctly fetched")
            else:
                print(f"  ❌ {expected} - MISSING (expected to be fetched)")
                all_passed = False
        
        for not_expected in tc["not_expected"]:
            if not_expected not in result or not result[not_expected]:
                print(f"  ✅ {not_expected} - correctly NOT fetched")
            else:
                print(f"  ⚠️  {not_expected} - was fetched (not expected, but ok)")
        
        if all_passed:
            print(f"\n  ✅ TEST PASSED")
        else:
            print(f"\n  ❌ TEST HAD ISSUES")
        
        # Show extracted entities
        entities = result.get("extracted_entities", {})
        print(f"\n  Entities extracted: {list(entities.keys())}")
        if entities.get("person_names"):
            print(f"  - People: {entities['person_names'][:5]}")
        if entities.get("topics"):
            print(f"  - Topics: {entities['topics'][:5]}")

    print("\n" + "=" * 70)
    print("DRY RUN COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_smart_gathering())
