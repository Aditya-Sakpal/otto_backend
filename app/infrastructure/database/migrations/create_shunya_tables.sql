-- ============================================================================
-- Migration: Create Shunya Integration Tables
-- ============================================================================
-- Creates tables for Shunya API integration:
-- - call_processing_jobs: Tracks call processing jobs
-- - ask_otto_conversations: Tracks Ask Otto conversations
-- - ask_otto_messages: Tracks Ask Otto messages
-- - insight_jobs: Tracks insight generation jobs
-- ============================================================================

-- Enable UUID extension if not already enabled
-- Note: Extension name needs to be quoted
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp') THEN
        CREATE EXTENSION "uuid-ossp";
    END IF;
END $$;

-- ============================================================================
-- TABLE: call_processing_jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS call_processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    shunya_job_id VARCHAR NOT NULL UNIQUE,
    
    -- Job status
    status VARCHAR NOT NULL DEFAULT 'queued',
    
    -- Progress tracking
    progress_percent INTEGER,
    current_step VARCHAR,
    steps_completed JSONB DEFAULT '[]',
    steps_remaining JSONB DEFAULT '[]',
    steps_failed JSONB DEFAULT '[]',
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    estimated_completion TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,
    
    -- Results URLs
    summary_url TEXT,
    chunks_url TEXT,
    transcript_url TEXT,
    
    -- Job metadata
    job_metadata JSONB,
    
    -- Error handling
    error JSONB,
    retry_available BOOLEAN DEFAULT FALSE,
    retry_attempt INTEGER DEFAULT 0,
    original_job_id VARCHAR,
    
    -- Options
    skip_rag_indexing BOOLEAN DEFAULT FALSE,
    skip_summary_generation BOOLEAN DEFAULT FALSE,
    priority VARCHAR DEFAULT 'normal',
    
    extra_metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for call_processing_jobs
CREATE INDEX IF NOT EXISTS idx_call_processing_jobs_company_id ON call_processing_jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_call_processing_jobs_call_id ON call_processing_jobs(call_id);
CREATE INDEX IF NOT EXISTS idx_call_processing_jobs_shunya_job_id ON call_processing_jobs(shunya_job_id);
CREATE INDEX IF NOT EXISTS idx_call_processing_jobs_status ON call_processing_jobs(status);

-- ============================================================================
-- TABLE: ask_otto_conversations
-- ============================================================================
CREATE TABLE IF NOT EXISTS ask_otto_conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    shunya_conversation_id VARCHAR UNIQUE,
    
    -- Conversation metadata
    title VARCHAR,
    context JSONB,
    
    extra_metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for ask_otto_conversations
CREATE INDEX IF NOT EXISTS idx_ask_otto_conversations_company_id ON ask_otto_conversations(company_id);
CREATE INDEX IF NOT EXISTS idx_ask_otto_conversations_user_id ON ask_otto_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_ask_otto_conversations_shunya_id ON ask_otto_conversations(shunya_conversation_id);

-- ============================================================================
-- TABLE: ask_otto_messages
-- ============================================================================
CREATE TABLE IF NOT EXISTS ask_otto_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES ask_otto_conversations(id) ON DELETE CASCADE,
    shunya_message_id VARCHAR UNIQUE,
    
    -- Message content
    role VARCHAR NOT NULL,  -- user, assistant
    content TEXT NOT NULL,
    
    -- Message metadata
    message_metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for ask_otto_messages
CREATE INDEX IF NOT EXISTS idx_ask_otto_messages_conversation_id ON ask_otto_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_ask_otto_messages_shunya_id ON ask_otto_messages(shunya_message_id);
CREATE INDEX IF NOT EXISTS idx_ask_otto_messages_role ON ask_otto_messages(role);

-- ============================================================================
-- TABLE: insight_jobs
-- ============================================================================
CREATE TABLE IF NOT EXISTS insight_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    shunya_job_id VARCHAR NOT NULL UNIQUE,
    
    -- Job parameters
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    company_ids VARCHAR[] DEFAULT '{}',
    insight_types VARCHAR[] DEFAULT '{}',
    
    -- Job status
    status VARCHAR NOT NULL DEFAULT 'queued',
    
    -- Options
    force_regenerate BOOLEAN DEFAULT FALSE,
    include_inactive_customers BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    
    -- Results
    results JSONB,
    error JSONB,
    
    extra_metadata JSONB,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for insight_jobs
CREATE INDEX IF NOT EXISTS idx_insight_jobs_company_id ON insight_jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_insight_jobs_shunya_job_id ON insight_jobs(shunya_job_id);
CREATE INDEX IF NOT EXISTS idx_insight_jobs_status ON insight_jobs(status);
CREATE INDEX IF NOT EXISTS idx_insight_jobs_week_range ON insight_jobs(week_start, week_end);
