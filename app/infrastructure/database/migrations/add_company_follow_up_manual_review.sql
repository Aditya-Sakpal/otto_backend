-- Contextual follow-up: manual review before send (company-level toggle).
-- Replaces storing this flag in companies.extra_metadata.

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS follow_up_manual_review_enabled BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN companies.follow_up_manual_review_enabled IS
    'If true, contextual follow-up agent persists drafts (proposed) until approve-send; no auto Twilio/rep nudge.';

-- Backfill from legacy extra_metadata key (JSON boolean or string).
UPDATE companies
SET follow_up_manual_review_enabled = true
WHERE extra_metadata IS NOT NULL
  AND (
      (extra_metadata::jsonb -> 'follow_up_manual_review_enabled') = 'true'::jsonb
      OR LOWER(TRIM(extra_metadata::jsonb ->> 'follow_up_manual_review_enabled')) IN ('true', '1', 'yes')
  );
