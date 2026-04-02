-- ============================================================================
-- Otto AI Backend Database Schema
-- PostgreSQL Database Creation Script
-- ============================================================================
-- This script creates the complete database schema for the Otto AI Backend.
-- It includes all tables, columns, indexes, constraints, and relationships.
--
-- Usage:
--   psql -U postgres -d otto_db -f database_schema.sql
--   Or connect to your database and run this script
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- TABLE: companies
-- ============================================================================
-- Companies/tenants in the system
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR NOT NULL,
    phone_number VARCHAR,
    address TEXT,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for companies
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);

-- ============================================================================
-- TABLE: users
-- ============================================================================
-- User accounts with authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR NOT NULL UNIQUE,
    password_hash VARCHAR,
    role VARCHAR(50) NOT NULL DEFAULT 'sales_rep',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    first_name VARCHAR,
    last_name VARCHAR,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for users
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- ============================================================================
-- TABLE: contact_cards
-- ============================================================================
-- Contact information for leads/customers
CREATE TABLE IF NOT EXISTS contact_cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    primary_phone VARCHAR NOT NULL,
    secondary_phone VARCHAR,
    email VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    address TEXT,
    city VARCHAR,
    state VARCHAR,
    postal_code VARCHAR,
    property_snapshot JSONB,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for contact_cards
CREATE INDEX IF NOT EXISTS idx_contact_cards_company_id ON contact_cards(company_id);
CREATE INDEX IF NOT EXISTS idx_contact_cards_primary_phone ON contact_cards(primary_phone);
CREATE INDEX IF NOT EXISTS idx_contact_cards_email ON contact_cards(email);

-- ============================================================================
-- TABLE: leads
-- ============================================================================
-- Sales leads/opportunities
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    contact_card_id UUID NOT NULL REFERENCES contact_cards(id) ON DELETE CASCADE,
    status VARCHAR NOT NULL DEFAULT 'new',
    deal_status VARCHAR,
    pipeline_stage VARCHAR,
    assigned_rep_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deal_size DOUBLE PRECISION,
    closed_at TIMESTAMP WITH TIME ZONE,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for leads
CREATE INDEX IF NOT EXISTS idx_leads_company_id ON leads(company_id);
CREATE INDEX IF NOT EXISTS idx_leads_contact_card_id ON leads(contact_card_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_assigned_rep_id ON leads(assigned_rep_id);
CREATE INDEX IF NOT EXISTS idx_leads_deal_status ON leads(deal_status);
CREATE INDEX IF NOT EXISTS idx_leads_pipeline_stage ON leads(pipeline_stage);

-- ============================================================================
-- TABLE: calls
-- ============================================================================
-- Phone call records from telephony providers
CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    contact_card_id UUID REFERENCES contact_cards(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    phone_number VARCHAR NOT NULL,
    call_type VARCHAR,
    missed_call BOOLEAN NOT NULL DEFAULT FALSE,
    transcript TEXT,
    audio_url TEXT,
    duration_seconds INTEGER,
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for calls
CREATE INDEX IF NOT EXISTS idx_calls_company_id ON calls(company_id);
CREATE INDEX IF NOT EXISTS idx_calls_contact_card_id ON calls(contact_card_id);
CREATE INDEX IF NOT EXISTS idx_calls_lead_id ON calls(lead_id);
CREATE INDEX IF NOT EXISTS idx_calls_phone_number ON calls(phone_number);
CREATE INDEX IF NOT EXISTS idx_calls_owner_id ON calls(owner_id);
CREATE INDEX IF NOT EXISTS idx_calls_call_type ON calls(call_type);
CREATE INDEX IF NOT EXISTS idx_calls_missed_call ON calls(missed_call);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at);

-- ============================================================================
-- TABLE: call_analyses
-- ============================================================================
-- AI analysis results for calls
CREATE TABLE IF NOT EXISTS call_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID NOT NULL UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    status VARCHAR NOT NULL DEFAULT 'pending',
    
    -- Qualification
    qualification_status VARCHAR,
    booking_status VARCHAR,
    
    -- Objections
    objections VARCHAR[] DEFAULT ARRAY[]::VARCHAR[],
    objection_texts VARCHAR[] DEFAULT ARRAY[]::VARCHAR[],
    
    -- SOP Compliance
    sop_stages_completed VARCHAR[] DEFAULT ARRAY[]::VARCHAR[],
    sop_stages_missed VARCHAR[] DEFAULT ARRAY[]::VARCHAR[],
    sop_compliance_score DOUBLE PRECISION,
    
    -- Sentiment
    sentiment_score DOUBLE PRECISION,
    
    -- Summary
    summary TEXT,
    key_points VARCHAR[] DEFAULT ARRAY[]::VARCHAR[],
    
    -- Raw analysis data
    raw_analysis JSONB,
    extra_metadata JSONB,
    
    -- Pending actions (JSON strings stored as text array)
    pending_actions TEXT[] DEFAULT ARRAY[]::TEXT[],
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for call_analyses
CREATE INDEX IF NOT EXISTS idx_call_analyses_call_id ON call_analyses(call_id);
CREATE INDEX IF NOT EXISTS idx_call_analyses_company_id ON call_analyses(company_id);
CREATE INDEX IF NOT EXISTS idx_call_analyses_status ON call_analyses(status);
CREATE INDEX IF NOT EXISTS idx_call_analyses_qualification_status ON call_analyses(qualification_status);
CREATE INDEX IF NOT EXISTS idx_call_analyses_booking_status ON call_analyses(booking_status);
CREATE INDEX IF NOT EXISTS idx_call_analyses_objections_gin ON call_analyses USING GIN(objections);

-- ============================================================================
-- TABLE: appointments
-- ============================================================================
-- Scheduled appointments
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    contact_card_id UUID NOT NULL REFERENCES contact_cards(id) ON DELETE CASCADE,
    scheduled_start TIMESTAMP WITH TIME ZONE NOT NULL,
    scheduled_end TIMESTAMP WITH TIME ZONE,
    location_address TEXT,
    outcome VARCHAR,
    assigned_rep_id UUID REFERENCES users(id) ON DELETE SET NULL,
    extra_metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for appointments
CREATE INDEX IF NOT EXISTS idx_appointments_company_id ON appointments(company_id);
CREATE INDEX IF NOT EXISTS idx_appointments_lead_id ON appointments(lead_id);
CREATE INDEX IF NOT EXISTS idx_appointments_contact_card_id ON appointments(contact_card_id);
CREATE INDEX IF NOT EXISTS idx_appointments_scheduled_start ON appointments(scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appointments_assigned_rep_id ON appointments(assigned_rep_id);
CREATE INDEX IF NOT EXISTS idx_appointments_outcome ON appointments(outcome);

-- ============================================================================
-- COMMENTS
-- ============================================================================
-- Add table comments for documentation
COMMENT ON TABLE companies IS 'Companies/tenants in the system';
COMMENT ON TABLE users IS 'User accounts with authentication and authorization';
COMMENT ON TABLE contact_cards IS 'Contact information for leads and customers';
COMMENT ON TABLE leads IS 'Sales leads and opportunities in the pipeline';
COMMENT ON TABLE calls IS 'Phone call records from telephony providers (CallRail, Twilio)';
COMMENT ON TABLE call_analyses IS 'AI analysis results for calls including objections, SOP compliance, sentiment';
COMMENT ON TABLE appointments IS 'Scheduled appointments for leads';

-- Add column comments for key fields
COMMENT ON COLUMN users.role IS 'User role: csr, sales_rep, executive';
COMMENT ON COLUMN users.company_id IS 'Associated company/tenant (nullable for system users)';
COMMENT ON COLUMN leads.status IS 'Lead status: new, warm, hot, qualified_booked, qualified_unbooked, etc.';
COMMENT ON COLUMN leads.deal_status IS 'Deal status: new, nurturing, booked, in_progress, won, lost';
COMMENT ON COLUMN leads.pipeline_stage IS 'Pipeline stage: qualified, unqualified, service_not_offered, booked, appointment_ran, won, lost, review';
COMMENT ON COLUMN calls.call_type IS 'Type of call: csr_call, sales_call, missed_call';
COMMENT ON COLUMN call_analyses.status IS 'Analysis status: pending, processing, completed, failed';
COMMENT ON COLUMN call_analyses.objections IS 'Array of objection types: price, timing, authority, need, competitor, other';
COMMENT ON COLUMN call_analyses.sop_stages_completed IS 'Array of completed SOP stages: greeting, qualification, presentation, objection_handling, close, follow_up';
COMMENT ON COLUMN call_analyses.sop_stages_missed IS 'Array of missed SOP stages';
COMMENT ON COLUMN call_analyses.sop_compliance_score IS 'SOP compliance score (0.0 to 1.0)';
COMMENT ON COLUMN call_analyses.sentiment_score IS 'Sentiment score (-1.0 to 1.0, negative to positive)';
COMMENT ON COLUMN call_analyses.pending_actions IS 'Array of pending action JSON objects with type, owner, due_at, raw_text, confidence, contact_method';

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

