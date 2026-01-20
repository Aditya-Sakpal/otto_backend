-- Migration: Move document URLs from company_integrations to companies table
-- (if you already created the wrong schema)

ALTER TABLE company_integrations
    DROP COLUMN IF EXISTS reference_doc_url,
    DROP COLUMN IF EXISTS sop_doc_url;

-- Ensure companies table has these columns (they should already exist per your ORM)
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS reference_doc_url TEXT,
    ADD COLUMN IF NOT EXISTS sop_doc_url TEXT;
