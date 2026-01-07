"""
Setup database functions for Jarvis ecosystem.
Includes function for Claude MCP to kill stuck transactions.
"""
import psycopg2

conn = psycopg2.connect(
    host='aws-1-ap-southeast-2.pooler.supabase.com',
    port=5432,
    dbname='postgres',
    user='postgres.ojnllduebzfxqmiyinhx',
    password='7G65BBNtoAd1ewfK'
)
cur = conn.cursor()

# Create the kill_stuck_transactions function
print("Creating kill_stuck_transactions function...")
sql = """
CREATE OR REPLACE FUNCTION kill_stuck_transactions(idle_minutes INTEGER DEFAULT 5)
RETURNS TABLE(
    killed_pid INTEGER,
    username TEXT,
    query TEXT,
    idle_duration INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pg_terminate_backend(pid)::INTEGER as killed_pid,
        usename::TEXT as username,
        LEFT(query, 200)::TEXT as query,
        (now() - state_change) as idle_duration
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
    AND (now() - state_change) > (idle_minutes || ' minutes')::INTERVAL
    AND pid != pg_backend_pid();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION kill_stuck_transactions IS 
'Kills transactions that have been idle for more than idle_minutes (default 5). 
Call with: SELECT * FROM kill_stuck_transactions();
Or with custom timeout: SELECT * FROM kill_stuck_transactions(2);
Use SELECT * FROM kill_stuck_transactions(0) to kill ALL idle transactions immediately.';
"""
cur.execute(sql)
conn.commit()
print("✅ Function kill_stuck_transactions created!")

# Delete the wrong memories I created during testing
print("\nCleaning up test memories...")
cur.execute("""DELETE FROM mem0_memories WHERE payload->>'data' IN ('Enjoys cycling on weekends', 'Loves coffee')""")
deleted = cur.rowcount
conn.commit()
print(f"✅ Deleted {deleted} test memories")

# Show remaining memories
print("\n📝 Current memories in system:")
cur.execute("""SELECT payload->>'data' as memory FROM mem0_memories ORDER BY id""")
for row in cur.fetchall():
    print(f"  - {row[0]}")

conn.close()
print("\n✅ Database setup complete!")
