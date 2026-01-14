import asyncio
from dotenv import load_dotenv
load_dotenv()

from app.features.knowledge import semantic_search
from app.core.database import supabase

async def test():
    print('=== Testing RAG search for Network School ===')
    
    # Test 1: Email-only search
    results = await semantic_search(
        query='Network School signup email acceptance link',
        db=supabase,
        source_types=['email'],
        limit=5
    )
    print(f'Email search found {len(results)} results:')
    for r in results:
        sim = r.get('similarity', 0)
        content = r.get('content', '')[:200].replace('\n', ' ')
        print(f'  - sim={sim:.3f}: {content}...')
    
    # Test 2: Lower threshold
    print('\n--- Lower threshold (0.3) ---')
    results = await semantic_search(
        query='Network School',
        db=supabase,
        source_types=['email'],
        limit=5,
        similarity_threshold=0.3
    )
    print(f'Low threshold found {len(results)} results:')
    for r in results:
        sim = r.get('similarity', 0)
        content = r.get('content', '')[:150].replace('\n', ' ')
        print(f'  - sim={sim:.3f}: {content}...')

asyncio.run(test())
