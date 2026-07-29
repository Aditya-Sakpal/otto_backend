-- ============================================================================
-- Migration: Smart Nudges + Coaching Auto-Cycling
-- ============================================================================
-- Creates smart_nudges and smart_nudge_reads tables for AI-driven coaching
-- notifications. Also adds cycle tracking columns to coaching_sessions for
-- 7-day auto-restarting coaching cycles.
-- ============================================================================

-- Enable UUID extension if not already enabled
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        CREATE EXTENSION "uuid-ossp";
    END IF;
END $$;

-- ============================================================================
-- TABLE: smart_nudges
-- ============================================================================
CREATE TABLE IF NOT EXISTS smart_nudges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,

    -- Who the nudge is about
    rep_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rep_name VARCHAR(255),

    -- Nudge content
    nudge_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,

    -- Metric context
    metric_name VARCHAR(100),
    previous_value DOUBLE PRECISION,
    current_value DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    window_description VARCHAR(100),

    -- Source references
    source_call_ids UUID[] DEFAULT '{}',
    source_session_id UUID REFERENCES coaching_sessions(id) ON DELETE SET NULL,
    extra_data JSON,

    -- Dedup fingerprint
    fingerprint VARCHAR(64) NOT NULL,

    -- Lifecycle
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for smart_nudges
CREATE INDEX IF NOT EXISTS idx_smart_nudges_company_created ON smart_nudges(company_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_smart_nudges_rep ON smart_nudges(company_id, rep_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_smart_nudges_fingerprint ON smart_nudges(fingerprint, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_smart_nudges_type ON smart_nudges(nudge_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_smart_nudges_expires ON smart_nudges(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_smart_nudges_priority ON smart_nudges(company_id, priority, created_at DESC);

COMMENT ON TABLE smart_nudges IS 'AI-generated coaching nudges for managers. Each nudge is about a specific rep performance change.';
COMMENT ON COLUMN smart_nudges.nudge_type IS 'Type: metric_improvement, metric_decline, critical_decline, recurring_issue, objection_weakness, objection_improvement, coaching_target_met, coaching_target_missed, new_strength, cycle_summary';
COMMENT ON COLUMN smart_nudges.fingerprint IS 'SHA256 hash for deduplication: rep_user_id:nudge_type:metric_name:window';


-- ============================================================================
-- TABLE: smart_nudge_reads (per-user read tracking)
-- ============================================================================
CREATE TABLE IF NOT EXISTS smart_nudge_reads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nudge_id UUID NOT NULL REFERENCES smart_nudges(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    status VARCHAR(20) NOT NULL DEFAULT 'read',
    read_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dismissed_at TIMESTAMP WITH TIME ZONE,

    UNIQUE(nudge_id, user_id)
);

-- Indexes for smart_nudge_reads
CREATE INDEX IF NOT EXISTS idx_smart_nudge_reads_user ON smart_nudge_reads(user_id, read_at DESC);
CREATE INDEX IF NOT EXISTS idx_smart_nudge_reads_nudge ON smart_nudge_reads(nudge_id);

COMMENT ON TABLE smart_nudge_reads IS 'Tracks which users have read/dismissed each nudge. Absence of a row means unread.';


-- ============================================================================
-- ALTER: coaching_sessions - add cycle tracking columns
-- ============================================================================
DO $$
BEGIN
    -- Add cycle_number column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'coaching_sessions' AND column_name = 'cycle_number'
    ) THEN
        ALTER TABLE coaching_sessions ADD COLUMN cycle_number INTEGER NOT NULL DEFAULT 1;
    END IF;

    -- Add parent_session_id column (links to original session in a cycle chain)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'coaching_sessions' AND column_name = 'parent_session_id'
    ) THEN
        ALTER TABLE coaching_sessions ADD COLUMN parent_session_id UUID REFERENCES coaching_sessions(id) ON DELETE SET NULL;
    END IF;

    -- Add auto_created flag
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'coaching_sessions' AND column_name = 'auto_created'
    ) THEN
        ALTER TABLE coaching_sessions ADD COLUMN auto_created BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

-- Index for cycle chain lookups
CREATE INDEX IF NOT EXISTS idx_coaching_sessions_parent ON coaching_sessions(parent_session_id);
