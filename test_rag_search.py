#!/usr/bin/env python3
"""Test RAG search functionality."""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from app.features.knowledge.service import KnowledgeService


async def test_search():
    service = KnowledgeService()
    
    queries = [
        "meetings with startup founders",
        "AI and machine learning projects",
        "family events",
        "grant applications",
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Search: '{query}'")
        print("="*60)
        
        results = await service.search(query, limit=5)
        print(f"Found {len(results)} results:\n")
        
        for i, r in enumerate(results, 1):
            content = r["content"][:100].replace("\n", " ")
            print(f"{i}. [{r['source_type']}] (score: {r['similarity']:.3f})")
            print(f"   {content}...")
            print()


if __name__ == "__main__":
    asyncio.run(test_search())
