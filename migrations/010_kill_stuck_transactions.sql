-- Kill Stuck Transactions Function
-- Created: 2026-01-07
-- 
-- This function allows Claude (via MCP) to kill stuck transactions that are
-- blocking other queries. It only kills idle-in-transaction connections,
-- NOT active queries or legitimate waiting transactions.
--
-- Usage from Claude MCP:
--   SELECT * FROM kill_stuck_transactions();
--   SELECT * FROM kill_stuck_transactions(interval '30 seconds');

-- Function to kill transactions that have been idle for too long
CREATE OR REPLACE FUNCTION kill_stuck_transactions(
    idle_threshold interval DEFAULT interval '60 seconds'
)
RETURNS TABLE (
    killed_pid int,
    username text,
    state text,
    idle_duration interval,
    last_query text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pg_stat_activity.pid::int,
        pg_stat_activity.usename::text,
        pg_stat_activity.state::text,
        (now() - pg_stat_activity.state_change)::interval,
        LEFT(pg_stat_activity.query, 200)::text
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
      AND (now() - state_change) > idle_threshold
      AND usename LIKE 'postgres%'  -- Only kill postgres user connections (pooler)
      AND pid != pg_backend_pid()   -- Don't kill self
      AND pg_terminate_backend(pid);  -- Actually kill it
END;
$$ LANGUAGE plpgsql;

-- Simpler function - just kill ALL idle-in-transaction connections immediately
-- Use this when you want to clear ALL stuck transactions right now
CREATE OR REPLACE FUNCTION kill_all_stuck_transactions()
RETURNS TABLE (
    killed_pid int,
    username text,
    idle_duration interval,
    last_query text
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pg_stat_activity.pid::int,
        pg_stat_activity.usename::text,
        (now() - pg_stat_activity.state_change)::interval,
        LEFT(pg_stat_activity.query, 200)::text
    FROM pg_stat_activity
    WHERE state = 'idle in transaction'
      AND usename LIKE 'postgres%'
      AND pid != pg_backend_pid()
      AND pg_terminate_backend(pid);
END;
$$ LANGUAGE plpgsql;

-- View to see current stuck transactions (without killing)
-- Use this to check BEFORE killing
CREATE OR REPLACE VIEW stuck_transactions AS
SELECT 
    pid,
    usename,
    state,
    (now() - state_change) as idle_duration,
    LEFT(query, 200) as last_query,
    client_addr,
    backend_start
FROM pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY state_change;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION kill_stuck_transactions TO postgres;
GRANT EXECUTE ON FUNCTION kill_all_stuck_transactions TO postgres;
GRANT SELECT ON stuck_transactions TO postgres;

COMMENT ON FUNCTION kill_stuck_transactions IS 'Kill idle-in-transaction connections older than threshold (default 60 seconds). Use when MCP queries get stuck.';
COMMENT ON FUNCTION kill_all_stuck_transactions IS 'Kill ALL idle-in-transaction connections immediately. Use when everything is blocked.';
COMMENT ON VIEW stuck_transactions IS 'View current stuck transactions without killing them.';
