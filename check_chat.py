"""Quick check of chat history and memory state."""
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

print("=" * 50)
print("CHAT HISTORY STATS")
print("=" * 50)

cur.execute("SELECT COUNT(*) FROM chat_messages")
total = cur.fetchone()[0]
print(f"Total messages: {total}")

cur.execute("SELECT role, COUNT(*) FROM chat_messages GROUP BY role")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n" + "=" * 50)
print("ANTLER MENTIONS IN CHAT HISTORY")
print("=" * 50)

cur.execute("""
    SELECT role, left(content, 150), created_at 
    FROM chat_messages 
    WHERE content ILIKE '%antler%' 
    ORDER BY created_at DESC LIMIT 5
""")
rows = cur.fetchall()
print(f"Found {len(rows)} Antler mentions:")
for r in rows:
    print(f"\n[{r[0]}] ({r[2]}):\n  {r[1]}...")

print("\n" + "=" * 50)
print("MEMORY STATS")
print("=" * 50)

# List all tables to find the right one
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name LIKE '%memo%' OR table_name LIKE '%vector%'
    LIMIT 10
""")
tables = cur.fetchall()
print(f"Memory-related tables: {[t[0] for t in tables]}")

conn.close()
