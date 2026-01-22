-- ============================================================================
-- Migration: Add role column to invitations
-- ============================================================================
-- Adds a role column to the invitations table to store the invited user's role.
-- Default is 'csr' to match the application default (UserRole.CSR).
-- ============================================================================

-- Add role column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'invitations'
          AND column_name = 'role'
    ) THEN
        ALTER TABLE invitations
        ADD COLUMN role VARCHAR(50) NOT NULL DEFAULT 'csr';
    END IF;
END $$;

