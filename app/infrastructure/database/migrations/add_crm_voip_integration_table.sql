/**
 * TABLE: company_integrations
 * DESCRIPTION: Stores third-party integration credentials (CRM, VoIP) for each company/location.
 * Document references (SOPs and Reference guides) are stored in the companies table.
 * AUTH: System Admin / Integration Service
 */

-- Enable extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS company_integrations (
    -- Primary and Foreign Keys
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL,
    
    -- Integration Identifiers
    location_id VARCHAR NOT NULL,
    
    -- CRM (Customer Relationship Management) Configuration
    crm_provider VARCHAR NOT NULL,
    crm_api_encrypted_key VARCHAR NOT NULL,
    crm_company_id VARCHAR,
    
    -- VoIP (Voice over IP) / CTM Configuration
    voip_provider VARCHAR NOT NULL,
    voip_api_encrypted_key VARCHAR NOT NULL,
    voip_company_id VARCHAR,
    
    -- Extensibility
    extra_metadata JSON,
    
    -- Constraints
    CONSTRAINT fk_company
        FOREIGN KEY(company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

-- Performance Optimization
-- This index is critical as we frequently filter integrations by the parent company ID.
CREATE INDEX ix_company_integrations_company_id ON company_integrations (company_id);

/**
 * Database-level comments 
 */
COMMENT ON TABLE company_integrations IS 'Stores encrypted credentials for company-level integrations. Document URLs are stored in companies table.';
COMMENT ON COLUMN company_integrations.crm_api_encrypted_key IS 'AES-encrypted. Decrypt only at the application service layer.';
COMMENT ON COLUMN company_integrations.voip_api_encrypted_key IS 'AES-encrypted. Decrypt only at the application service layer.';