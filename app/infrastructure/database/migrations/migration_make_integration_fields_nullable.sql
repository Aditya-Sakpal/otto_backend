-- Migration: Make company integration fields nullable
-- Description: Makes CRM and VOIP fields optional in company_integrations table
-- Date: 2024-01-20
-- Safe migration: Only runs if table exists

DO $$
BEGIN
    -- Check if table exists before attempting migration
    IF EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = 'company_integrations'
    ) THEN

        -- Make location_id nullable if column exists and is NOT NULL
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'company_integrations'
            AND column_name = 'location_id'
            AND is_nullable = 'NO'
        ) THEN
            ALTER TABLE company_integrations
            ALTER COLUMN location_id DROP NOT NULL;
            RAISE NOTICE 'Made location_id nullable';
        END IF;

        -- Make crm_api_encrypted_key nullable if column exists and is NOT NULL
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'company_integrations'
            AND column_name = 'crm_api_encrypted_key'
            AND is_nullable = 'NO'
        ) THEN
            ALTER TABLE company_integrations
            ALTER COLUMN crm_api_encrypted_key DROP NOT NULL;
            RAISE NOTICE 'Made crm_api_encrypted_key nullable';
        END IF;

        -- Make crm_provider nullable if column exists and is NOT NULL
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'company_integrations'
            AND column_name = 'crm_provider'
            AND is_nullable = 'NO'
        ) THEN
            ALTER TABLE company_integrations
            ALTER COLUMN crm_provider DROP NOT NULL;
            RAISE NOTICE 'Made crm_provider nullable';
        END IF;

        -- Make voip_api_encrypted_key nullable if column exists and is NOT NULL
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'company_integrations'
            AND column_name = 'voip_api_encrypted_key'
            AND is_nullable = 'NO'
        ) THEN
            ALTER TABLE company_integrations
            ALTER COLUMN voip_api_encrypted_key DROP NOT NULL;
            RAISE NOTICE 'Made voip_api_encrypted_key nullable';
        END IF;

        -- Make voip_provider nullable if column exists and is NOT NULL
        IF EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'company_integrations'
            AND column_name = 'voip_provider'
            AND is_nullable = 'NO'
        ) THEN
            ALTER TABLE company_integrations
            ALTER COLUMN voip_provider DROP NOT NULL;
            RAISE NOTICE 'Made voip_provider nullable';
        END IF;

        -- Add comments to document the changes (safe to run multiple times)
        COMMENT ON COLUMN company_integrations.location_id IS 'GHL location ID (optional)';
        COMMENT ON COLUMN company_integrations.crm_api_encrypted_key IS 'Encrypted CRM API key (optional)';
        COMMENT ON COLUMN company_integrations.crm_provider IS 'CRM provider name (optional)';
        COMMENT ON COLUMN company_integrations.crm_company_id IS 'CRM company ID (optional)';
        COMMENT ON COLUMN company_integrations.voip_api_encrypted_key IS 'Encrypted VoIP API key (optional)';
        COMMENT ON COLUMN company_integrations.voip_provider IS 'VoIP provider name (optional)';
        COMMENT ON COLUMN company_integrations.voip_company_id IS 'VoIP company ID (optional)';

        RAISE NOTICE 'Migration completed successfully';
    ELSE
        RAISE NOTICE 'Table company_integrations does not exist, skipping migration';
    END IF;
END $$;
