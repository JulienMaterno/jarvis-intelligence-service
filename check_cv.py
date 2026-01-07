"""Check CV content."""
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
cur.execute("SELECT content FROM documents WHERE id = '9663b1e3-3202-43dd-a7d9-5b06cbc45eda'")
content = cur.fetchone()[0]
print("CV Content:")
print("-" * 40)
print(content)
print("-" * 40)
print(f"Length: {len(content)} chars")
conn.close()
