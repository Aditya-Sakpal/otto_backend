-- ============================================================================
-- COMPREHENSIVE DUMMY DATA SCRIPT FOR OTTO AI BACKEND
-- ============================================================================
-- This script inserts dummy data covering all scenarios, statuses, and edge cases
-- Run this after creating tables to populate the database with test data
-- ============================================================================

-- Clear existing data (optional - comment out if you want to keep existing data)
-- TRUNCATE TABLE ask_otto_messages CASCADE;
-- TRUNCATE TABLE ask_otto_conversations CASCADE;
-- TRUNCATE TABLE insight_jobs CASCADE;
-- TRUNCATE TABLE call_processing_jobs CASCADE;
-- TRUNCATE TABLE pending_actions CASCADE;
-- TRUNCATE TABLE invitations CASCADE;
-- TRUNCATE TABLE call_analyses CASCADE;
-- TRUNCATE TABLE appointments CASCADE;
-- TRUNCATE TABLE calls CASCADE;
-- TRUNCATE TABLE leads CASCADE;
-- TRUNCATE TABLE contact_cards CASCADE;
-- TRUNCATE TABLE users CASCADE;
-- TRUNCATE TABLE companies CASCADE;

-- ============================================================================
-- 1. COMPANIES
-- ============================================================================
INSERT INTO companies (id, name, phone_number, address, extra_metadata) VALUES
('11111111-1111-1111-1111-111111111111', 'Acme Corporation', '+1-555-0100', '123 Business St, New York, NY 10001', '{"industry": "Technology", "founded": 2010}'),
('22222222-2222-2222-2222-222222222222', 'Global Solutions Inc', '+1-555-0200', '456 Commerce Ave, Los Angeles, CA 90001', '{"industry": "Consulting", "founded": 2015}'),
('33333333-3333-3333-3333-333333333333', 'Startup Ventures LLC', '+1-555-0300', NULL, '{"industry": "Finance"}');

-- ============================================================================
-- 2. USERS (All Roles: CSR, SALES_REP, EXECUTIVE)
-- ============================================================================
INSERT INTO users (id, email, password_hash, role, is_active, first_name, last_name, company_id, extra_metadata, created_at) VALUES
-- Executives
('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'exec@acme.com', '$2b$12$dummy', 'executive', true, 'John', 'Executive', '11111111-1111-1111-1111-111111111111', '{"department": "Management"}', NOW() - INTERVAL '1 year'),
('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'ceo@global.com', '$2b$12$dummy', 'executive', true, 'Sarah', 'CEO', '22222222-2222-2222-2222-222222222222', NULL, NOW() - INTERVAL '6 months'),

-- Sales Reps
('cccccccc-cccc-cccc-cccc-cccccccccccc', 'sales1@acme.com', '$2b$12$dummy', 'sales_rep', true, 'Mike', 'Salesman', '11111111-1111-1111-1111-111111111111', '{"territory": "East Coast"}', NOW() - INTERVAL '8 months'),
('dddddddd-dddd-dddd-dddd-dddddddddddd', 'sales2@acme.com', '$2b$12$dummy', 'sales_rep', true, 'Emily', 'Rep', '11111111-1111-1111-1111-111111111111', '{"territory": "West Coast"}', NOW() - INTERVAL '6 months'),
('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'sales3@global.com', '$2b$12$dummy', 'sales_rep', true, 'David', 'Seller', '22222222-2222-2222-2222-222222222222', NULL, NOW() - INTERVAL '4 months'),

-- CSRs
('ffffffff-ffff-ffff-ffff-ffffffffffff', 'csr1@acme.com', '$2b$12$dummy', 'csr', true, 'Lisa', 'Support', '11111111-1111-1111-1111-111111111111', NULL, NOW() - INTERVAL '3 months'),
('99999999-9999-9999-9999-999999999999', 'csr2@acme.com', '$2b$12$dummy', 'csr', true, 'Tom', 'Helper', '11111111-1111-1111-1111-111111111111', NULL, NOW() - INTERVAL '2 months'),

-- Inactive user
('88888888-8888-8888-8888-888888888888', 'inactive@acme.com', '$2b$12$dummy', 'sales_rep', false, 'Inactive', 'User', '11111111-1111-1111-1111-111111111111', NULL, NOW() - INTERVAL '1 year');

-- ============================================================================
-- 3. CONTACT CARDS
-- ============================================================================
INSERT INTO contact_cards (id, company_id, primary_phone, secondary_phone, email, first_name, last_name, address, city, state, postal_code, property_snapshot, extra_metadata) VALUES
-- Complete contact info
('10000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '+1-555-1001', '+1-555-1002', 'customer1@example.com', 'Alice', 'Johnson', '789 Customer St', 'New York', 'NY', '10001', '{"property_type": "residential", "sqft": 2000}', '{"source": "website"}'),
('10000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '+1-555-2001', NULL, 'customer2@example.com', 'Bob', 'Smith', '321 Main Ave', 'Boston', 'MA', '02101', NULL, NULL),
('10000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '+1-555-3001', '+1-555-3002', 'customer3@example.com', 'Carol', 'Williams', '654 Oak Blvd', 'Chicago', 'IL', '60601', '{"property_type": "commercial"}', '{"source": "referral"}'),
('10000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '+1-555-4001', NULL, NULL, 'David', 'Brown', NULL, 'Miami', 'FL', '33101', NULL, NULL),
('10000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '+1-555-5001', '+1-555-5002', 'customer5@example.com', 'Eva', 'Davis', '987 Pine Rd', 'Seattle', 'WA', '98101', '{"property_type": "residential", "sqft": 1500}', '{"source": "cold_call"}'),
('10000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '+1-555-6001', NULL, 'customer6@example.com', 'Frank', 'Miller', '147 Elm St', 'Denver', 'CO', '80201', NULL, NULL),
('10000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '+1-555-7001', '+1-555-7002', 'customer7@example.com', 'Grace', 'Wilson', '258 Maple Dr', 'Phoenix', 'AZ', '85001', '{"property_type": "residential"}', '{"source": "website"}'),
('10000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', '+1-555-8001', NULL, 'customer8@example.com', 'Henry', 'Moore', '369 Cedar Ln', 'Austin', 'TX', '73301', NULL, NULL),
('10000000-0000-0000-0000-000000000009', '22222222-2222-2222-2222-222222222222', '+1-555-9001', '+1-555-9002', 'customer9@example.com', 'Iris', 'Taylor', '741 Birch Way', 'Portland', 'OR', '97201', '{"property_type": "commercial"}', NULL),
('10000000-0000-0000-0000-000000000010', '22222222-2222-2222-2222-222222222222', '+1-555-0011', NULL, 'customer10@example.com', 'Jack', 'Anderson', '852 Spruce Ct', 'San Francisco', 'CA', '94101', NULL, NULL);

-- ============================================================================
-- 4. LEADS (All Statuses and Deal Statuses)
-- ============================================================================
INSERT INTO leads (id, company_id, contact_card_id, status, deal_status, assigned_rep_id, deal_size, closed_at, extra_metadata, created_at, updated_at) VALUES
-- Qualified leads (for testing qualified_leads metric)
('20000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', 'qualified_booked', 'qualified', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 5000.00, NULL, NULL, NOW() - INTERVAL '80 days', NOW() - INTERVAL '75 days'),
('20000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000002', 'qualified_unbooked', 'qualified', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 7500.00, NULL, NULL, NOW() - INTERVAL '55 days', NOW() - INTERVAL '50 days'),
('20000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000003', 'qualified_service_not_offered', 'qualified', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 3000.00, NULL, NULL, NOW() - INTERVAL '40 days', NOW() - INTERVAL '35 days'),

-- New leads
('20000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000004', 'new', 'new', NULL, NULL, NULL, NULL, NOW() - INTERVAL '25 days', NULL),
('20000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000005', 'new', 'new', 'dddddddd-dddd-dddd-dddd-dddddddddddd', NULL, NULL, NULL, NOW() - INTERVAL '15 days', NULL),

-- Warm/Hot leads
('20000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000006', 'warm', 'nurturing', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 2000.00, NULL, NULL, NOW() - INTERVAL '10 days', NOW() - INTERVAL '8 days'),
('20000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000007', 'hot', 'in_progress', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 10000.00, NULL, NULL, NOW() - INTERVAL '5 days', NOW() - INTERVAL '2 days'),

-- Closed leads
('20000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000008', 'closed_won', 'won', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 15000.00, NOW() - INTERVAL '3 days', NULL, NOW() - INTERVAL '30 days', NOW() - INTERVAL '3 days'),
('20000000-0000-0000-0000-000000000009', '22222222-2222-2222-2222-222222222222', '10000000-0000-0000-0000-000000000009', 'closed_lost', 'lost', 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', NULL, NOW() - INTERVAL '1 day', NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day'),
('20000000-0000-0000-0000-000000000010', '22222222-2222-2222-2222-222222222222', '10000000-0000-0000-0000-000000000010', 'nurturing', 'nurturing', 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 5000.00, NULL, NULL, NOW() - INTERVAL '10 days', NULL);

-- ============================================================================
-- 5. CALLS (All Types, Missed/Not Missed, With/Without Transcripts)
-- ============================================================================
INSERT INTO calls (id, company_id, contact_card_id, lead_id, phone_number, call_type, missed_call, transcript, audio_url, duration_seconds, handled_by_user_id, interaction_type, extra_metadata, created_at, updated_at) VALUES
-- Sales calls with transcripts
('30000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', '+1-555-1001', 'sales_call', false, 'Hello, I am interested in your services. What are your pricing options?', 'https://storage.example.com/audio/call1.mp3', 180, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'call', NULL, NOW() - INTERVAL '80 days', NOW() - INTERVAL '80 days'),
('30000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', '+1-555-2001', 'sales_call', false, 'I need to discuss pricing. Your service seems expensive compared to competitors.', 'https://storage.example.com/audio/call2.mp3', 240, 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'call', NULL, NOW() - INTERVAL '55 days', NOW() - INTERVAL '55 days'),
('30000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000003', '+1-555-3001', 'sales_call', false, 'The timing is not right for us. We might be interested next quarter.', 'https://storage.example.com/audio/call3.mp3', 300, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'call', NULL, NOW() - INTERVAL '40 days', NOW() - INTERVAL '40 days'),
('30000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000004', '+1-555-4001', 'sales_call', false, 'I need to check with my manager before making a decision.', 'https://storage.example.com/audio/call4.mp3', 120, NULL, 'call', NULL, NOW() - INTERVAL '25 days', NOW() - INTERVAL '25 days'),
('30000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000005', '20000000-0000-0000-0000-000000000005', '+1-555-5001', 'sales_call', false, 'We already have a solution from another vendor. Why should we switch?', 'https://storage.example.com/audio/call5.mp3', 360, 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'call', NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days'),

-- CSR calls
('30000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000006', '20000000-0000-0000-0000-000000000006', '+1-555-6001', 'csr_call', false, 'I have a question about my existing service.', 'https://storage.example.com/audio/call6.mp3', 90, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'call', NULL, NOW() - INTERVAL '10 days', NOW() - INTERVAL '10 days'),
('30000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000007', '20000000-0000-0000-0000-000000000007', '+1-555-7001', 'csr_call', false, 'I need help with billing.', 'https://storage.example.com/audio/call7.mp3', 150, '99999999-9999-9999-9999-999999999999', 'call', NULL, NOW() - INTERVAL '5 days', NOW() - INTERVAL '5 days'),

-- Missed calls
('30000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000008', '20000000-0000-0000-0000-000000000008', '+1-555-8001', 'missed_call', true, NULL, NULL, NULL, NULL, 'call', NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days'),
('30000000-0000-0000-0000-000000000009', '22222222-2222-2222-2222-222222222222', '10000000-0000-0000-0000-000000000009', '20000000-0000-0000-0000-000000000009', '+1-555-9001', 'missed_call', true, NULL, NULL, NULL, NULL, 'call', NULL, NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days'),

-- Calls without transcripts
('30000000-0000-0000-0000-000000000010', '22222222-2222-2222-2222-222222222222', '10000000-0000-0000-0000-000000000010', '20000000-0000-0000-0000-000000000010', '+1-555-0011', 'sales_call', false, NULL, 'https://storage.example.com/audio/call10.mp3', 200, 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'call', NULL, NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day'),

-- Recent calls for testing
('30000000-0000-0000-0000-000000000011', '11111111-1111-1111-1111-111111111111', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', '+1-555-1001', 'sales_call', false, 'Follow-up call about pricing. The cost is still a concern for us.', 'https://storage.example.com/audio/call11.mp3', 180, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'call', NULL, NOW() - INTERVAL '12 hours', NOW() - INTERVAL '12 hours');

-- ============================================================================
-- 6. CALL ANALYSES (All Statuses, Various Objections, SOP Compliance, Sentiment)
-- ============================================================================
INSERT INTO call_analyses (id, call_id, company_id, status, qualification_status, booking_status, objections, objection_texts, sop_stages_completed, sop_stages_missed, sop_compliance_score, sentiment_score, summary, key_points, raw_analysis, extra_metadata, created_at, updated_at) VALUES
-- Completed analysis with price objection
('40000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['price', 'pricing'], ARRAY['What are your pricing options?', 'The service seems expensive'], ARRAY['greeting', 'qualification', 'presentation'], ARRAY['close'], 75.5, 0.65, 'Customer inquired about pricing and expressed concerns about cost. Qualified lead but not ready to book.', ARRAY['Price concern', 'Qualified lead', 'Needs follow-up'], '{"confidence": 0.85}', NULL, NOW() - INTERVAL '80 days', NOW() - INTERVAL '80 days'),

-- Completed analysis with pricing objection (variation)
('40000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['pricing', 'cost'], ARRAY['Your service seems expensive compared to competitors'], ARRAY['greeting', 'qualification'], ARRAY['presentation', 'close'], 50.0, 0.45, 'Customer raised pricing concerns and compared to competitors. Needs competitive analysis.', ARRAY['Pricing objection', 'Competitor comparison'], '{"confidence": 0.78}', NULL, NOW() - INTERVAL '55 days', NOW() - INTERVAL '55 days'),

-- Completed analysis with timing objection
('40000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['timing'], ARRAY['The timing is not right for us. We might be interested next quarter.'], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling'], ARRAY['close'], 90.0, 0.70, 'Customer interested but timing is not right. Qualified for future engagement.', ARRAY['Timing objection', 'Future opportunity'], '{"confidence": 0.82}', NULL, NOW() - INTERVAL '40 days', NOW() - INTERVAL '40 days'),

-- Completed analysis with authority objection
('40000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['authority'], ARRAY['I need to check with my manager before making a decision'], ARRAY['greeting', 'qualification'], ARRAY['presentation', 'objection_handling', 'close'], 40.0, 0.60, 'Customer needs manager approval. Decision maker not on call.', ARRAY['Authority objection', 'Needs decision maker'], '{"confidence": 0.75}', NULL, NOW() - INTERVAL '25 days', NOW() - INTERVAL '25 days'),

-- Completed analysis with competitor objection
('40000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['competitor'], ARRAY['We already have a solution from another vendor. Why should we switch?'], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling'], ARRAY['close'], 85.0, 0.55, 'Customer has existing solution. Needs competitive differentiation.', ARRAY['Competitor objection', 'Existing solution'], '{"confidence": 0.80}', NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '15 days'),

-- Processing analysis
('40000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', 'processing', NULL, NULL, ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], NULL, NULL, NULL, ARRAY[]::VARCHAR[], NULL, NULL, NOW() - INTERVAL '10 days', NOW() - INTERVAL '10 days'),

-- Pending analysis
('40000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', 'pending', NULL, NULL, ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], NULL, NULL, NULL, ARRAY[]::VARCHAR[], NULL, NULL, NOW() - INTERVAL '5 days', NULL),

-- Failed analysis
('40000000-0000-0000-0000-000000000008', '30000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', 'failed', NULL, NULL, ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], ARRAY[]::VARCHAR[], NULL, NULL, NULL, ARRAY[]::VARCHAR[], '{"error": "Audio quality too poor"}', NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days'),

-- Multiple objections
('40000000-0000-0000-0000-000000000011', '30000000-0000-0000-0000-000000000011', '11111111-1111-1111-1111-111111111111', 'completed', 'qualified', 'not_booked', ARRAY['price', 'pricing', 'cost'], ARRAY['The cost is still a concern for us', 'Pricing needs to be more competitive'], ARRAY['greeting', 'qualification', 'presentation', 'objection_handling'], ARRAY['close'], 80.0, 0.50, 'Follow-up call with continued pricing concerns. Multiple price-related objections raised.', ARRAY['Price objection', 'Follow-up call', 'Needs pricing adjustment'], '{"confidence": 0.88}', NULL, NOW() - INTERVAL '12 hours', NOW() - INTERVAL '12 hours');

-- ============================================================================
-- 7. APPOINTMENTS (All Outcomes)
-- ============================================================================
INSERT INTO appointments (id, company_id, lead_id, contact_card_id, scheduled_start, scheduled_end, location_address, outcome, assigned_rep_id, extra_metadata, created_at, updated_at) VALUES
('50000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', NOW() + INTERVAL '5 days', NOW() + INTERVAL '5 days' + INTERVAL '1 hour', '123 Business St, New York, NY 10001', 'pending', 'cccccccc-cccc-cccc-cccc-cccccccccccc', NULL, NOW() - INTERVAL '75 days', NOW() - INTERVAL '75 days'),
('50000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000008', '10000000-0000-0000-0000-000000000008', NOW() - INTERVAL '5 days', NOW() - INTERVAL '5 days' + INTERVAL '1 hour', '369 Cedar Ln, Austin, TX 73301', 'won', 'cccccccc-cccc-cccc-cccc-cccccccccccc', NULL, NOW() - INTERVAL '30 days', NOW() - INTERVAL '3 days'),
('50000000-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', '20000000-0000-0000-0000-000000000009', '10000000-0000-0000-0000-000000000009', NOW() - INTERVAL '2 days', NOW() - INTERVAL '2 days' + INTERVAL '1 hour', '741 Birch Way, Portland, OR 97201', 'lost', 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '1 day'),
('50000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000006', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day' + INTERVAL '1 hour', '147 Elm St, Denver, CO 80201', 'no_show', 'cccccccc-cccc-cccc-cccc-cccccccccccc', NULL, NOW() - INTERVAL '10 days', NOW() - INTERVAL '1 day'),
('50000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000007', '10000000-0000-0000-0000-000000000007', NOW() + INTERVAL '3 days', NOW() + INTERVAL '3 days' + INTERVAL '1 hour', '258 Maple Dr, Phoenix, AZ 85001', 'rescheduled', 'dddddddd-dddd-dddd-dddd-dddddddddddd', NULL, NOW() - INTERVAL '5 days', NOW() - INTERVAL '2 days');

-- ============================================================================
-- 8. INVITATIONS (All Statuses)
-- ============================================================================
INSERT INTO invitations (id, email, company_id, inviter_id, token, status, expires_at, created_at, accepted_at) VALUES
('60000000-0000-0000-0000-000000000001', 'newuser1@acme.com', '11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'token_pending_12345', 'pending', NOW() + INTERVAL '7 days', NOW() - INTERVAL '2 days', NULL),
('60000000-0000-0000-0000-000000000002', 'newuser2@acme.com', '11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'token_accepted_67890', 'accepted', NOW() - INTERVAL '5 days', NOW() - INTERVAL '10 days', NOW() - INTERVAL '5 days'),
('60000000-0000-0000-0000-000000000003', 'newuser3@global.com', '22222222-2222-2222-2222-222222222222', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'token_expired_abcde', 'expired', NOW() - INTERVAL '1 day', NOW() - INTERVAL '15 days', NULL);

-- ============================================================================
-- 9. PENDING ACTIONS (All Statuses, All Action Types)
-- ============================================================================
INSERT INTO pending_actions (id, company_id, lead_id, call_id, appointment_id, action_type, raw_text, status, due_at, priority, owner_id, source, extra_metadata, created_at, updated_at) VALUES
-- Pending actions
('70000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', NULL, 'follow_up', 'Follow up on pricing concerns', 'pending', NOW() + INTERVAL '2 days', 5, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'shunya', NULL, NOW() - INTERVAL '80 days', NULL),
('70000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000002', NULL, 'call_back', 'Call back to discuss competitor comparison', 'pending', NOW() + INTERVAL '1 day', 8, 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'shunya', NULL, NOW() - INTERVAL '55 days', NULL),
('70000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000004', NULL, 'send_quote', 'Send pricing quote to customer', 'pending', NOW() + INTERVAL '3 days', 6, NULL, 'shunya', NULL, NOW() - INTERVAL '25 days', NULL),

-- Completed actions
('70000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000003', NULL, 'follow_up', 'Follow up on timing objection', 'completed', NOW() - INTERVAL '10 days', 4, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'shunya', NULL, NOW() - INTERVAL '40 days', NOW() - INTERVAL '10 days'),
('70000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', NULL, '30000000-0000-0000-0000-000000000005', NULL, 'research_competitor', 'Research competitor solutions', 'completed', NOW() - INTERVAL '5 days', 7, 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'shunya', NULL, NOW() - INTERVAL '15 days', NOW() - INTERVAL '5 days'),

-- Cancelled actions
('70000000-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000006', NULL, 'call_back', 'Call back customer', 'cancelled', NULL, 3, 'ffffffff-ffff-ffff-ffff-ffffffffffff', 'shunya', NULL, NOW() - INTERVAL '10 days', NOW() - INTERVAL '8 days'),

-- Converted actions
('70000000-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000007', NULL, 'schedule_appointment', 'Schedule follow-up appointment', 'converted', NOW() - INTERVAL '2 days', 9, 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'shunya', NULL, NOW() - INTERVAL '5 days', NOW() - INTERVAL '2 days'),

-- Actions with appointments
('70000000-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', '20000000-0000-0000-0000-000000000001', NULL, '50000000-0000-0000-0000-000000000001', 'prepare_for_appointment', 'Prepare materials for upcoming appointment', 'pending', NOW() + INTERVAL '4 days', 8, 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'manual', NULL, NOW() - INTERVAL '75 days', NULL);

-- ============================================================================
-- 10. CALL PROCESSING JOBS (All Statuses: queued, running, completed, failed)
-- ============================================================================
INSERT INTO call_processing_jobs (id, company_id, call_id, shunya_job_id, status, progress_percent, current_step, steps_completed, steps_remaining, steps_failed, started_at, completed_at, failed_at, estimated_completion, duration_seconds, summary_url, chunks_url, transcript_url, retry_available, retry_attempt, original_job_id, skip_rag_indexing, skip_summary_generation, priority, job_metadata, error, extra_metadata, created_at, updated_at) VALUES
-- Queued job
('80000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '30000000-0000-0000-0000-000000000010', 'shunya_job_queued_001', 'queued', NULL, NULL, '[]'::JSON, '[]'::JSON, '[]'::JSON, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, false, 0, NULL, false, false, 'normal', NULL, NULL, NULL, NOW() - INTERVAL '1 day', NULL),

-- Running job
('80000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '30000000-0000-0000-0000-000000000011', 'shunya_job_running_002', 'running', 65, 'transcription', '["upload", "validation"]'::JSON, '["transcription", "analysis", "summarization"]'::JSON, '[]'::JSON, NOW() - INTERVAL '30 minutes', NULL, NULL, NOW() + INTERVAL '10 minutes', NULL, NULL, NULL, NULL, false, 0, NULL, false, false, 'normal', NULL, NULL, NULL, NOW() - INTERVAL '12 hours', NOW() - INTERVAL '30 minutes'),

-- Completed job
('80000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '30000000-0000-0000-0000-000000000001', 'shunya_job_completed_003', 'completed', 100, 'completed', '["upload", "validation", "transcription", "analysis", "summarization", "rag_indexing"]'::JSON, '[]'::JSON, '[]'::JSON, NOW() - INTERVAL '80 days', NOW() - INTERVAL '80 days' + INTERVAL '5 minutes', NULL, NULL, 300, 'https://storage.example.com/summaries/job003.json', 'https://storage.example.com/chunks/job003.json', 'https://storage.example.com/transcripts/job003.txt', false, 0, NULL, false, false, 'normal', '{"chunks_generated": 15, "summaries_generated": 1, "vectors_indexed": 15, "transcript_words": 450, "transcript_duration": 180}'::JSON, NULL, NULL, NOW() - INTERVAL '80 days', NOW() - INTERVAL '80 days' + INTERVAL '5 minutes'),

-- Failed job
('80000000-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '30000000-0000-0000-0000-000000000008', 'shunya_job_failed_004', 'failed', 20, 'transcription', '["upload", "validation"]'::JSON, '[]'::JSON, '["transcription"]'::JSON, NOW() - INTERVAL '3 days', NULL, NOW() - INTERVAL '3 days' + INTERVAL '2 minutes', NULL, 120, NULL, NULL, NULL, true, 0, NULL, false, false, 'normal', NULL, '{"code": "AUDIO_QUALITY_ERROR", "message": "Audio quality too poor for transcription"}'::JSON, NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '3 days' + INTERVAL '2 minutes'),

-- Retry job
('80000000-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '30000000-0000-0000-0000-000000000002', 'shunya_job_retry_005', 'completed', 100, 'completed', '["upload", "validation", "transcription", "analysis", "summarization"]'::JSON, '[]'::JSON, '[]'::JSON, NOW() - INTERVAL '55 days', NOW() - INTERVAL '55 days' + INTERVAL '6 minutes', NULL, NULL, 360, 'https://storage.example.com/summaries/job005.json', 'https://storage.example.com/chunks/job005.json', 'https://storage.example.com/transcripts/job005.txt', false, 1, 'shunya_job_failed_004', false, false, 'high', '{"chunks_generated": 20, "summaries_generated": 1, "vectors_indexed": 20, "transcript_words": 600, "transcript_duration": 240}'::JSON, NULL, NULL, NOW() - INTERVAL '55 days', NOW() - INTERVAL '55 days' + INTERVAL '6 minutes');

-- ============================================================================
-- 11. ASK OTTO CONVERSATIONS AND MESSAGES
-- ============================================================================
INSERT INTO ask_otto_conversations (id, company_id, user_id, shunya_conversation_id, title, context, extra_metadata, created_at, updated_at) VALUES
('90000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'shunya_conv_001', 'Sales Performance Questions', '{"lead_id": "20000000-0000-0000-0000-000000000001"}'::JSON, NULL, NOW() - INTERVAL '5 days', NOW() - INTERVAL '4 days'),
('90000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'dddddddd-dddd-dddd-dddd-dddddddddddd', 'shunya_conv_002', 'Objection Handling Help', NULL, NULL, NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day');

INSERT INTO ask_otto_messages (id, conversation_id, shunya_message_id, role, content, message_metadata, created_at) VALUES
('a0000000-0000-0000-0000-000000000001', '90000000-0000-0000-0000-000000000001', 'shunya_msg_001', 'user', 'What are the top objections this week?', NULL, NOW() - INTERVAL '5 days'),
('a0000000-0000-0000-0000-000000000002', '90000000-0000-0000-0000-000000000001', 'shunya_msg_002', 'assistant', 'The top objections this week are: 1. Price (40%), 2. Timing (25%), 3. Competitor (20%)', '{"sources": ["call_analyses"]}'::JSON, NOW() - INTERVAL '5 days' + INTERVAL '2 seconds'),
('a0000000-0000-0000-0000-000000000003', '90000000-0000-0000-0000-000000000001', 'shunya_msg_003', 'user', 'How can I handle price objections?', NULL, NOW() - INTERVAL '4 days'),
('a0000000-0000-0000-0000-000000000004', '90000000-0000-0000-0000-000000000001', 'shunya_msg_004', 'assistant', 'To handle price objections: 1. Emphasize value and ROI, 2. Offer flexible payment plans, 3. Compare to cost of not solving the problem', '{"sources": ["best_practices"]}'::JSON, NOW() - INTERVAL '4 days' + INTERVAL '3 seconds'),
('a0000000-0000-0000-0000-000000000005', '90000000-0000-0000-0000-000000000002', 'shunya_msg_005', 'user', 'What should I say when a customer says the price is too high?', NULL, NOW() - INTERVAL '2 days'),
('a0000000-0000-0000-0000-000000000006', '90000000-0000-0000-0000-000000000002', 'shunya_msg_006', 'assistant', 'When a customer says the price is too high, acknowledge their concern and reframe the conversation around value. Ask: "What would make this investment worthwhile for you?"', '{"sources": ["objection_handling_guide"]}'::JSON, NOW() - INTERVAL '2 days' + INTERVAL '2 seconds');

-- ============================================================================
-- 12. INSIGHT JOBS (All Statuses)
-- ============================================================================
INSERT INTO insight_jobs (id, company_id, shunya_job_id, week_start, week_end, company_ids, insight_types, status, force_regenerate, include_inactive_customers, started_at, completed_at, failed_at, results, error, extra_metadata, created_at, updated_at) VALUES
-- Queued job
('b0000000-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'insight_job_queued_001', CURRENT_DATE - INTERVAL '7 days', CURRENT_DATE, ARRAY['11111111-1111-1111-1111-111111111111'], ARRAY['company', 'objection'], 'queued', false, false, NULL, NULL, NULL, NULL, NULL, NULL, NOW() - INTERVAL '1 day', NULL),

-- Running job
('b0000000-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'insight_job_running_002', CURRENT_DATE - INTERVAL '14 days', CURRENT_DATE - INTERVAL '7 days', ARRAY['11111111-1111-1111-1111-111111111111'], ARRAY['company', 'customer', 'objection'], 'running', false, false, NOW() - INTERVAL '2 hours', NULL, NULL, NULL, NULL, NULL, NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 hours'),

-- Completed job
('b0000000-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'insight_job_completed_003', CURRENT_DATE - INTERVAL '21 days', CURRENT_DATE - INTERVAL '14 days', ARRAY['11111111-1111-1111-1111-111111111111'], ARRAY['company', 'objection'], 'completed', false, false, NOW() - INTERVAL '30 days', NOW() - INTERVAL '30 days' + INTERVAL '10 minutes', NULL, '{"insights": [{"type": "objection", "data": {"top_objections": ["price", "timing", "competitor"]}}, {"type": "company", "data": {"trends": "positive"}}]}'::JSON, NULL, NULL, NOW() - INTERVAL '30 days', NOW() - INTERVAL '30 days' + INTERVAL '10 minutes'),

-- Failed job
('b0000000-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'insight_job_failed_004', CURRENT_DATE - INTERVAL '28 days', CURRENT_DATE - INTERVAL '21 days', ARRAY['22222222-2222-2222-2222-222222222222'], ARRAY['company'], 'failed', true, false, NOW() - INTERVAL '20 days', NULL, NOW() - INTERVAL '20 days' + INTERVAL '5 minutes', NULL, '{"code": "INSUFFICIENT_DATA", "message": "Not enough data for the specified time range"}'::JSON, NULL, NOW() - INTERVAL '20 days', NOW() - INTERVAL '20 days' + INTERVAL '5 minutes');

-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Data inserted:
-- - 3 Companies
-- - 8 Users (2 executives, 3 sales reps, 2 CSRs, 1 inactive)
-- - 10 Contact Cards
-- - 10 Leads (3 qualified, 2 new, 2 warm/hot, 2 closed, 1 nurturing)
-- - 11 Calls (7 sales, 2 CSR, 2 missed, various with/without transcripts)
-- - 9 Call Analyses (5 completed with various objections, 1 processing, 1 pending, 1 failed)
-- - 5 Appointments (1 pending, 1 won, 1 lost, 1 no_show, 1 rescheduled)
-- - 3 Invitations (1 pending, 1 accepted, 1 expired)
-- - 8 Pending Actions (4 pending, 2 completed, 1 cancelled, 1 converted)
-- - 5 Call Processing Jobs (1 queued, 1 running, 2 completed, 1 failed)
-- - 2 Ask Otto Conversations with 6 Messages
-- - 4 Insight Jobs (1 queued, 1 running, 1 completed, 1 failed)
-- ============================================================================
022