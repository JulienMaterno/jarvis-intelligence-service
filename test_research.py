"""
Test script for Research Tools (LinkedIn + Brave Search)

Run with:
  # Set your API keys from Secret Manager or environment
  # $env:BRIGHTDATA_API_KEY="your-key-here"
  # $env:BRAVE_API_KEY="your-key-here"
  python test_research.py
"""

import asyncio
import os
import json

# Check for required environment variables
if not os.getenv("BRIGHTDATA_API_KEY"):
    print("WARNING: BRIGHTDATA_API_KEY not set. Set via: $env:BRIGHTDATA_API_KEY='your-key'")
if not os.getenv("BRAVE_API_KEY"):
    print("WARNING: BRAVE_API_KEY not set. Set via: $env:BRAVE_API_KEY='your-key'")

from app.features.research import get_research_service


async def test_brave_search():
    """Test Brave Search API."""
    print("\n" + "="*60)
    print("TEST: Brave Web Search")
    print("="*60)
    
    service = get_research_service()
    
    # Check if configured
    print(f"Brave configured: {service.web_search.is_configured}")
    
    # Test web search
    print("\nSearching for 'AI trends 2026'...")
    result = await service.web_search.execute("search", {
        "query": "AI trends 2026",
        "num_results": 5
    })
    
    if result.is_success:
        print(f"✅ Success! Found {len(result.data.get('results', []))} results")
        for r in result.data.get("results", [])[:3]:
            print(f"  - {r.get('title')[:60]}...")
            print(f"    {r.get('url')}")
    else:
        print(f"❌ Error: {result.error}")
    
    return result.is_success


async def test_linkedin_search():
    """Test LinkedIn Search via Bright Data."""
    print("\n" + "="*60)
    print("TEST: LinkedIn Profile Search by Name (Bright Data)")
    print("="*60)
    
    service = get_research_service()
    
    # Check if configured
    print(f"LinkedIn configured: {service.linkedin.is_configured}")
    
    # Test profile search by name
    print("\nSearching for 'Bill Gates'...")
    result = await service.linkedin.execute("search_profiles", {
        "first_name": "Bill",
        "last_name": "Gates"
    })
    
    if result.is_success:
        data = result.data
        # Check if it's an async job or immediate results
        if isinstance(data, dict) and data.get("snapshot_id"):
            print(f"⏳ Async job started: {data.get('snapshot_id')}")
            return True
        elif isinstance(data, list):
            print(f"✅ Success! Found {len(data)} profiles")
            for p in data[:3]:
                print(f"  - {p.get('name', p.get('full_name', 'Unknown'))}")
                print(f"    {p.get('position', p.get('headline', ''))}")
        else:
            print(f"✅ Got response: {json.dumps(data, indent=2)[:500]}")
    else:
        print(f"❌ Error: {result.error}")
    
    return result.is_success


async def test_linkedin_profile():
    """Test LinkedIn Profile Lookup."""
    print("\n" + "="*60)
    print("TEST: LinkedIn Profile by URL (Bright Data)")
    print("="*60)
    
    service = get_research_service()
    
    # Test profile lookup - using a well-known profile
    print("\nLooking up Satya Nadella's profile...")
    result = await service.linkedin.execute("get_profile", {
        "url": "https://www.linkedin.com/in/satyanadella"
    })
    
    if result.is_success:
        data = result.data
        if isinstance(data, list) and len(data) > 0:
            profile = data[0]
            print(f"✅ Found profile:")
            print(f"  Name: {profile.get('name', profile.get('full_name', 'N/A'))}")
            print(f"  Title: {profile.get('headline', profile.get('title', 'N/A'))}")
            print(f"  Company: {profile.get('company', 'N/A')}")
        else:
            print(f"✅ Got response: {json.dumps(data, indent=2)[:500]}")
    else:
        print(f"❌ Error: {result.error}")
    
    return result.is_success


async def test_research_status():
    """Test research service status."""
    print("\n" + "="*60)
    print("TEST: Research Service Status")
    print("="*60)
    
    service = get_research_service()
    status = service.get_status()
    
    print(json.dumps(status, indent=2))
    return True


async def main():
    """Run all tests."""
    print("🧪 Research Tools Test Suite")
    print("="*60)
    
    results = {}
    
    # Test status first
    results["status"] = await test_research_status()
    
    # Test Brave Search (cheap, fast)
    results["brave"] = await test_brave_search()
    
    # Test LinkedIn (costs money, be careful)
    results["linkedin_search"] = await test_linkedin_search()
    results["linkedin_profile"] = await test_linkedin_profile()
    
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")
    
    # Cleanup
    service = get_research_service()
    await service.close()


if __name__ == "__main__":
    asyncio.run(main())
