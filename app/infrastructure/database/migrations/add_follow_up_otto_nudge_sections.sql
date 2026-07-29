-- ============================================================================
-- Migration: Add nudge section columns to follow_up_otto
-- ============================================================================
-- For action_type = 'nudge_sales_rep', store structured sections separately:
-- opening_line, objections (JSONB), key_talking_points (JSONB), close_approach.
-- ============================================================================

ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS opening_line TEXT;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS objections JSONB;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS key_talking_points JSONB;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS close_approach TEXT;

COMMENT ON COLUMN follow_up_otto.opening_line IS 'Rep nudge: opening line for the follow-up call';
COMMENT ON COLUMN follow_up_otto.objections IS 'Rep nudge: JSON array of {objection, suggested_response}';
COMMENT ON COLUMN follow_up_otto.key_talking_points IS 'Rep nudge: JSON array of talking point strings';
COMMENT ON COLUMN follow_up_otto.close_approach IS 'Rep nudge: suggested close for the call';
