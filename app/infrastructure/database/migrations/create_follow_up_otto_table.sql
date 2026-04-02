-- ============================================================================
-- Migration: Create follow_up_otto Table
-- ============================================================================
-- Stores GoMotto/contextual follow-up messages for the Follow Up tab in the
-- frontend: sent and scheduled messages, AI reasoning, and engagement status.
-- ============================================================================

-- Enable UUID extension if not already enabled
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        CREATE EXTENSION "uuid-ossp";
    END IF;
END $$;

-- ============================================================================
-- TABLE: follow_up_otto
-- ============================================================================
CREATE TABLE IF NOT EXISTS follow_up_otto (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Message
    message_content TEXT NOT NULL,
    action_type VARCHAR(32) NOT NULL,       -- 'sms_to_lead' | 'nudge_sales_rep'

    -- External IDs (Twilio SID, etc.)
    external_message_id VARCHAR(256),
    pending_action_id UUID REFERENCES pending_actions(id) ON DELETE SET NULL,

    -- Timing
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE,

    -- Status: proposed | pending | scheduled | sent | failed | overdue | cancelled | paused | opted_out | dormant
    status VARCHAR(32) NOT NULL DEFAULT 'proposed',
    error_message TEXT,

    -- "Why GoMotto sent this" — list of reason strings (JSON array)
    ai_reasoning JSONB,
    queue_type VARCHAR(32) NOT NULL,       -- qualified_unbooked | appointment_ran
    attempt_number INTEGER NOT NULL,

    -- Recipient (for rep nudges)
    assigned_rep_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Audit
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for common queries
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
