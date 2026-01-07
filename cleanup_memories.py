"""Script to find and delete wrong memories."""
import psycopg2

conn = psycopg2.connect(
    user='postgres.ojnllduebzfxqmiyinhx', 
    password='7G65BBNtoAd1ewfK', 
    host='aws-1-ap-southeast-2.pooler.supabase.com', 
    port=5432, 
    dbname='postgres', 
    sslmode='require'
)
cur = conn.cursor()

# First, let's see all memories
print("All memories in database:")
cur.execute("SELECT id, payload->>'data' as memory FROM mem0_memories ORDER BY id LIMIT 100")
rows = cur.fetchall()
print(f"Total: {len(rows)} memories\n")

for i, r in enumerate(rows):
    mem = r[1][:80] + '...' if r[1] and len(r[1]) > 80 else r[1]
    print(f"{i+1}. [{r[0][:8]}] {mem}")

cur.close()
conn.close()
