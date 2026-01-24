-- Migration 027: Fix trait processing trigger that references non-existent user_id column
-- The trigger_queue_reflection_for_traits trigger references NEW.user_id but
-- reflections and journals tables don't have this column, causing 400 errors on updates.

-- Drop the problematic triggers
DROP TRIGGER IF EXISTS trigger_queue_reflection_for_traits ON reflections;
DROP TRIGGER IF EXISTS trigger_queue_reflection_for_traits ON journals;

-- Create a fixed version of the function that uses a default user_id
-- or skips the insert if user_id is required but not available
CREATE OR REPLACE FUNCTION auto_queue_for_trait_processing()
RETURNS TRIGGER AS $$
DECLARE
    default_user_id text;
BEGIN
    -- Only queue if not deleted
    IF NEW.deleted_at IS NULL THEN
        -- Get a default user_id from users table (single-user system)
        SELECT id INTO default_user_id FROM users LIMIT 1;

        -- Only insert if we have a valid user_id
        IF default_user_id IS NOT NULL THEN
            INSERT INTO trait_processing_queue (user_id, source_id, source_type)
            VALUES (
                default_user_id,
                NEW.id,
                CASE
                    WHEN TG_TABLE_NAME = 'reflections' THEN 'reflection'
                    WHEN TG_TABLE_NAME = 'journals' THEN 'journal'
                END
            )
            ON CONFLICT (source_id, source_type) WHERE status IN ('pending', 'processing')
            DO NOTHING;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Re-create the triggers with the fixed function
CREATE TRIGGER trigger_queue_reflection_for_traits
    AFTER INSERT OR UPDATE ON reflections
    FOR EACH ROW
    EXECUTE FUNCTION auto_queue_for_trait_processing();

CREATE TRIGGER trigger_queue_journal_for_traits
    AFTER INSERT OR UPDATE ON journals
    FOR EACH ROW
    EXECUTE FUNCTION auto_queue_for_trait_processing();
