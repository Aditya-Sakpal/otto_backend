-- Migration: Add lead_source column to leads table
-- This allows tracking lead source (e.g. Google, LSA, Yelp) directly on the lead,
-- populated from CRM integrations (GoHighLevel, ServiceTitan).

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS lead_source VARCHAR(255) NULL;

CREATE INDEX IF NOT EXISTS idx_leads_lead_source ON leads(lead_source);

COMMENT ON COLUMN leads.lead_source IS 'Lead source from CRM (e.g. Google, LSA, Yelp, Meta ad)';
