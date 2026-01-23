-- Migration: Add new fields from Shunya Summary API
-- These fields were added in the updated Shunya Summary API response structure
-- Date: 2026-01-23

-- Add compliance.target_role field
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS compliance_target_role VARCHAR(50) NULL;

-- Add qualification fields
ALTER TABLE call_analyses
ADD COLUMN IF NOT EXISTS detected_call_type VARCHAR(50) NULL,
ADD COLUMN IF NOT EXISTS is_existing_customer BOOLEAN NULL,
ADD COLUMN IF NOT EXISTS is_deprioritized BOOLEAN NULL,
ADD COLUMN IF NOT EXISTS service_wait_time_weeks INTEGER NULL,
ADD COLUMN IF NOT EXISTS applied_rules TEXT[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS property_details JSONB NULL,
ADD COLUMN IF NOT EXISTS customer_details JSONB NULL;

-- Add indexes for commonly queried fields
CREATE INDEX IF NOT EXISTS idx_call_analyses_compliance_target_role ON call_analyses(compliance_target_role);
CREATE INDEX IF NOT EXISTS idx_call_analyses_detected_call_type ON call_analyses(detected_call_type);
CREATE INDEX IF NOT EXISTS idx_call_analyses_is_existing_customer ON call_analyses(is_existing_customer);
CREATE INDEX IF NOT EXISTS idx_call_analyses_is_deprioritized ON call_analyses(is_deprioritized);

-- Add comment for documentation
COMMENT ON COLUMN call_analyses.compliance_target_role IS 'The role this call was evaluated against (e.g., customer_rep, sales_rep)';
COMMENT ON COLUMN call_analyses.detected_call_type IS 'Type of call: fresh_sales, follow_up_inquiry, existing_customer_service';
COMMENT ON COLUMN call_analyses.is_existing_customer IS 'Whether this is an existing customer';
COMMENT ON COLUMN call_analyses.is_deprioritized IS 'Whether service is deprioritized per tenant rules';
COMMENT ON COLUMN call_analyses.service_wait_time_weeks IS 'Wait time in weeks if service is deferred';
COMMENT ON COLUMN call_analyses.applied_rules IS 'Tenant-specific rules that were applied';
COMMENT ON COLUMN call_analyses.property_details IS 'Home services property information (roof_type, roof_age_years, stories, hoa_status, etc.)';
COMMENT ON COLUMN call_analyses.customer_details IS 'Customer details with address, phone, email, decision_makers';
