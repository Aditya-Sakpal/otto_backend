-- ============================================================================
-- Migration: Create pending_actions Table
-- ============================================================================
-- Creates the pending_actions table for tracking follow-up tasks and actions
-- extracted from calls (e.g. via Shunya). Supports company, lead, call,
-- appointment, and owner associations.
-- ============================================================================

-- Enable UUID extension if not already enabled
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        CREATE EXTENSION "uuid-ossp";
    END IF;
END $$;

-- ============================================================================
-- TABLE: pending_actions
-- ============================================================================
CREATE TABLE IF NOT EXISTS pending_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    call_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,

    -- Action content
    action_type VARCHAR NOT NULL,
    raw_text TEXT,

    -- Status and scheduling
    status VARCHAR NOT NULL DEFAULT 'pending',
    due_at TIMESTAMP WITH TIME ZONE,
    priority INTEGER,
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Source (e.g. shunya) and extensibility
    source VARCHAR NOT NULL DEFAULT 'shunya',
    extra_metadata JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Single-column indexes
CREATE INDEX IF NOT EXISTS idx_pending_actions_company_id ON pending_actions(company_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_lead_id ON pending_actions(lead_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_call_id ON pending_actions(call_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_appointment_id ON pending_actions(appointment_id);
CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_due_at ON pending_actions(due_at);
CREATE INDEX IF NOT EXISTS idx_pending_actions_owner_id ON pending_actions(owner_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_pending_actions_company_status ON pending_actions(company_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_lead_status ON pending_actions(lead_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_owner_status ON pending_actions(owner_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_urgency ON pending_actions(due_at, priority);

-- Comments
COMMENT ON TABLE pending_actions IS 'Follow-up tasks and actions extracted from calls (e.g. Shunya)';
COMMENT ON COLUMN pending_actions.action_type IS 'Type of action: callback, follow_up, schedule_appointment, etc.';
COMMENT ON COLUMN pending_actions.source IS 'Origin of the action: shunya, manual, etc.';
