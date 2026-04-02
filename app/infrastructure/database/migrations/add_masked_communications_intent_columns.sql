-- Intent-to-Action: store classifier output on inbound comms rows.
ALTER TABLE masked_communications
    ADD COLUMN IF NOT EXISTS intent_label VARCHAR(64),
    ADD COLUMN IF NOT EXISTS confidence_score DOUBLE PRECISION;

COMMENT ON COLUMN masked_communications.intent_label IS
    'Inbound reply intent: interested | price_objection | timing_issue | not_interested | call_me | unclear';
COMMENT ON COLUMN masked_communications.confidence_score IS
    'Classifier confidence in [0, 1]';

CREATE INDEX IF NOT EXISTS idx_masked_comms_intent_label
    ON masked_communications (intent_label)
    WHERE intent_label IS NOT NULL;
