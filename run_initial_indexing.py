#!/usr/bin/env python3
"""
Initial RAG Knowledge Base Indexing Script

Run this ONCE after running the 016_add_knowledge_chunks.sql migration.
This indexes all existing content into the knowledge_chunks table.

Usage:
    python run_initial_indexing.py [--content-types TYPE1,TYPE2,...] [--limit N]

Examples:
    # Index everything (recommended first run)
    python run_initial_indexing.py
    
    # Index only specific types
    python run_initial_indexing.py --content-types transcript,meeting,journal
    
    # Test with limited records
    python run_initial_indexing.py --limit 10
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Verify required env vars
required_vars = ["SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY"]
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    logger.error(f"Missing required environment variables: {missing}")
    sys.exit(1)

from app.features.knowledge import get_knowledge_service, KnowledgeService


async def run_indexing(
    content_types: list[str] | None = None,
    limit: int | None = None,
    verbose: bool = False
):
    """Run the initial indexing."""
    
    logger.info("=" * 60)
    logger.info("🧠 JARVIS RAG Knowledge Base - Initial Indexing")
    logger.info("=" * 60)
    
    # Get knowledge service
    knowledge = get_knowledge_service()
    
    # Check health first
    logger.info("\n📊 Checking system health...")
    health = await knowledge.health_check()
    
    if not health["supabase_connected"]:
        logger.error("❌ Cannot connect to Supabase!")
        return False
    
    if not health["openai_configured"]:
        logger.error("❌ OpenAI API key not configured!")
        return False
    
    logger.info(f"✅ Supabase: Connected")
    logger.info(f"✅ OpenAI: Configured")
    logger.info(f"📦 Current chunks in database: {health['total_chunks']}")
    
    # Get current stats
    logger.info("\n📈 Current indexing stats:")
    stats = await knowledge.get_stats()
    for source_type, count in sorted(stats.items()):
        logger.info(f"   {source_type}: {count} chunks")
    
    # Run indexing
    logger.info("\n🚀 Starting reindex_all...")
    start_time = datetime.now()
    
    try:
        results = await knowledge.reindex_all(
            content_types=content_types,
            limit=limit
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ INDEXING COMPLETE!")
        logger.info("=" * 60)
        logger.info(f"\n⏱️  Time elapsed: {elapsed:.1f} seconds")
        
        # Show results
        logger.info("\n📊 Results by content type:")
        total_indexed = 0
        total_errors = 0
        
        for content_type, result in sorted(results.items()):
            indexed = result.get("indexed", 0)
            errors = result.get("errors", 0)
            total_indexed += indexed
            total_errors += errors
            
            status = "✅" if errors == 0 else "⚠️"
            logger.info(f"   {status} {content_type}: {indexed} indexed, {errors} errors")
        
        logger.info(f"\n📈 TOTALS: {total_indexed} chunks indexed, {total_errors} errors")
        
        # Get updated stats
        logger.info("\n📦 Final chunk counts:")
        final_stats = await knowledge.get_stats()
        for source_type, count in sorted(final_stats.items()):
            logger.info(f"   {source_type}: {count} chunks")
        
        total_chunks = sum(final_stats.values())
        logger.info(f"\n   TOTAL: {total_chunks} chunks in knowledge base")
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_search(query: str = "meeting with"):
    """Quick test search after indexing."""
    logger.info("\n" + "=" * 60)
    logger.info("🔍 Quick Search Test")
    logger.info("=" * 60)
    
    knowledge = get_knowledge_service()
    
    results = await knowledge.search(query, limit=5)
    
    logger.info(f"\nQuery: '{query}'")
    logger.info(f"Found: {len(results)} results\n")
    
    for i, r in enumerate(results, 1):
        logger.info(f"{i}. [{r['source_type']}] score={r['similarity']:.3f}")
        content_preview = r['content'][:100].replace('\n', ' ')
        logger.info(f"   {content_preview}...")
        if r.get('metadata'):
            logger.info(f"   Metadata: {r['metadata']}")
        logger.info("")


def main():
    parser = argparse.ArgumentParser(
        description="Index existing content into the RAG knowledge base"
    )
    parser.add_argument(
        "--content-types",
        type=str,
        default=None,
        help="Comma-separated list of content types to index (e.g., transcript,meeting,journal)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records per content type (for testing)"
    )
    parser.add_argument(
        "--test-search",
        action="store_true",
        help="Run a test search after indexing"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Parse content types
    content_types = None
    if args.content_types:
        content_types = [t.strip() for t in args.content_types.split(",")]
        logger.info(f"Indexing only: {content_types}")
    
    # Run indexing
    success = asyncio.run(run_indexing(
        content_types=content_types,
        limit=args.limit,
        verbose=args.verbose
    ))
    
    # Run test search if requested
    if success and args.test_search:
        asyncio.run(test_search())
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
