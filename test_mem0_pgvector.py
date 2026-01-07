"""
Test Mem0 pgvector connection locally.
Run this to debug the Supabase pooler connection.
"""
import os
from dotenv import load_dotenv

# Load .env if it exists
load_dotenv()

# Set test environment variables (override if needed)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ojnllduebzfxqmiyinhx.supabase.co")
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "7G65BBNtoAd1ewfK")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

print("=" * 60)
print("Testing Mem0 pgvector connection")
print("=" * 60)

# Step 1: Test raw psycopg2 connection first
print("\n1. Testing raw psycopg2 connection...")
try:
    import psycopg2
    
    # Connection parameters for Supabase Session Pooler
    conn_params = {
        "user": "postgres.ojnllduebzfxqmiyinhx",
        "password": SUPABASE_DB_PASSWORD,
        "host": "aws-1-ap-southeast-2.pooler.supabase.com",
        "port": 5432,
        "dbname": "postgres",
        "sslmode": "require",
    }
    
    print(f"   User: {conn_params['user']}")
    print(f"   Host: {conn_params['host']}:{conn_params['port']}")
    print(f"   Database: {conn_params['dbname']}")
    print(f"   Password length: {len(SUPABASE_DB_PASSWORD)}")
    
    conn = psycopg2.connect(**conn_params)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"   ✅ Connected! PostgreSQL version: {version[0][:50]}...")
    
    # Check if pgvector extension is available
    cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
    pgvector = cur.fetchone()
    if pgvector:
        print(f"   ✅ pgvector extension: {pgvector[0]} v{pgvector[1]}")
    else:
        print("   ❌ pgvector extension not installed!")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    print("\n   If password auth fails, check:")
    print("   - Password is correct (reset in Supabase Dashboard if needed)")
    print("   - Using Session Pooler format (postgres.{project_ref})")
    raise

# Step 2: Test Mem0 initialization
print("\n2. Testing Mem0 initialization...")
try:
    from mem0 import Memory
    
    config = {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": "claude-3-5-haiku-20241022",
                "api_key": ANTHROPIC_API_KEY,
            }
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": OPENAI_API_KEY,
            }
        },
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "user": "postgres.ojnllduebzfxqmiyinhx",
                "password": SUPABASE_DB_PASSWORD,
                "host": "aws-1-ap-southeast-2.pooler.supabase.com",
                "port": 5432,
                "dbname": "postgres",
                "collection_name": "mem0_memories",
                "embedding_model_dims": 1536,
            }
        },
    }
    
    print("   Initializing Mem0...")
    memory = Memory.from_config(config)
    print("   ✅ Mem0 initialized successfully!")
    
except Exception as e:
    print(f"   ❌ Mem0 initialization failed: {e}")
    import traceback
    traceback.print_exc()
    raise

# Step 3: Test adding a memory
print("\n3. Testing memory operations...")
try:
    # Add a test memory
    result = memory.add(
        "Aaron is the creator of Jarvis, a personal AI assistant ecosystem.",
        user_id="test_user",
        metadata={"type": "fact", "source": "test"}
    )
    print(f"   ✅ Memory added: {result}")
    
    # Search for the memory
    results = memory.search("Who created Jarvis?", user_id="test_user")
    print(f"   ✅ Search results: {type(results)} - {results}")
    
    # Get all memories
    all_memories = memory.get_all(user_id="test_user")
    print(f"   ✅ Total memories for test_user: {type(all_memories)} - {all_memories}")
    
except Exception as e:
    print(f"   ❌ Memory operations failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
