-- Migration: Add ServiceTitan credential columns to company_integrations

ALTER TABLE company_integrations
  ADD COLUMN IF NOT EXISTS st_tenant_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_client_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_client_secret_encrypted VARCHAR NULL;

CREATE INDEX IF NOT EXISTS ix_ci_st_tenant_id
  ON company_integrations (st_tenant_id) WHERE st_tenant_id IS NOT NULL;

COMMENT ON COLUMN company_integrations.st_tenant_id IS 'ServiceTitan tenant ID';
COMMENT ON COLUMN company_integrations.st_client_secret_encrypted IS 'Encrypted ST client_secret (AES-256)';
