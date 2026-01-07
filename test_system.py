"""
Comprehensive test of the Jarvis system end-to-end.
"""
import httpx
import time
import json
import asyncio

BASE_URL = "https://jarvis-intelligence-service-qkz4et4n4q-as.a.run.app"
TELEGRAM_URL = "https://jarvis-telegram-bot-qkz4et4n4q-as.a.run.app"

def test_endpoint(name: str, method: str, url: str, body: dict = None, expected_key: str = None):
    """Test an endpoint and report results."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        if method == "GET":
            response = httpx.get(url, timeout=120.0)
        else:
            response = httpx.post(url, json=body, timeout=120.0)
        
        elapsed = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS ({elapsed:.1f}s)")
            if expected_key and expected_key in data:
                value = data[expected_key]
                if isinstance(value, str) and len(value) > 100:
                    print(f"   {expected_key}: {value[:100]}...")
                else:
                    print(f"   {expected_key}: {value}")
            return True, elapsed
        else:
            print(f"❌ FAILED: {response.status_code}")
            print(f"   {response.text[:200]}")
            return False, elapsed
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ ERROR ({elapsed:.1f}s): {e}")
        return False, elapsed

def main():
    print("\n" + "="*60)
    print("JARVIS SYSTEM COMPREHENSIVE TEST")
    print("="*60)
    
    results = []
    
    # 1. Health checks
    results.append(("Intelligence Health", *test_endpoint(
        "Intelligence Service Health",
        "GET",
        f"{BASE_URL}/health",
        expected_key="status"
    )))
    
    results.append(("Telegram Health", *test_endpoint(
        "Telegram Bot Health",
        "GET",
        f"{TELEGRAM_URL}/health",
        expected_key="status"
    )))
    
    # 2. Memory system
    results.append(("Memory Stats", *test_endpoint(
        "Memory Stats",
        "GET",
        f"{BASE_URL}/api/v1/memory/stats",
        expected_key="total_memories"
    )))
    
    results.append(("Memory Search", *test_endpoint(
        "Memory Search: 'Antler'",
        "POST",
        f"{BASE_URL}/api/v1/memory/search",
        body={"query": "Antler application deadline", "limit": 3},
        expected_key="count"
    )))
    
    # 3. Chat system
    results.append(("Chat Simple", *test_endpoint(
        "Chat: Simple greeting",
        "POST",
        f"{BASE_URL}/api/v1/chat",
        body={"message": "Hello!", "user_id": "test_user"},
        expected_key="response"
    )))
    
    results.append(("Chat Memory", *test_endpoint(
        "Chat: Memory query",
        "POST",
        f"{BASE_URL}/api/v1/chat",
        body={"message": "What do you remember about me?", "user_id": "test_user"},
        expected_key="response"
    )))
    
    # 4. Core features
    results.append(("Contact Search", *test_endpoint(
        "Contact Search",
        "GET",
        f"{BASE_URL}/api/v1/contacts/search?q=test&limit=3",
        expected_key="contacts"
    )))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results if r[1])
    total = len(results)
    avg_time = sum(r[2] for r in results) / len(results)
    
    print(f"\n✅ Passed: {passed}/{total}")
    print(f"⏱️  Avg response time: {avg_time:.1f}s")
    
    print("\nDetailed results:")
    for name, success, elapsed in results:
        status = "✅" if success else "❌"
        print(f"  {status} {name}: {elapsed:.1f}s")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")

if __name__ == "__main__":
    main()
