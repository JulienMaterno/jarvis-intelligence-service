"""Index new content types for RAG with retry logic."""
import asyncio
import time
from app.features.knowledge.indexer import reindex_all

async def run_with_retry(source_types: list, max_retries: int = 3):
    """Run indexing with retries on failure."""
    for attempt in range(max_retries):
        try:
            results = await reindex_all(
                source_types=source_types,
                limit=None
            )
            return results
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                raise

async def main():
    all_results = {}
    
    # Index each type separately for better error handling
    for source_type in ['linkedin_post', 'email', 'beeper_message']:
        print(f"\n{'='*50}")
        print(f"Indexing {source_type}...")
        print(f"{'='*50}")
        try:
            results = await run_with_retry([source_type])
            all_results.update(results)
            print(f"✓ {source_type}: indexed={results[source_type]['indexed']}, errors={results[source_type]['errors']}")
        except Exception as e:
            print(f"✗ {source_type}: FAILED - {e}")
            all_results[source_type] = {'indexed': 0, 'errors': 1, 'failed': True}
    
    print(f"\n{'='*50}")
    print("FINAL RESULTS:")
    print(f"{'='*50}")
    for t, r in all_results.items():
        status = "✓" if not r.get('failed') else "✗"
        print(f"  {status} {t}: indexed={r['indexed']}, errors={r['errors']}")

if __name__ == "__main__":
    asyncio.run(main())
