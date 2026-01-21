-- ============================================================================
-- Migration: Add Recording Handling Fields
-- ============================================================================
-- This migration adds fields to support recording handling for mobile uploads:
-- 1. interaction_id column to appointments table (FK to calls.id)
-- 2. status column to calls table (pending, processing, completed)
-- 3. shunya_job_id column to calls table (for tracking Shunya processing jobs)
-- ============================================================================

-- ============================================================================
-- 1. ADD interaction_id COLUMN TO appointments TABLE
-- ============================================================================
ALTER TABLE appointments
ADD COLUMN IF NOT EXISTS interaction_id UUID REFERENCES calls(id) ON DELETE SET NULL;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_appointments_interaction_id ON appointments(interaction_id);

-- Add comment
COMMENT ON COLUMN appointments.interaction_id IS 'Directly points to the Call record once recording starts. This is the single source of truth for whether a meeting has AI data.';

-- ============================================================================
-- 2. ADD status COLUMN TO calls TABLE
-- ============================================================================
ALTER TABLE calls
ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending';

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);

-- Add comment
COMMENT ON COLUMN calls.status IS 'Tracks call processing status: pending, processing, completed, or failed.';

-- Update existing calls to have 'pending' status if they don't have one
-- (This handles existing records that might have NULL status)
UPDATE calls
SET status = 'pending'
WHERE status IS NULL;

-- ============================================================================
-- 3. ADD shunya_job_id COLUMN TO calls TABLE
-- ============================================================================
ALTER TABLE calls
ADD COLUMN IF NOT EXISTS shunya_job_id VARCHAR;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_calls_shunya_job_id ON calls(shunya_job_id);

-- Add comment
COMMENT ON COLUMN calls.shunya_job_id IS 'Stores the ID returned by Shunya Labs for tracking call processing jobs.';

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Migration completed:
-- 1. Added interaction_id column to appointments table (FK to calls.id)
-- 2. Added status column to calls table (default 'pending')
-- 3. Added shunya_job_id column to calls table
-- 4. Created indexes for performance
-- 5. Updated existing calls to have 'pending' status
-- ============================================================================
