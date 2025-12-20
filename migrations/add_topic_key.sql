-- Add topic_key column to reflections table for smart topic merging
-- Run this in Supabase SQL Editor

ALTER TABLE reflections 
ADD COLUMN IF NOT EXISTS topic_key TEXT;

-- Create index for faster topic lookups
CREATE INDEX IF NOT EXISTS idx_reflections_topic_key 
ON reflections(topic_key) 
WHERE topic_key IS NOT NULL AND deleted_at IS NULL;

-- Add comment explaining the column
COMMENT ON COLUMN reflections.topic_key IS 'Lowercase hyphenated identifier for recurring topics (e.g. project-jarvis, explore-out-loud-newsletter). Used to append new content to existing reflections.';
