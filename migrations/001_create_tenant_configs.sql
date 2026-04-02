-- Migration: Create tenant_configs table
-- Date: 2026-03-09

CREATE TABLE IF NOT EXISTS tenant_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL UNIQUE REFERENCES companies(id),
    company_name VARCHAR NOT NULL,
    shunya_config_id VARCHAR,
    qualification_thresholds JSONB,
    service_prioritization JSONB,
    custom_keywords JSONB,
    qualification_rules JSONB,
    business_hours JSONB,
    service_area JSONB,
    industry VARCHAR,
    primary_services JSONB,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_tenant_configs_company_id ON tenant_configs(company_id);
