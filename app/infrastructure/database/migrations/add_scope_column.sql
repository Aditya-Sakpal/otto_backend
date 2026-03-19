-- Add scope column to calls and call_analyses tables
-- scope: "in" (in-scope) or "out" (out-of-scope) based on Shunya scope_classification

ALTER TABLE calls ADD COLUMN IF NOT EXISTS scope VARCHAR(10);
ALTER TABLE call_analyses ADD COLUMN IF NOT EXISTS scope VARCHAR(10);

-- Index for filtering by scope in call logs
CREATE INDEX IF NOT EXISTS ix_calls_scope ON calls (scope);
CREATE INDEX IF NOT EXISTS ix_call_analyses_scope ON call_analyses (scope);
