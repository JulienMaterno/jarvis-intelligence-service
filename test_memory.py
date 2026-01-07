"""Quick test of memory service."""
import asyncio
from app.features.memory import get_memory_service

async def test():
    mem = get_memory_service()
    
    # Get all memories
    memories = await mem.get_all()
    print(f"Total memories: {len(memories)}")
    
    if memories:
        print("\nSample memories:")
        for m in memories[:10]:
            text = m.get("memory", str(m))
            print(f"  - {text[:100]}...")
    else:
        print("\n⚠️ Memory is EMPTY!")
        print("This is because we're using in-memory fallback (no Qdrant configured)")
        print("Every server restart clears the memories.")
    
    # Check if using fallback
    print(f"\nUsing fallback: {mem._use_fallback}")
    print(f"Qdrant URL configured: {bool(mem._memory and hasattr(mem._memory, '_vector_store'))}")

if __name__ == "__main__":
    asyncio.run(test())
