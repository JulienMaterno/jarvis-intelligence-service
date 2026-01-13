#!/usr/bin/env python3
"""Index the missing content types: emails, books, highlights, linkedin_posts."""

import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from app.features.knowledge.indexer import reindex_all

async def main():
    print("=" * 60)
    print("INDEXING MISSING CONTENT TYPES")
    print("=" * 60)
    print()
    
    # Only index the new types
    results = await reindex_all(
        source_types=['email', 'book', 'highlight', 'linkedin_post'],
        limit=None  # All records
    )
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    total = 0
    for t, r in results.items():
        indexed = r.get("indexed", 0)
        errors = r.get("errors", 0)
        print(f"  {t}: {indexed} indexed, {errors} errors")
        total += indexed
    
    print(f"\nTOTAL NEW CHUNKS: {total}")

if __name__ == "__main__":
    asyncio.run(main())
