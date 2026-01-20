-- ============================================================================
-- MIGRATION: Add Response Time Support and Enhanced CSR Data
-- ============================================================================
-- This migration adds:
-- 1. answered_at column to calls table for response time calculation
-- 2. Company integrations data
-- 3. Enhanced CSR-specific data (calls, appointments, leads)
-- ============================================================================

-- ============================================================================
-- 1. ADD answered_at COLUMN TO calls TABLE
-- ============================================================================
ALTER TABLE calls 
ADD COLUMN IF NOT EXISTS answered_at TIMESTAMP WITH TIME ZONE;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_calls_answered_at ON calls(answered_at);

-- Add comment
COMMENT ON COLUMN calls.answered_at IS 'Timestamp when the call was answered. Used to calculate response time.';

-- ============================================================================
-- 2. UPDATE EXISTING CALLS WITH answered_at (for non-missed calls)
-- ============================================================================
-- For existing calls that were not missed, set answered_at to created_at + random response time (5-15 seconds)
UPDATE calls 
SET answered_at = created_at + (RANDOM() * 10 + 5) * INTERVAL '1 second'
WHERE missed_call = false AND answered_at IS NULL;

-- ============================================================================
-- 3. COMPANY INTEGRATIONS DATA
-- ============================================================================
INSERT INTO company_integrations (
    id, 
    company_id, 
    location_id, 
    crm_provider, 
    crm_api_encrypted_key, 
    crm_company_id,
    voip_provider, 
    voip_api_encrypted_key, 
    voip_company_id,
    reference_doc_url,
    sop_doc_url,
    extra_metadata
) VALUES
-- Acme Corporation integrations
(
    'c1000000-0000-0000-0000-000000000001',
    '11111111-1111-1111-1111-111111111111',
    'NYC-001',
    'salesforce',
    'encrypted_sf_key_abc123xyz',
    'sf_company_12345',
    'ringcentral',
    'encrypted_rc_key_def456uvw',
    'rc_company_67890',
    'https://s3.example.com/docs/acme/reference-guide.pdf',
    'https://s3.example.com/docs/acme/sop-manual.pdf',
    '{"crm_version": "v2.1", "voip_plan": "enterprise"}'::JSON
),
-- Global Solutions Inc integrations
(
    'c1000000-0000-0000-0000-000000000002',
    '22222222-2222-2222-2222-222222222222',
    'LA-001',
    'hubspot',
    'encrypted_hs_key_ghi789rst',
    'hs_company_54321',
    'twilio',
    'encrypted_tw_key_jkl012mno',
    'tw_company_09876',
    'https://s3.example.com/docs/global/reference-guide.pdf',
    'https://s3.example.com/docs/global/sop-manual.pdf',
    '{"crm_version": "v3.0", "voip_plan": "professional"}'::JSON
),
-- Startup Ventures LLC integrations
(
    'c1000000-0000-0000-0000-000000000003',
    '33333333-3333-3333-3333-333333333333',
    'SF-001',
    'pipedrive',
    'encrypted_pd_key_pqr345stu',
    'pd_company_11223',
    'vonage',
    'encrypted_vg_key_vwx567yza',
    'vg_company_44556',
    NULL,
    NULL,
    '{"crm_version": "v1.5", "voip_plan": "starter"}'::JSON
);

-- ============================================================================
-- 4. ADDITIONAL CONTACT CARDS FOR CSR TESTING
-- ============================================================================
INSERT INTO contact_cards (
    id, 
    company_id, 
    primary_phone, 
    secondary_phone, 
    email, 
    first_name, 
    last_name, 
    address, 
    city, 
    state, 
    postal_code, 
    property_snapshot, 
    extra_metadata
) VALUES
-- Additional contacts for CSR calls
('10000000-0000-0000-0000-000000000011', '11111111-1111-1111-1111-111111111111', '+1-555-1011', NULL, 'csr_customer1@example.com', 'Jane', 'Doe', '111 Main St', 'New York', 'NY', '10002', '{"property_type": "residential", "sqft": 1800}', '{"source": "csr_inquiry"}'),
('10000000-0000-0000-0000-000000000012', '11111111-1111-1111-1111-111111111111', '+1-555-1021', '+1-555-1022', 'csr_customer2@example.com', 'John', 'Public', '222 Oak Ave', 'New York', 'NY', '10003', NULL, '{"source": "csr_support"}'),
('10000000-0000-0000-0000-000000000013', '11111111-1111-1111-1111-111111111111', '+1-555-1031', NULL, 'csr_customer3@example.com', 'Mary', 'Smith', '333 Pine Rd', 'Boston', 'MA', '02102', '{"property_type": "commercial"}', NULL),
('10000000-0000-0000-0000-000000000014', '11111111-1111-1111-1111-111111111111', '+1-555-1041', '+1-555-1042', 'csr_customer4@example.com', 'Robert', 'Johnson', '444 Elm St', 'Chicago', 'IL', '60602', NULL, '{"source": "csr_call"}'),
('10000000-0000-0000-0000-000000000015', '11111111-1111-1111-1111-111111111111', '+1-555-1051', NULL, 'csr_customer5@example.com', 'Susan', 'Williams', '555 Maple Dr', 'Miami', 'FL', '33102', '{"property_type": "residential", "sqft": 2200}', NULL);

-- ============================================================================
-- 5. ADDITIONAL LEADS ASSIGNED TO CSRs
-- ============================================================================
INSERT INTO leads (
    id, 
    company_id, 
    contact_card_id, 
    status, 
    deal_status, 
    assigned_rep_id, 
    deal_size, 
    closed_at, 
    extra_metadata, 
    created_at, 
    updated_at
) VALUES
-- Leads assigned to CSR Lisa (ffffffff-ffff-ffff-ffff-ffffffffffff)
('20000000-0000-0000-0000-000000000011', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000011', 'qualified_booked', 'qualified', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 3500.00, NULL, NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '18 days'),
('20000000-0000-0000-0000-000000000012', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000012', 'qualified_unbooked', 'qualified', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 4200.00, NULL, NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '12 days'),
('20000000-0000-0000-0000-000000000013', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000013', 'warm', 'nurturing', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 2800.00, NULL, NULL, NOW() - INTERVAL '8 days', NOW() - INTERVAL '6 days'),
('20000000-0000-0000-0000-000000000014', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000014', 'new', 'new', 'ffffffff-ffff-ffff-ffff-ffffffffffff', NULL, NULL, NULL, NOW() - INTERVAL '3 days', NULL),
('20000000-0000-0000-0000-000000000015', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000015', 'qualified_booked', 'qualified', 'ffffffff-ffff-ffff-ffff-ffffffffffff', 5100.00, NULL, NULL, NOW() - INTERVAL '25 days', NOW() - INTERVAL '22 days'),

-- Leads assigned to CSR Tom (99999999-9999-9999-9999-999999999999)
('20000000-0000-0000-0000-000000000016', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', 'qualified_booked', 'qualified', '99999999-9999-9999-9999-999999999999', 3800.00, NULL, NULL, NOW() - INTERVAL '18 days', NOW() - INTERVAL '16 days'),
('20000000-0000-0000-0000-000000000017', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000002', 'qualified_unbooked', 'qualified', '99999999-9999-9999-9999-999999999999', 4500.00, NULL, NULL, NOW() - INTERVAL '12 days', NOW() - INTERVAL '10 days'),
('20000000-0000-0000-0000-000000000018', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000003', 'hot', 'in_progress', '99999999-9999-9999-9999-999999999999', 6200.00, NULL, NULL, NOW() - INTERVAL '7 days', NOW() - INTERVAL '4 days'),
('20000000-0000-0000-0000-000000000019', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000004', 'new', 'new', '99999999-9999-9999-9999-999999999999', NULL, NULL, NULL, NOW() - INTERVAL '2 days', NULL),
('20000000-0000-0000-0000-000000000020', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000005', 'qualified_booked', 'qualified', '99999999-9999-9999-9999-999999999999', 4900.00, NULL, NULL, NOW() - INTERVAL '22 days', NOW() - INTERVAL '20 days');

-- ============================================================================
-- 6. ADDITIONAL CSR CALLS WITH answered_at TIMESTAMPS
-- ============================================================================
INSERT INTO calls (
    id, 
    company_id, 
    contact_card_id, 
    lead_id, 
    phone_number, 
    call_type, 
    missed_call, 
    transcript, 
    audio_url, 
    duration_seconds, 
    handled_by_user_id, 
    interaction_type, 
    extra_metadata, 
    created_at, 
    updated_at,
    answered_at
) VALUES
-- CSR Lisa calls (ffffffff-ffff-ffff-ffff-ffffffffffff) - Fast response times (5-10s)
('30000000-0000-0000-0000-000000000012', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000011', '+1-555-1011', 'csr_call', false, 'Customer inquiry about service pricing and availability.', 'https://storage.example.com/audio/csr_call1.mp3', 240, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days' + INTERVAL '8 seconds'),
('30000000-0000-0000-0000-000000000013', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000012', '20000000-0000-0000-0000-000000000012', '+1-555-1021', 'csr_call', false, 'Customer needs help with account setup and configuration.', 'https://storage.example.com/audio/csr_call2.mp3', 180, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days' + INTERVAL '6 seconds'),
('30000000-0000-0000-0000-000000000014', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000013', '20000000-0000-0000-0000-000000000013', '+1-555-1031', 'csr_call', false, 'Customer asking about billing questions and payment options.', 'https://storage.example.com/audio/csr_call3.mp3', 120, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '8 days', NOW() - INTERVAL '8 days', NOW() - INTERVAL '8 days' + INTERVAL '9 seconds'),
('30000000-0000-0000-0000-000000000015', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000014', '20000000-0000-0000-0000-000000000014', '+1-555-1041', 'csr_call', false, 'Customer wants to upgrade their service plan.', 'https://storage.example.com/audio/csr_call4.mp3', 300, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days' + INTERVAL '7 seconds'),
('30000000-0000-0000-0000-000000000016', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000015', '20000000-0000-0000-0000-000000000015', '+1-555-1051', 'csr_call', false, 'Customer reporting an issue with their current service.', 'https://storage.example.com/audio/csr_call5.mp3', 210, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '25 days', NOW() - INTERVAL '25 days', NOW() - INTERVAL '25 days' + INTERVAL '5 seconds'),

-- CSR Tom calls (99999999-9999-9999-9999-999999999999) - Slightly slower response times (10-15s)
('30000000-0000-0000-0000-000000000017', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000016', '+1-555-1001', 'csr_call', false, 'Customer inquiry about service features and benefits.', 'https://storage.example.com/audio/csr_call6.mp3', 195, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '18 days', NOW() - INTERVAL '18 days', NOW() - INTERVAL '18 days' + INTERVAL '12 seconds'),
('30000000-0000-0000-0000-000000000018', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000017', '+1-555-2001', 'csr_call', false, 'Customer needs assistance with account management.', 'https://storage.example.com/audio/csr_call7.mp3', 165, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '12 days', NOW() - INTERVAL '12 days', NOW() - INTERVAL '12 days' + INTERVAL '14 seconds'),
('30000000-0000-0000-0000-000000000019', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000018', '+1-555-3001', 'csr_call', false, 'Customer asking about contract terms and cancellation policy.', 'https://storage.example.com/audio/csr_call8.mp3', 225, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days' + INTERVAL '11 seconds'),
('30000000-0000-0000-0000-000000000020', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000019', '+1-555-4001', 'csr_call', false, 'Customer wants to schedule a service appointment.', 'https://storage.example.com/audio/csr_call9.mp3', 150, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days' + INTERVAL '13 seconds'),
('30000000-0000-0000-0000-000000000021', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000005', '20000000-0000-0000-0000-000000000020', '+1-555-5001', 'csr_call', false, 'Customer inquiry about pricing and payment plans.', 'https://storage.example.com/audio/csr_call10.mp3', 270, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '22 days', NOW() - INTERVAL '22 days', NOW() - INTERVAL '22 days' + INTERVAL '10 seconds'),

-- Some missed calls for CSR Lisa
('30000000-0000-0000-0000-000000000022', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000011', NULL, '+1-555-1011', 'missed_call', true, NULL, NULL, NULL, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '19 days', NOW() - INTERVAL '19 days', NULL),
('30000000-0000-0000-0000-000000000023', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000012', NULL, '+1-555-1021', 'missed_call', true, NULL, NULL, NULL, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '14 days', NOW() - INTERVAL '14 days', NULL),

-- Some missed calls for CSR Tom
('30000000-0000-0000-0000-000000000024', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', NULL, '+1-555-1001', 'missed_call', true, NULL, NULL, NULL, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '17 days', NOW() - INTERVAL '17 days', NULL);

-- ============================================================================
-- 7. ADDITIONAL CALL ANALYSES FOR CSR CALLS
-- ============================================================================
INSERT INTO call_analyses (
    id, 
    call_id, 
    company_id, 
    status, 
    qualification_status, 
    booking_status, 
    objections, 
    objection_texts, 
    sop_stages_completed, 
    sop_stages_missed, 
    sop_compliance_score, 
    sentiment_score, 
    summary, 
    key_points, 
    raw_analysis, 
    extra_metadata, 
    created_at, 
    updated_at
) VALUES
-- Analysis for CSR Lisa calls - Good SOP compliance
('40000000-0000-0000-0000-000000000012', '30000000-0000-0000-0000-000000000012', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'close'], ARRAY[]::VARCHAR[], 95.0, 0.75, 'Customer inquiry handled professionally. Service booked successfully.', ARRAY['Professional greeting', 'Clear communication', 'Booking completed'], '{"confidence": 0.90}'::JSON, NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days'),
('40000000-0000-0000-0000-000000000013', '30000000-0000-0000-0000-000000000013', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation'], ARRAY['close'], 85.0, 0.70, 'Customer needs more information. Follow-up required.', ARRAY['Good qualification', 'Needs follow-up'], '{"confidence": 0.85}'::JSON, NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days'),
('40000000-0000-0000-0000-000000000014', '30000000-0000-0000-0000-000000000014', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling', 'close'], ARRAY[]::VARCHAR[], 100.0, 0.80, 'Excellent call handling. All SOP stages completed. Booking successful.', ARRAY['Perfect SOP compliance', 'Booking completed'], '{"confidence": 0.95}'::JSON, NULL, NOW() - INTERVAL '8 days', NOW() - INTERVAL '8 days'),
('40000000-0000-0000-0000-000000000015', '30000000-0000-0000-0000-000000000015', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'close'], ARRAY[]::VARCHAR[], 90.0, 0.72, 'Customer upgraded service. Professional handling.', ARRAY['Service upgrade', 'Booking completed'], '{"confidence": 0.88}'::JSON, NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days'),
('40000000-0000-0000-0000-000000000016', '30000000-0000-0000-0000-000000000016', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['need'], ARRAY['Customer needs to think about it'], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling'], ARRAY['close'], 80.0, 0.65, 'Customer has a need but wants time to consider. Follow-up scheduled.', ARRAY['Need objection', 'Follow-up scheduled'], '{"confidence": 0.82}'::JSON, NULL, NOW() - INTERVAL '25 days', NOW() - INTERVAL '25 days'),

-- Analysis for CSR Tom calls - Good but slightly lower compliance
('40000000-0000-0000-0000-000000000017', '30000000-0000-0000-0000-000000000017', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'close'], ARRAY[]::VARCHAR[], 88.0, 0.73, 'Good call handling. Service booked.', ARRAY['Booking completed', 'Good communication'], '{"confidence": 0.87}'::JSON, NULL, NOW() - INTERVAL '18 days', NOW() - INTERVAL '18 days'),
('40000000-0000-0000-0000-000000000018', '30000000-0000-0000-0000-000000000018', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification'], ARRAY['presentation', 'close'], 70.0, 0.68, 'Customer needs more information. Presentation stage missed.', ARRAY['Needs more info', 'Presentation missed'], '{"confidence": 0.75}'::JSON, NULL, NOW() - INTERVAL '12 days', NOW() - INTERVAL '12 days'),
('40000000-0000-0000-0000-000000000019', '30000000-0000-0000-0000-000000000019', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'close'], ARRAY[]::VARCHAR[], 85.0, 0.70, 'Customer booked after discussing contract terms.', ARRAY['Contract discussion', 'Booking completed'], '{"confidence": 0.83}'::JSON, NULL, NOW() - INTERVAL '7 days', NOW() - INTERVAL '7 days'),
('40000000-0000-0000-0000-000000000020', '30000000-0000-0000-0000-000000000020', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'booked', ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY['greeting', 'qualification', 'presentation', 'close'], ARRAY[]::VARCHAR[], 90.0, 0.75, 'Appointment scheduled successfully. Good call flow.', ARRAY['Appointment scheduled', 'Good flow'], '{"confidence": 0.89}'::JSON, NULL, NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days'),
('40000000-0000-0000-0000-000000000021', '30000000-0000-0000-0000-000000000021', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['price'], ARRAY['Price is a concern'], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling'], ARRAY['close'], 82.0, 0.60, 'Price objection raised. Needs follow-up with pricing options.', ARRAY['Price objection', 'Needs pricing follow-up'], '{"confidence": 0.80}'::JSON, NULL, NOW() - INTERVAL '22 days', NOW() - INTERVAL '22 days');

-- ============================================================================
-- 8. APPOINTMENTS ASSIGNED TO CSRs
-- ============================================================================
INSERT INTO appointments (
    id, 
    company_id, 
    lead_id, 
    contact_card_id, 
    scheduled_start, 
    scheduled_end, 
    location_address, 
    outcome, 
    assigned_rep_id, 
    extra_metadata, 
    created_at, 
    updated_at
) VALUES
-- Appointments for CSR Lisa
('50000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000011', '10000000-0000-0000-0000-000000000011', NOW() + INTERVAL '3 days', NOW() + INTERVAL '3 days' + INTERVAL '1 hour', '111 Main St, New York, NY 10002', 'pending', 'ffffffff-ffff-ffff-ffff-ffffffffffff', NULL, NOW() - INTERVAL '18 days', NOW() - INTERVAL '18 days'),
('50000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000015', '10000000-0000-0000-0000-000000000015', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days' + INTERVAL '1 hour', '555 Maple Dr, Miami, FL 33102', 'won', 'ffffffff-ffff-ffff-ffff-ffffffffffff', NULL, NOW() - INTERVAL '22 days', NOW() - INTERVAL '2 days'),

-- Appointments for CSR Tom
('50000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000016', '10000000-0000-0000-0000-000000000001', NOW() + INTERVAL '4 days', NOW() + INTERVAL '4 days' + INTERVAL '1 hour', '789 Customer St, New York, NY 10001', 'pending', '99999999-9999-9999-9999-999999999999', NULL, NOW() - INTERVAL '16 days', NOW() - INTERVAL '16 days'),
('50000000-0000-0000-0000-000000000009', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000020', '10000000-0000-0000-0000-000000000005', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day' + INTERVAL '1 hour', '987 Pine Rd, Seattle, WA 98101', 'won', '99999999-9999-9999-9999-999999999999', NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day'),
('50000000-0000-0000-0000-000000000010', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000018', '10000000-0000-0000-0000-000000000003', NOW() + INTERVAL '2 days', NOW() + INTERVAL '2 days' + INTERVAL '1 hour', '654 Oak Blvd, Chicago, IL 60601', 'pending', '99999999-9999-9999-9999-999999999999', NULL, NOW() - INTERVAL '4 days', NOW() - INTERVAL '4 days');

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Migration completed:
-- 1. Added answered_at column to calls table
-- 2. Updated existing calls with answered_at timestamps
-- 3. Added 3 company integrations records
-- 4. Added 5 additional contact cards for CSR testing
-- 5. Added 10 leads assigned to CSRs (5 each)
-- 6. Added 13 CSR calls with answered_at timestamps (8 for Lisa, 5 for Tom)
-- 7. Added 10 call analyses for CSR calls
-- 8. Added 5 appointments assigned to CSRs
-- ============================================================================
