import psycopg

conn = psycopg.connect('host=aws-1-ap-southeast-2.pooler.supabase.com port=5432 dbname=postgres user=postgres.ojnllduebzfxqmiyinhx password=7G65BBNtoAd1ewfK sslmode=require')
cur = conn.cursor()

# Check table schema
cur.execute("""
    SELECT column_name, data_type FROM information_schema.columns 
    WHERE table_name = 'mem0_memories'
""")
print('mem0_memories schema:')
for row in cur.fetchall():
    print(f'  - {row[0]}: {row[1]}')

# Check contents
cur.execute('SELECT COUNT(*) FROM mem0_memories')
print(f'\nMemory count: {cur.fetchone()[0]}')
