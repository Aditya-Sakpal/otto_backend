-- ============================================================================
-- Migration: Add Complete Call Summary Fields to call_analyses Table
-- ============================================================================
-- This migration adds all fields from Shunya's Call Summary API to the
-- call_analyses table to store complete analysis data including:
-- - Summary section: action_items, next_steps, pending_actions, confidence_score
-- - Compliance section: issues, positive_behaviors, confidence, compliance_rate
-- - Objections section: total_count
-- - Qualification section: BANT scores, appointment details, customer details,
--   service details, follow-up information
-- ============================================================================

-- ============================================================================
-- 1. SUMMARY SECTION FIELDS
-- ============================================================================

-- Action items from summary
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS action_items TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.action_items IS 'Action items extracted from call summary';

-- Next steps from summary
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS next_steps TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.next_steps IS 'Next steps identified in call summary';

-- Pending actions (detailed objects with type, owner, due_at, etc.)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS pending_actions JSONB DEFAULT '[]';

COMMENT ON COLUMN call_analyses.pending_actions IS 'Pending actions with details: type, owner, due_at, raw_text, confidence, contact_method';

-- Summary confidence score
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS summary_confidence_score FLOAT;

COMMENT ON COLUMN call_analyses.summary_confidence_score IS 'Confidence score for the summary (0.0 to 1.0)';

-- ============================================================================
-- 2. COMPLIANCE SECTION FIELDS
-- ============================================================================

-- SOP compliance issues
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS sop_compliance_issues TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.sop_compliance_issues IS 'List of SOP compliance issues identified';

-- SOP compliance positive behaviors
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS sop_compliance_positive_behaviors TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.sop_compliance_positive_behaviors IS 'List of positive behaviors observed during call';

-- SOP compliance confidence
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS sop_compliance_confidence FLOAT;

COMMENT ON COLUMN call_analyses.sop_compliance_confidence IS 'Confidence score for SOP compliance evaluation (0.0 to 1.0)';

-- SOP compliance rate (may be same as score, but keeping separate for clarity)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS sop_compliance_rate FLOAT;

COMMENT ON COLUMN call_analyses.sop_compliance_rate IS 'SOP compliance rate (0.0 to 1.0)';

-- SOP stages total count
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS sop_stages_total INTEGER;

COMMENT ON COLUMN call_analyses.sop_stages_total IS 'Total number of SOP stages evaluated';

-- ============================================================================
-- 3. OBJECTIONS SECTION FIELDS
-- ============================================================================

-- Total objections count
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS objections_total_count INTEGER DEFAULT 0;

COMMENT ON COLUMN call_analyses.objections_total_count IS 'Total number of objections detected';

-- ============================================================================
-- 4. QUALIFICATION SECTION FIELDS
-- ============================================================================

-- BANT Scores (individual breakdown)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS bant_need_score FLOAT;

COMMENT ON COLUMN call_analyses.bant_need_score IS 'BANT Need score (0.0 to 1.0)';

ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS bant_budget_score FLOAT;

COMMENT ON COLUMN call_analyses.bant_budget_score IS 'BANT Budget score (0.0 to 1.0)';

ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS bant_timeline_score FLOAT;

COMMENT ON COLUMN call_analyses.bant_timeline_score IS 'BANT Timeline score (0.0 to 1.0)';

ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS bant_authority_score FLOAT;

COMMENT ON COLUMN call_analyses.bant_authority_score IS 'BANT Authority score (0.0 to 1.0)';

-- Overall qualification score
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS qualification_overall_score FLOAT;

COMMENT ON COLUMN call_analyses.qualification_overall_score IS 'Overall qualification score (0.0 to 1.0)';

-- Call outcome category
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS call_outcome_category VARCHAR(100);

COMMENT ON COLUMN call_analyses.call_outcome_category IS 'Call outcome category (e.g., qualified_but_unbooked, qualified_and_booked)';

-- ============================================================================
-- 5. APPOINTMENT FIELDS
-- ============================================================================

-- Appointment confirmed
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_confirmed BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN call_analyses.appointment_confirmed IS 'Whether appointment was confirmed during call';

-- Appointment date/time
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_date TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN call_analyses.appointment_date IS 'Scheduled appointment date and time';

-- Appointment type
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(50);

COMMENT ON COLUMN call_analyses.appointment_type IS 'Appointment type (e.g., in-person, virtual, phone)';

-- Appointment timezone
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_timezone VARCHAR(50);

COMMENT ON COLUMN call_analyses.appointment_timezone IS 'Timezone for appointment (e.g., UTC, America/New_York)';

-- Appointment time confidence
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_time_confidence FLOAT;

COMMENT ON COLUMN call_analyses.appointment_time_confidence IS 'Confidence score for appointment time extraction (0.0 to 1.0)';

-- Preferred time window
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS preferred_time_window VARCHAR(100);

COMMENT ON COLUMN call_analyses.preferred_time_window IS 'Preferred time window for appointment (e.g., morning, afternoon, evening)';

-- Appointment intent
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS appointment_intent VARCHAR(50);

COMMENT ON COLUMN call_analyses.appointment_intent IS 'Appointment intent (e.g., new, reschedule, cancel)';

-- Original appointment datetime (for reschedules)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS original_appointment_datetime TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN call_analyses.original_appointment_datetime IS 'Original appointment datetime (for rescheduled appointments)';

-- New requested time (for reschedules)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS new_requested_time TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN call_analyses.new_requested_time IS 'New requested appointment time (for rescheduled appointments)';

-- ============================================================================
-- 6. SERVICE FIELDS
-- ============================================================================

-- Service requested
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS service_requested TEXT;

COMMENT ON COLUMN call_analyses.service_requested IS 'Service requested by customer';

-- Service not offered reason
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS service_not_offered_reason TEXT;

COMMENT ON COLUMN call_analyses.service_not_offered_reason IS 'Reason if service was not offered';

-- Service address (raw)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS service_address_raw TEXT;

COMMENT ON COLUMN call_analyses.service_address_raw IS 'Raw service address as mentioned in call';

-- Service address (structured)
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS service_address_structured JSONB;

COMMENT ON COLUMN call_analyses.service_address_structured IS 'Structured service address: {line1, city, state, postal_code, country}';

-- Address confidence
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS address_confidence FLOAT;

COMMENT ON COLUMN call_analyses.address_confidence IS 'Confidence score for address extraction (0.0 to 1.0)';

-- ============================================================================
-- 7. CUSTOMER FIELDS
-- ============================================================================

-- Customer name
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255);

COMMENT ON COLUMN call_analyses.customer_name IS 'Customer name extracted from call';

-- Customer name confidence
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS customer_name_confidence FLOAT;

COMMENT ON COLUMN call_analyses.customer_name_confidence IS 'Confidence score for customer name extraction (0.0 to 1.0)';

-- Decision makers
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS decision_makers TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.decision_makers IS 'List of decision makers identified (e.g., ["John Smith (homeowner)"])';

-- Urgency signals
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS urgency_signals TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.urgency_signals IS 'Urgency signals detected in call (quotes or phrases indicating urgency)';

-- Budget indicators
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS budget_indicators TEXT[] DEFAULT '{}';

COMMENT ON COLUMN call_analyses.budget_indicators IS 'Budget indicators detected in call (quotes or phrases indicating budget)';

-- ============================================================================
-- 8. FOLLOW-UP FIELDS
-- ============================================================================

-- Follow-up required
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS follow_up_required BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN call_analyses.follow_up_required IS 'Whether follow-up is required';

-- Follow-up reason
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS follow_up_reason TEXT;

COMMENT ON COLUMN call_analyses.follow_up_reason IS 'Reason why follow-up is required';

-- Qualification confidence score
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS qualification_confidence_score FLOAT;

COMMENT ON COLUMN call_analyses.qualification_confidence_score IS 'Confidence score for qualification assessment (0.0 to 1.0)';

-- ============================================================================
-- 9. ADD INDEXES FOR PERFORMANCE
-- ============================================================================

-- Index on appointment_date for filtering
CREATE INDEX IF NOT EXISTS idx_call_analyses_appointment_date 
ON call_analyses(appointment_date) 
WHERE appointment_date IS NOT NULL;

-- Index on call_outcome_category for filtering
CREATE INDEX IF NOT EXISTS idx_call_analyses_outcome_category 
ON call_analyses(call_outcome_category) 
WHERE call_outcome_category IS NOT NULL;

-- Index on follow_up_required for filtering
CREATE INDEX IF NOT EXISTS idx_call_analyses_follow_up_required 
ON call_analyses(follow_up_required) 
WHERE follow_up_required = TRUE;

-- Index on appointment_confirmed for filtering
CREATE INDEX IF NOT EXISTS idx_call_analyses_appointment_confirmed 
ON call_analyses(appointment_confirmed) 
WHERE appointment_confirmed = TRUE;

-- Index on qualification_overall_score for sorting/filtering
CREATE INDEX IF NOT EXISTS idx_call_analyses_qualification_score 
ON call_analyses(qualification_overall_score) 
WHERE qualification_overall_score IS NOT NULL;

-- ============================================================================
-- Migration Complete
-- ============================================================================
