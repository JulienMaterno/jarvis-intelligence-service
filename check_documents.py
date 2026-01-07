"""Check recent documents and CV upload status."""
import psycopg2
import json

conn = psycopg2.connect(
    user='postgres.ojnllduebzfxqmiyinhx',
    password='7G65BBNtoAd1ewfK',
    host='aws-1-ap-southeast-2.pooler.supabase.com',
    port=5432,
    dbname='postgres',
    sslmode='require'
)
cur = conn.cursor()

print("=" * 60)
print("DOCUMENTS TABLE SCHEMA")
print("=" * 60)

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'documents'
""")
cols = cur.fetchall()
if cols:
    for c in cols:
        print(f"  {c[0]}: {c[1]}")
else:
    print("documents table does not exist!")

print("\n" + "=" * 60)
print("RECENT DOCUMENTS")
print("=" * 60)

try:
    cur.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 3")
    rows = cur.fetchall()
    if rows:
        # Get column names
        col_names = [desc[0] for desc in cur.description]
        for row in rows:
            print("\nDocument:")
            for i, val in enumerate(row):
                if col_names[i] == 'content':
                    print(f"  {col_names[i]}: {len(str(val)) if val else 0} chars")
                else:
                    print(f"  {col_names[i]}: {val}")
    else:
        print("No documents found")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("MEMORIES FROM DOCUMENTS")
print("=" * 60)

# Check if any memories came from documents
cur.execute("""
    SELECT id, payload->>'data' as memory, payload->>'source' as source
    FROM mem0_memories 
    WHERE payload->>'source' ILIKE '%document%' OR payload->>'source' ILIKE '%cv%'
    LIMIT 10
""")
doc_memories = cur.fetchall()
if doc_memories:
    for m in doc_memories:
        print(f"  - {m[1][:80]}... (source: {m[2]})")
else:
    print("No memories from documents found")

conn.close()
