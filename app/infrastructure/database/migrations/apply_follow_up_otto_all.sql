-- ============================================================================
-- One-shot: create follow_up_otto + nudge columns (run against your Postgres DB)
-- ============================================================================
-- If you see: relation "follow_up_otto" does not exist
-- Run this file once (psql, pgAdmin, Neon console, etc.) on the SAME database
-- as DATABASE_URL in .env
-- ============================================================================

-- Enable UUID extension if not already enabled
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        CREATE EXTENSION "uuid-ossp";
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS follow_up_otto (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    message_content TEXT NOT NULL,
    action_type VARCHAR(32) NOT NULL,

    external_message_id VARCHAR(256),
    pending_action_id UUID REFERENCES pending_actions(id) ON DELETE SET NULL,

    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,

    status VARCHAR(32) NOT NULL DEFAULT 'proposed',
    error_message TEXT,

    ai_reasoning JSONB,
    queue_type VARCHAR(32) NOT NULL,
    attempt_number INTEGER NOT NULL,

    assigned_rep_id UUID REFERENCES users(id) ON DELETE SET NULL,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_follow_up_otto_lead_id ON follow_up_otto(lead_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_company_id ON follow_up_otto(company_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_status ON follow_up_otto(status);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_external_message_id ON follow_up_otto(external_message_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_pending_action_id ON follow_up_otto(pending_action_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_assigned_rep_id ON follow_up_otto(assigned_rep_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_lead_status ON follow_up_otto(lead_id, status);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_company_lead ON follow_up_otto(company_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_follow_up_otto_scheduled_status ON follow_up_otto(scheduled_at, status);

COMMENT ON TABLE follow_up_otto IS 'GoMotto follow-up messages for the Follow Up tab: sent/scheduled, AI reasoning';
COMMENT ON COLUMN follow_up_otto.action_type IS 'sms_to_lead | nudge_sales_rep';
COMMENT ON COLUMN follow_up_otto.ai_reasoning IS 'JSON array of "Why GoMotto sent this" reason bullets';
COMMENT ON COLUMN follow_up_otto.queue_type IS 'qualified_unbooked | appointment_ran';

-- Nudge section columns (safe if re-run)
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS opening_line TEXT;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS objections JSONB;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS key_talking_points JSONB;
ALTER TABLE follow_up_otto ADD COLUMN IF NOT EXISTS close_approach TEXT;

COMMENT ON COLUMN follow_up_otto.opening_line IS 'Rep nudge: opening line for the follow-up call';
COMMENT ON COLUMN follow_up_otto.objections IS 'Rep nudge: JSON array of {objection, suggested_response}';
COMMENT ON COLUMN follow_up_otto.key_talking_points IS 'Rep nudge: JSON array of talking point strings';
COMMENT ON COLUMN follow_up_otto.close_approach IS 'Rep nudge: suggested close for the call';
