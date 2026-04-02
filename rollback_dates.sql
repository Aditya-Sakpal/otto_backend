-- ============================================================
-- ROLLBACK SCRIPT: Restore original dates for company d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a
--
-- Run this to undo all date changes:
-- psql $DATABASE_URL -f rollback_dates.sql
-- ============================================================

BEGIN;

-- 1. Restore calls
UPDATE calls c SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    answered_at = b.answered_at
FROM _backup_calls_dates b
WHERE c.id = b.id;

-- 2. Restore appointments
UPDATE appointments a SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    scheduled_start = b.scheduled_start,
    scheduled_end = b.scheduled_end,
    original_appointment_datetime = b.original_appointment_datetime,
    analysis_appointment_date = b.analysis_appointment_date,
    analysis_created_at = b.analysis_created_at,
    analysis_updated_at = b.analysis_updated_at,
    new_requested_time = b.new_requested_time,
    recording_started_at = b.recording_started_at,
    recording_completed_at = b.recording_completed_at
FROM _backup_appointments_dates b
WHERE a.id = b.id;

-- 3. Restore leads
UPDATE leads l SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    closed_at = b.closed_at
FROM _backup_leads_dates b
WHERE l.id = b.id;

-- 4. Restore call_analyses
UPDATE call_analyses ca SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    appointment_date = b.appointment_date,
    new_requested_time = b.new_requested_time
FROM _backup_call_analyses_dates b
WHERE ca.id = b.id;

-- 5. Restore coaching_sessions
UPDATE coaching_sessions cs SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    coached_at = b.coached_at,
    follow_up_end_date = b.follow_up_end_date
FROM _backup_coaching_sessions_dates b
WHERE cs.id = b.id;

-- 6. Restore coaching_issues
UPDATE coaching_issues ci SET
    created_at = b.created_at
FROM _backup_coaching_issues_dates b
WHERE ci.id = b.id;

-- 7. Restore coaching_strengths
UPDATE coaching_strengths cs SET
    created_at = b.created_at
FROM _backup_coaching_strengths_dates b
WHERE cs.id = b.id;

-- 8. Restore ask_otto_conversations
UPDATE ask_otto_conversations aoc SET
    created_at = b.created_at,
    updated_at = b.updated_at
FROM _backup_ask_otto_conversations_dates b
WHERE aoc.id = b.id;

-- 9. Restore ask_otto_messages
UPDATE ask_otto_messages aom SET
    created_at = b.created_at
FROM _backup_ask_otto_messages_dates b
WHERE aom.id = b.id;

-- 10. Restore action_items
UPDATE action_items ai SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    due_at = b.due_at
FROM _backup_action_items_dates b
WHERE ai.id = b.id;

-- 11. Restore pending_actions
UPDATE pending_actions pa SET
    created_at = b.created_at,
    updated_at = b.updated_at,
    due_at = b.due_at
FROM _backup_pending_actions_dates b
WHERE pa.id = b.id;

-- 12. Restore lead_status_changes
UPDATE lead_status_changes lsc SET
    created_at = b.created_at
FROM _backup_lead_status_changes_dates b
WHERE lsc.id = b.id;

-- 13. Restore call_objection_details
UPDATE call_objection_details cod SET
    created_at = b.created_at
FROM _backup_call_objection_details_dates b
WHERE cod.id = b.id;

COMMIT;

-- Optional: Drop backup tables after successful rollback
-- DROP TABLE IF EXISTS _backup_calls_dates, _backup_appointments_dates, _backup_leads_dates,
--     _backup_call_analyses_dates, _backup_coaching_sessions_dates, _backup_coaching_issues_dates,
--     _backup_coaching_strengths_dates, _backup_ask_otto_conversations_dates, _backup_ask_otto_messages_dates,
--     _backup_action_items_dates, _backup_pending_actions_dates, _backup_lead_status_changes_dates,
--     _backup_call_objection_details_dates;
-- DROP FUNCTION IF EXISTS _map_date(timestamptz);

SELECT 'Date rollback completed successfully!' as status;

-- ============================================================
-- ROLLBACK OBJECTION CATEGORIES
-- ============================================================

BEGIN;

-- Restore call_objection_details categories
UPDATE call_objection_details cod SET
    category_id = b.category_id,
    category_text = b.category_text
FROM _backup_call_objection_details_categories b
WHERE cod.id = b.id;

-- Restore call_analyses objections
UPDATE call_analyses ca SET
    objections = b.objections,
    objection_texts = b.objection_texts,
    objections_total_count = b.objections_total_count
FROM _backup_call_analyses_objections b
WHERE ca.id = b.id;

COMMIT;

SELECT 'Objection rollback completed successfully!' as status;
