-- Migration: Add call log fields (answered_by_display, lead_source), lead_status_changes audit table, pending_actions.assigned_by_id
-- Purpose: Support "who picked up" fallback, lead source in call logs, status change audit (admin), exec-assigned action items

-- ============================================================================
-- 1. CALLS: answered_by_display, lead_source (for call logs and metrics)
-- ============================================================================
ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS answered_by_display VARCHAR(255) NULL,
  ADD COLUMN IF NOT EXISTS lead_source VARCHAR(255) NULL;

COMMENT ON COLUMN calls.answered_by_display IS 'Display name/email of who answered (from VoIP/CRM); fallback when not an Otto user';
COMMENT ON COLUMN calls.lead_source IS 'Lead source from CRM/VoIP (e.g. Google, LSA, Yelp, Meta ad)';

CREATE INDEX IF NOT EXISTS idx_calls_lead_source ON calls(lead_source);

-- ============================================================================
-- 2. LEAD_STATUS_CHANGES: Audit log for lead status changes (admin-only)
-- ============================================================================
CREATE TABLE IF NOT EXISTS lead_status_changes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  changed_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  old_status VARCHAR(100) NULL,
  new_status VARCHAR(100) NOT NULL,
  old_deal_status VARCHAR(100) NULL,
  new_deal_status VARCHAR(100) NULL,
  reason VARCHAR(500) NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lead_status_changes_lead_id ON lead_status_changes(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_status_changes_company_id ON lead_status_changes(company_id);
CREATE INDEX IF NOT EXISTS idx_lead_status_changes_changed_by ON lead_status_changes(changed_by_user_id);
CREATE INDEX IF NOT EXISTS idx_lead_status_changes_created_at ON lead_status_changes(created_at);

COMMENT ON TABLE lead_status_changes IS 'Audit log for lead status/deal_status changes (e.g. admin manually qualified/unqualified)';

-- ============================================================================
-- 3. PENDING_ACTIONS: assigned_by_id (who assigned the action, e.g. exec)
-- ============================================================================
ALTER TABLE pending_actions
  ADD COLUMN IF NOT EXISTS assigned_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_pending_actions_assigned_by_id ON pending_actions(assigned_by_id);

COMMENT ON COLUMN pending_actions.assigned_by_id IS 'User who assigned this action (e.g. exec tagging a CSR)';
