"""Check documents table and do full system dry run."""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
import os

def check_documents_table():
    """Check if documents table exists."""
    print("=" * 60)
    print("CHECKING DOCUMENTS TABLE")
    print("=" * 60)
    
    c = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    try:
        r = c.table('documents').select('id,title,type').execute()
        print(f"✅ DOCUMENTS TABLE EXISTS!")
        print(f"   Records: {len(r.data)}")
        for d in r.data:
            print(f"   - {d['title']} ({d.get('type', 'N/A')})")
        return True
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def check_via_information_schema():
    """Check via information_schema like the web chat does."""
    print("\n" + "=" * 60)
    print("CHECKING VIA information_schema (like web chat)")
    print("=" * 60)
    
    c = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    # This is what the web chat's query_database tool does
    try:
        r = c.rpc('query_database', {
            'sql': "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%doc%'"
        }).execute()
        print(f"RPC Result: {r.data}")
    except Exception as e:
        print(f"RPC failed (expected): {e}")
    
    # Try raw SQL via postgres (won't work via Supabase client)
    # The issue is that the web chat uses a specific query_database function
    
    # Let's check what tables the REST API can see
    print("\nTables accessible via REST API:")
    tables_to_check = ['documents', 'contacts', 'meetings', 'tasks', 'applications']
    for table in tables_to_check:
        try:
            r = c.table(table).select('id').limit(1).execute()
            print(f"  ✅ {table}: accessible ({len(r.data)} sample)")
        except Exception as e:
            print(f"  ❌ {table}: NOT accessible - {e}")

def get_last_transcript():
    """Get the most recent transcript for dry run."""
    print("\n" + "=" * 60)
    print("GETTING LAST TRANSCRIPT")
    print("=" * 60)
    
    c = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    r = c.table('transcripts').select('id,source_file,full_text,language,created_at').order('created_at', desc=True).limit(1).execute()
    
    if r.data:
        t = r.data[0]
        print(f"ID: {t['id']}")
        print(f"File: {t['source_file']}")
        print(f"Language: {t['language']}")
        print(f"Created: {t['created_at']}")
        print(f"Text length: {len(t['full_text'])} chars")
        print(f"\nFirst 500 chars:")
        print(t['full_text'][:500])
        return t
    return None

async def dry_run_stage1(transcript_text: str, filename: str):
    """Run Stage 1: Entity extraction + smart context gathering."""
    print("\n" + "=" * 60)
    print("STAGE 1: ENTITY EXTRACTION + CONTEXT GATHERING")
    print("=" * 60)
    
    from app.features.analysis.context_gatherer import ContextGatherer
    from app.services.database import SupabaseMultiDatabase
    
    db = SupabaseMultiDatabase()
    gatherer = ContextGatherer(db=db)
    
    result = await gatherer.gather_context(
        transcript=transcript_text,
        filename=filename
    )
    
    # Show extracted entities
    entities = result.get("extracted_entities", {})
    print("\n📊 EXTRACTED ENTITIES:")
    print(f"  Person names: {entities.get('person_names', [])}")
    print(f"  Companies: {entities.get('companies', [])}")
    print(f"  Topics: {entities.get('topics', [])}")
    print(f"  Content type: {entities.get('content_type', 'unknown')}")
    print(f"  Primary person: {entities.get('primary_person')}")
    print(f"  Action intent: {entities.get('action_intent', [])}")
    
    # Show what context was fetched
    fetched = [k for k in result.keys() if k != 'extracted_entities' and result[k]]
    print(f"\n📦 CONTEXT FETCHED: {fetched}")
    
    for key in fetched:
        data = result[key]
        if isinstance(data, list):
            print(f"\n  {key}: {len(data)} items")
            for item in data[:3]:
                if isinstance(item, dict):
                    # Show first few fields
                    preview = str(item)[:100]
                    print(f"    - {preview}...")
        else:
            print(f"\n  {key}: {type(data).__name__}")
    
    return result

async def dry_run_stage2(transcript_text: str, filename: str, context: dict):
    """Show what Stage 2 would receive."""
    print("\n" + "=" * 60)
    print("STAGE 2: ANALYSIS INPUT PREVIEW")
    print("=" * 60)
    
    import json
    
    # Calculate context size
    context_json = json.dumps(context, default=str)
    print(f"\n📊 CONTEXT SIZE: {len(context_json):,} chars (~{len(context_json)//4:,} tokens)")
    print(f"📊 TRANSCRIPT SIZE: {len(transcript_text):,} chars (~{len(transcript_text)//4:,} tokens)")
    print(f"📊 TOTAL INPUT: ~{(len(context_json) + len(transcript_text))//4:,} tokens")
    
    # Show the actual context that would be passed
    print("\n📋 CONTEXT SECTIONS PASSED TO STAGE 2:")
    for key, value in context.items():
        if key == "extracted_entities":
            continue
        if isinstance(value, list):
            print(f"  - {key}: {len(value)} items")
        elif value:
            print(f"  - {key}: present")
    
    # Show what reflections are available (important for routing)
    if "existing_reflections" in context:
        print("\n🔄 EXISTING REFLECTION TOPICS (for routing):")
        for r in context["existing_reflections"][:10]:
            print(f"  - {r.get('topic_key', 'N/A')}: {r.get('title', 'N/A')}")
    
    # Show contacts found
    if "contacts" in context:
        print("\n👤 CONTACTS MATCHED:")
        for c in context["contacts"][:5]:
            primary = " ⭐" if c.get("is_primary_match") else ""
            suggestion = " (suggestion)" if c.get("is_suggestion") else ""
            print(f"  - {c.get('name', 'Unknown')}{primary}{suggestion}")

async def main():
    # Check documents table
    check_documents_table()
    check_via_information_schema()
    
    # Get last transcript
    transcript = get_last_transcript()
    
    if transcript:
        # Run Stage 1
        context = await dry_run_stage1(
            transcript_text=transcript['full_text'],
            filename=transcript['source_file']
        )
        
        # Preview Stage 2 input
        await dry_run_stage2(
            transcript_text=transcript['full_text'],
            filename=transcript['source_file'],
            context=context
        )
    
    print("\n" + "=" * 60)
    print("DRY RUN COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
