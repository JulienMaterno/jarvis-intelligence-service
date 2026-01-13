#!/usr/bin/env python3
"""
Incremental Indexing Service for RAG Knowledge Base.

This handles smart reindexing that:
1. Only re-embeds content that has actually changed
2. Uses content hashes to detect changes
3. Handles new records automatically
4. Can be run daily via Cloud Scheduler

Usage:
    python run_incremental_indexing.py                  # Incremental (last 24h)
    python run_incremental_indexing.py --hours 48      # Custom time window
    python run_incremental_indexing.py --full          # Full reindex (all)
"""

import asyncio
import logging
import argparse
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def content_hash(text: str) -> str:
    """Generate hash for content comparison."""
    return hashlib.md5(text.encode()).hexdigest()


async def run_incremental_indexing(hours: int = 24, full: bool = False):
    """
    Run incremental indexing for recently updated content.
    
    Strategy:
    1. For each content type, find records updated since cutoff
    2. Check if their content_hash differs from existing chunks
    3. Only re-embed if content actually changed
    4. Also index any records missing from knowledge_chunks
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from app.services.database import SupabaseMultiDatabase
    from app.features.knowledge.indexer import (
        index_transcript, index_meeting, index_journal, index_reflection,
        index_contact, index_calendar_event, index_application, index_document,
        TABLE_NAME_MAP
    )
    
    db = SupabaseMultiDatabase()
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()
    
    results = {
        "checked": 0,
        "skipped_unchanged": 0,
        "indexed_new": 0,
        "indexed_updated": 0,
        "errors": 0,
        "by_type": {}
    }
    
    content_types = [
        ("transcript", "transcripts", index_transcript, "full_text"),
        ("meeting", "meetings", index_meeting, "summary"),
        ("journal", "journals", index_journal, "content"),
        ("reflection", "reflections", index_reflection, "content"),
        ("contact", "contacts", index_contact, None),  # Contact uses multiple fields
        ("calendar", "calendar_events", index_calendar_event, "summary"),
        ("application", "applications", index_application, "context"),
        ("document", "documents", index_document, "content"),
    ]
    
    for source_type, table_name, index_func, content_field in content_types:
        logger.info(f"\nProcessing {source_type}...")
        type_results = {"checked": 0, "skipped": 0, "new": 0, "updated": 0, "errors": 0}
        
        try:
            # Get records to check
            if full:
                records = db.client.table(table_name).select("id, updated_at").execute()
            else:
                # Only check recently updated records
                records = db.client.table(table_name).select("id, updated_at").gte(
                    "updated_at", cutoff_str
                ).execute()
            
            if not records.data:
                logger.info(f"  No {source_type} records to check")
                continue
            
            logger.info(f"  Found {len(records.data)} records to check")
            
            # Get existing chunks for comparison
            existing_chunks = db.client.table("knowledge_chunks").select(
                "source_id, content_hash"
            ).eq("source_type", source_type).execute()
            
            existing_hashes = {}
            for chunk in existing_chunks.data:
                sid = chunk["source_id"]
                if sid not in existing_hashes:
                    existing_hashes[sid] = set()
                if chunk.get("content_hash"):
                    existing_hashes[sid].add(chunk["content_hash"])
            
            for record in records.data:
                record_id = record["id"]
                type_results["checked"] += 1
                
                try:
                    # Check if this record needs reindexing
                    needs_index = False
                    is_new = record_id not in existing_hashes
                    
                    if is_new:
                        # New record - definitely needs indexing
                        needs_index = True
                    elif content_field:
                        # Get current content to compare hash
                        full_record = db.client.table(table_name).select(
                            content_field
                        ).eq("id", record_id).execute()
                        
                        if full_record.data:
                            current_content = full_record.data[0].get(content_field) or ""
                            current_hash = content_hash(current_content)
                            
                            # Check if hash changed
                            if current_hash not in existing_hashes.get(record_id, set()):
                                needs_index = True
                    else:
                        # No simple content field (e.g., contacts) - reindex if updated
                        needs_index = True
                    
                    if needs_index:
                        # Actually index the record
                        count = await index_func(record_id, db, force=True)
                        
                        if is_new:
                            type_results["new"] += 1
                            logger.debug(f"  Indexed NEW {source_type} {record_id[:8]}...")
                        else:
                            type_results["updated"] += 1
                            logger.debug(f"  Re-indexed UPDATED {source_type} {record_id[:8]}...")
                    else:
                        type_results["skipped"] += 1
                        
                except Exception as e:
                    logger.error(f"  Error indexing {source_type} {record_id}: {e}")
                    type_results["errors"] += 1
            
        except Exception as e:
            logger.error(f"  Failed to process {source_type}: {e}")
            type_results["errors"] += 1
        
        # Aggregate results
        results["checked"] += type_results["checked"]
        results["skipped_unchanged"] += type_results["skipped"]
        results["indexed_new"] += type_results["new"]
        results["indexed_updated"] += type_results["updated"]
        results["errors"] += type_results["errors"]
        results["by_type"][source_type] = type_results
        
        logger.info(f"  {source_type}: {type_results['checked']} checked, "
                   f"{type_results['new']} new, {type_results['updated']} updated, "
                   f"{type_results['skipped']} unchanged, {type_results['errors']} errors")
    
    return results


async def find_missing_embeddings():
    """
    Find records that exist in source tables but not in knowledge_chunks.
    
    Useful for detecting gaps after initial indexing.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    from app.services.database import SupabaseMultiDatabase
    
    db = SupabaseMultiDatabase()
    
    tables = {
        "transcript": "transcripts",
        "meeting": "meetings",
        "journal": "journals",
        "reflection": "reflections",
        "contact": "contacts",
        "calendar": "calendar_events",
        "application": "applications",
    }
    
    missing = {}
    
    for source_type, table_name in tables.items():
        # Get all source IDs
        source_records = db.client.table(table_name).select("id").execute()
        source_ids = set(r["id"] for r in source_records.data)
        
        # Get all indexed source IDs
        chunks = db.client.table("knowledge_chunks").select("source_id").eq(
            "source_type", source_type
        ).execute()
        indexed_ids = set(c["source_id"] for c in chunks.data)
        
        # Find missing
        missing_ids = source_ids - indexed_ids
        
        if missing_ids:
            missing[source_type] = list(missing_ids)
            logger.warning(f"{source_type}: {len(missing_ids)} records missing embeddings!")
    
    return missing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Incremental RAG indexing")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours")
    parser.add_argument("--full", action="store_true", help="Full reindex (check all)")
    parser.add_argument("--check-missing", action="store_true", help="Find missing embeddings only")
    
    args = parser.parse_args()
    
    if args.check_missing:
        logger.info("Checking for missing embeddings...")
        missing = asyncio.run(find_missing_embeddings())
        
        if missing:
            print("\n" + "=" * 60)
            print("⚠️  MISSING EMBEDDINGS FOUND:")
            for source_type, ids in missing.items():
                print(f"  {source_type}: {len(ids)} missing")
            print("=" * 60)
        else:
            print("\n✅ All records have embeddings!")
    else:
        mode = "FULL" if args.full else f"INCREMENTAL (last {args.hours}h)"
        logger.info(f"Starting {mode} indexing...")
        
        results = asyncio.run(run_incremental_indexing(
            hours=args.hours,
            full=args.full
        ))
        
        print("\n" + "=" * 60)
        print("✅ INCREMENTAL INDEXING COMPLETE!")
        print("=" * 60)
        print(f"\nRecords checked: {results['checked']}")
        print(f"Skipped (unchanged): {results['skipped_unchanged']}")
        print(f"Indexed (new): {results['indexed_new']}")
        print(f"Indexed (updated): {results['indexed_updated']}")
        print(f"Errors: {results['errors']}")
        print("\nBy type:")
        for t, r in results["by_type"].items():
            print(f"  {t}: {r['new']} new, {r['updated']} updated, {r['skipped']} unchanged")
