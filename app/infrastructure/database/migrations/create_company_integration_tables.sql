-- Ensure the uuid-ossp extension is enabled if you want the DB to handle defaults
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE company_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL,
    location_id VARCHAR NOT NULL,
    crm_api_encrypted_key VARCHAR NOT NULL,
    crm_provider VARCHAR NOT NULL,
    crm_company_id VARCHAR,
    voip_api_encrypted_key VARCHAR NOT NULL,
    voip_provider VARCHAR NOT NULL,
    voip_company_id VARCHAR,
    extra_metadata JSON,

    -- Foreign Key Constraint
    CONSTRAINT fk_company
        FOREIGN KEY(company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

-- Index for optimized lookups by company_id
CREATE INDEX ix_company_integrations_company_id ON company_integrations (company_id);
