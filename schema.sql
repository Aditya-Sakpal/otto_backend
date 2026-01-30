--
-- PostgreSQL database dump
--

\restrict D19LZbGB8yyCU2lF6pnRT9IWrlATVWOyrgb6cRPv9CkP87fbMLwV0WnSt2Nf2eU

-- Dumped from database version 17.6
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: appointments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appointments (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    lead_id uuid NOT NULL,
    contact_card_id uuid NOT NULL,
    scheduled_start timestamp with time zone NOT NULL,
    scheduled_end timestamp with time zone,
    location_address text,
    outcome character varying,
    assigned_rep_id uuid,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    interaction_id uuid
);


--
-- Name: COLUMN appointments.interaction_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.appointments.interaction_id IS 'Directly points to the Call record once recording starts. This is the single source of truth for whether a meeting has AI data.';


--
-- Name: ask_otto_conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ask_otto_conversations (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    user_id uuid,
    shunya_conversation_id character varying,
    title character varying,
    context json,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: ask_otto_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ask_otto_messages (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    shunya_message_id character varying,
    role character varying NOT NULL,
    content text NOT NULL,
    message_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: call_analyses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_analyses (
    id uuid NOT NULL,
    call_id uuid NOT NULL,
    company_id uuid NOT NULL,
    status character varying NOT NULL,
    qualification_status character varying,
    booking_status character varying,
    objections character varying[] NOT NULL,
    objection_texts character varying[] NOT NULL,
    sop_stages_completed character varying[] NOT NULL,
    sop_stages_missed character varying[] NOT NULL,
    sop_compliance_score double precision,
    sentiment_score double precision,
    summary text,
    key_points character varying[] NOT NULL,
    raw_analysis json,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    action_items text[] DEFAULT '{}'::text[],
    next_steps text[] DEFAULT '{}'::text[],
    pending_actions jsonb DEFAULT '[]'::jsonb,
    summary_confidence_score double precision,
    sop_compliance_issues text[] DEFAULT '{}'::text[],
    sop_compliance_positive_behaviors text[] DEFAULT '{}'::text[],
    sop_compliance_confidence double precision,
    sop_compliance_rate double precision,
    sop_stages_total integer,
    objections_total_count integer DEFAULT 0,
    bant_need_score double precision,
    bant_budget_score double precision,
    bant_timeline_score double precision,
    bant_authority_score double precision,
    qualification_overall_score double precision,
    call_outcome_category character varying(100),
    appointment_confirmed boolean DEFAULT false,
    appointment_date timestamp with time zone,
    appointment_type character varying(50),
    appointment_timezone character varying(50),
    appointment_time_confidence double precision,
    preferred_time_window character varying(100),
    appointment_intent character varying(50),
    original_appointment_datetime timestamp with time zone,
    new_requested_time timestamp with time zone,
    service_requested text,
    service_not_offered_reason text,
    service_address_raw text,
    service_address_structured jsonb,
    address_confidence double precision,
    customer_name character varying(255),
    customer_name_confidence double precision,
    decision_makers text[] DEFAULT '{}'::text[],
    urgency_signals text[] DEFAULT '{}'::text[],
    budget_indicators text[] DEFAULT '{}'::text[],
    follow_up_required boolean DEFAULT false,
    follow_up_reason text,
    qualification_confidence_score double precision,
    compliance_target_role character varying(50),
    detected_call_type character varying(50),
    is_existing_customer boolean,
    is_deprioritized boolean,
    service_wait_time_weeks integer,
    applied_rules text[] DEFAULT '{}'::text[],
    property_details jsonb,
    customer_details jsonb
);


--
-- Name: COLUMN call_analyses.action_items; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.action_items IS 'Action items extracted from call summary';


--
-- Name: COLUMN call_analyses.next_steps; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.next_steps IS 'Next steps identified in call summary';


--
-- Name: COLUMN call_analyses.pending_actions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.pending_actions IS 'Pending actions with details: type, owner, due_at, raw_text, confidence, contact_method';


--
-- Name: COLUMN call_analyses.summary_confidence_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.summary_confidence_score IS 'Confidence score for the summary (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.sop_compliance_issues; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.sop_compliance_issues IS 'List of SOP compliance issues identified';


--
-- Name: COLUMN call_analyses.sop_compliance_positive_behaviors; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.sop_compliance_positive_behaviors IS 'List of positive behaviors observed during call';


--
-- Name: COLUMN call_analyses.sop_compliance_confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.sop_compliance_confidence IS 'Confidence score for SOP compliance evaluation (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.sop_compliance_rate; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.sop_compliance_rate IS 'SOP compliance rate (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.sop_stages_total; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.sop_stages_total IS 'Total number of SOP stages evaluated';


--
-- Name: COLUMN call_analyses.objections_total_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.objections_total_count IS 'Total number of objections detected';


--
-- Name: COLUMN call_analyses.bant_need_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.bant_need_score IS 'BANT Need score (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.bant_budget_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.bant_budget_score IS 'BANT Budget score (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.bant_timeline_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.bant_timeline_score IS 'BANT Timeline score (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.bant_authority_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.bant_authority_score IS 'BANT Authority score (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.qualification_overall_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.qualification_overall_score IS 'Overall qualification score (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.call_outcome_category; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.call_outcome_category IS 'Call outcome category (e.g., qualified_but_unbooked, qualified_and_booked)';


--
-- Name: COLUMN call_analyses.appointment_confirmed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_confirmed IS 'Whether appointment was confirmed during call';


--
-- Name: COLUMN call_analyses.appointment_date; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_date IS 'Scheduled appointment date and time';


--
-- Name: COLUMN call_analyses.appointment_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_type IS 'Appointment type (e.g., in-person, virtual, phone)';


--
-- Name: COLUMN call_analyses.appointment_timezone; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_timezone IS 'Timezone for appointment (e.g., UTC, America/New_York)';


--
-- Name: COLUMN call_analyses.appointment_time_confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_time_confidence IS 'Confidence score for appointment time extraction (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.preferred_time_window; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.preferred_time_window IS 'Preferred time window for appointment (e.g., morning, afternoon, evening)';


--
-- Name: COLUMN call_analyses.appointment_intent; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.appointment_intent IS 'Appointment intent (e.g., new, reschedule, cancel)';


--
-- Name: COLUMN call_analyses.original_appointment_datetime; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.original_appointment_datetime IS 'Original appointment datetime (for rescheduled appointments)';


--
-- Name: COLUMN call_analyses.new_requested_time; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.new_requested_time IS 'New requested appointment time (for rescheduled appointments)';


--
-- Name: COLUMN call_analyses.service_requested; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.service_requested IS 'Service requested by customer';


--
-- Name: COLUMN call_analyses.service_not_offered_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.service_not_offered_reason IS 'Reason if service was not offered';


--
-- Name: COLUMN call_analyses.service_address_raw; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.service_address_raw IS 'Raw service address as mentioned in call';


--
-- Name: COLUMN call_analyses.service_address_structured; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.service_address_structured IS 'Structured service address: {line1, city, state, postal_code, country}';


--
-- Name: COLUMN call_analyses.address_confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.address_confidence IS 'Confidence score for address extraction (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.customer_name; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.customer_name IS 'Customer name extracted from call';


--
-- Name: COLUMN call_analyses.customer_name_confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.customer_name_confidence IS 'Confidence score for customer name extraction (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.decision_makers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.decision_makers IS 'List of decision makers identified (e.g., ["John Smith (homeowner)"])';


--
-- Name: COLUMN call_analyses.urgency_signals; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.urgency_signals IS 'Urgency signals detected in call (quotes or phrases indicating urgency)';


--
-- Name: COLUMN call_analyses.budget_indicators; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.budget_indicators IS 'Budget indicators detected in call (quotes or phrases indicating budget)';


--
-- Name: COLUMN call_analyses.follow_up_required; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.follow_up_required IS 'Whether follow-up is required';


--
-- Name: COLUMN call_analyses.follow_up_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.follow_up_reason IS 'Reason why follow-up is required';


--
-- Name: COLUMN call_analyses.qualification_confidence_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.qualification_confidence_score IS 'Confidence score for qualification assessment (0.0 to 1.0)';


--
-- Name: COLUMN call_analyses.compliance_target_role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.compliance_target_role IS 'The role this call was evaluated against (e.g., customer_rep, sales_rep)';


--
-- Name: COLUMN call_analyses.detected_call_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.detected_call_type IS 'Type of call: fresh_sales, follow_up_inquiry, existing_customer_service';


--
-- Name: COLUMN call_analyses.is_existing_customer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.is_existing_customer IS 'Whether this is an existing customer';


--
-- Name: COLUMN call_analyses.is_deprioritized; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.is_deprioritized IS 'Whether service is deprioritized per tenant rules';


--
-- Name: COLUMN call_analyses.service_wait_time_weeks; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.service_wait_time_weeks IS 'Wait time in weeks if service is deferred';


--
-- Name: COLUMN call_analyses.applied_rules; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.applied_rules IS 'Tenant-specific rules that were applied';


--
-- Name: COLUMN call_analyses.property_details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.property_details IS 'Home services property information (roof_type, roof_age_years, stories, hoa_status, etc.)';


--
-- Name: COLUMN call_analyses.customer_details; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.call_analyses.customer_details IS 'Customer details with address, phone, email, decision_makers';


--
-- Name: call_processing_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_processing_jobs (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    call_id uuid NOT NULL,
    shunya_job_id character varying NOT NULL,
    status character varying NOT NULL,
    progress_percent integer,
    current_step character varying,
    steps_completed json NOT NULL,
    steps_remaining json NOT NULL,
    steps_failed json NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    failed_at timestamp with time zone,
    estimated_completion timestamp with time zone,
    duration_seconds integer,
    summary_url text,
    chunks_url text,
    transcript_url text,
    job_metadata json,
    error json,
    retry_available boolean NOT NULL,
    retry_attempt integer NOT NULL,
    original_job_id character varying,
    skip_rag_indexing boolean NOT NULL,
    skip_summary_generation boolean NOT NULL,
    priority character varying NOT NULL,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.calls (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    contact_card_id uuid,
    lead_id uuid,
    phone_number character varying NOT NULL,
    call_type character varying,
    missed_call boolean NOT NULL,
    transcript text,
    audio_url text,
    duration_seconds integer,
    handled_by_user_id uuid,
    interaction_type character varying,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone,
    answered_at timestamp with time zone,
    status character varying DEFAULT 'pending'::character varying,
    shunya_job_id character varying
);


--
-- Name: COLUMN calls.answered_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calls.answered_at IS 'Timestamp when the call was answered. Used to calculate response time.';


--
-- Name: COLUMN calls.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calls.status IS 'Tracks call processing status: pending, processing, completed, or failed.';


--
-- Name: COLUMN calls.shunya_job_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.calls.shunya_job_id IS 'Stores the ID returned by Shunya Labs for tracking call processing jobs.';


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id uuid NOT NULL,
    name character varying NOT NULL,
    phone_number character varying,
    address text,
    extra_metadata json,
    reference_doc_url text,
    sop_doc_url text,
    csr_sop_doc_url text,
    sales_sop_doc_url text
);


--
-- Name: company_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_integrations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    location_id character varying,
    crm_provider character varying,
    crm_api_encrypted_key character varying,
    crm_company_id character varying,
    voip_provider character varying,
    voip_api_encrypted_key character varying,
    voip_company_id character varying,
    extra_metadata json
);


--
-- Name: TABLE company_integrations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.company_integrations IS 'Stores encrypted credentials and document links for company-level integrations.';


--
-- Name: COLUMN company_integrations.location_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.location_id IS 'GHL location ID (optional)';


--
-- Name: COLUMN company_integrations.crm_provider; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.crm_provider IS 'CRM provider name (optional)';


--
-- Name: COLUMN company_integrations.crm_api_encrypted_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.crm_api_encrypted_key IS 'Encrypted CRM API key (optional)';


--
-- Name: COLUMN company_integrations.crm_company_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.crm_company_id IS 'CRM company ID (optional)';


--
-- Name: COLUMN company_integrations.voip_provider; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.voip_provider IS 'VoIP provider name (optional)';


--
-- Name: COLUMN company_integrations.voip_api_encrypted_key; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.voip_api_encrypted_key IS 'Encrypted VoIP API key (optional)';


--
-- Name: COLUMN company_integrations.voip_company_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.company_integrations.voip_company_id IS 'VoIP company ID (optional)';


--
-- Name: contact_cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contact_cards (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    primary_phone character varying NOT NULL,
    secondary_phone character varying,
    email character varying,
    first_name character varying,
    last_name character varying,
    address text,
    city character varying,
    state character varying,
    postal_code character varying,
    property_snapshot json,
    extra_metadata json
);


--
-- Name: insight_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.insight_jobs (
    id uuid NOT NULL,
    company_id uuid,
    shunya_job_id character varying NOT NULL,
    week_start date NOT NULL,
    week_end date NOT NULL,
    company_ids character varying[] NOT NULL,
    insight_types character varying[] NOT NULL,
    status character varying NOT NULL,
    force_regenerate boolean NOT NULL,
    include_inactive_customers boolean NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    failed_at timestamp with time zone,
    results json,
    error json,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invitations (
    id uuid NOT NULL,
    email character varying NOT NULL,
    company_id uuid NOT NULL,
    inviter_id uuid NOT NULL,
    token character varying NOT NULL,
    status character varying(50) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    accepted_at timestamp with time zone,
    role character varying(50) DEFAULT 'csr'::character varying NOT NULL
);


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    contact_card_id uuid NOT NULL,
    status character varying NOT NULL,
    deal_status character varying,
    assigned_rep_id uuid,
    deal_size double precision,
    closed_at timestamp with time zone,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: pending_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_actions (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    lead_id uuid,
    call_id uuid,
    appointment_id uuid,
    action_type character varying NOT NULL,
    raw_text text,
    status character varying NOT NULL,
    due_at timestamp with time zone,
    priority integer,
    owner_id uuid,
    source character varying NOT NULL,
    extra_metadata json,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying NOT NULL,
    password_hash character varying,
    role character varying(50) NOT NULL,
    is_active boolean NOT NULL,
    first_name character varying,
    last_name character varying,
    company_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    extra_metadata json
);


--
-- Name: appointments appointments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_pkey PRIMARY KEY (id);


--
-- Name: ask_otto_conversations ask_otto_conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ask_otto_conversations
    ADD CONSTRAINT ask_otto_conversations_pkey PRIMARY KEY (id);


--
-- Name: ask_otto_messages ask_otto_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ask_otto_messages
    ADD CONSTRAINT ask_otto_messages_pkey PRIMARY KEY (id);


--
-- Name: call_analyses call_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_analyses
    ADD CONSTRAINT call_analyses_pkey PRIMARY KEY (id);


--
-- Name: call_processing_jobs call_processing_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_processing_jobs
    ADD CONSTRAINT call_processing_jobs_pkey PRIMARY KEY (id);


--
-- Name: calls calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_pkey PRIMARY KEY (id);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: company_integrations company_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_integrations
    ADD CONSTRAINT company_integrations_pkey PRIMARY KEY (id);


--
-- Name: contact_cards contact_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_cards
    ADD CONSTRAINT contact_cards_pkey PRIMARY KEY (id);


--
-- Name: insight_jobs insight_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insight_jobs
    ADD CONSTRAINT insight_jobs_pkey PRIMARY KEY (id);


--
-- Name: invitations invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: pending_actions pending_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_appointments_interaction_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_appointments_interaction_id ON public.appointments USING btree (interaction_id);


--
-- Name: idx_call_analyses_appointment_confirmed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_appointment_confirmed ON public.call_analyses USING btree (appointment_confirmed) WHERE (appointment_confirmed = true);


--
-- Name: idx_call_analyses_appointment_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_appointment_date ON public.call_analyses USING btree (appointment_date) WHERE (appointment_date IS NOT NULL);


--
-- Name: idx_call_analyses_compliance_target_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_compliance_target_role ON public.call_analyses USING btree (compliance_target_role);


--
-- Name: idx_call_analyses_detected_call_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_detected_call_type ON public.call_analyses USING btree (detected_call_type);


--
-- Name: idx_call_analyses_follow_up_required; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_follow_up_required ON public.call_analyses USING btree (follow_up_required) WHERE (follow_up_required = true);


--
-- Name: idx_call_analyses_is_deprioritized; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_is_deprioritized ON public.call_analyses USING btree (is_deprioritized);


--
-- Name: idx_call_analyses_is_existing_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_is_existing_customer ON public.call_analyses USING btree (is_existing_customer);


--
-- Name: idx_call_analyses_outcome_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_outcome_category ON public.call_analyses USING btree (call_outcome_category) WHERE (call_outcome_category IS NOT NULL);


--
-- Name: idx_call_analyses_qualification_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_analyses_qualification_score ON public.call_analyses USING btree (qualification_overall_score) WHERE (qualification_overall_score IS NOT NULL);


--
-- Name: idx_calls_answered_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_calls_answered_at ON public.calls USING btree (answered_at);


--
-- Name: idx_calls_shunya_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_calls_shunya_job_id ON public.calls USING btree (shunya_job_id);


--
-- Name: idx_calls_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_calls_status ON public.calls USING btree (status);


--
-- Name: idx_invitations_email_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_email_status ON public.invitations USING btree (email, status);


--
-- Name: idx_invitations_token_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_token_status ON public.invitations USING btree (token, status);


--
-- Name: idx_pending_actions_company_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_actions_company_status ON public.pending_actions USING btree (company_id, status);


--
-- Name: idx_pending_actions_due_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_actions_due_at ON public.pending_actions USING btree (due_at);


--
-- Name: idx_pending_actions_lead_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_actions_lead_status ON public.pending_actions USING btree (lead_id, status);


--
-- Name: idx_pending_actions_owner_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_actions_owner_status ON public.pending_actions USING btree (owner_id, status);


--
-- Name: idx_pending_actions_urgency; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pending_actions_urgency ON public.pending_actions USING btree (due_at, priority);


--
-- Name: ix_appointments_assigned_rep_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_assigned_rep_id ON public.appointments USING btree (assigned_rep_id);


--
-- Name: ix_appointments_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_company_id ON public.appointments USING btree (company_id);


--
-- Name: ix_appointments_contact_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_contact_card_id ON public.appointments USING btree (contact_card_id);


--
-- Name: ix_appointments_lead_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_lead_id ON public.appointments USING btree (lead_id);


--
-- Name: ix_appointments_scheduled_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appointments_scheduled_start ON public.appointments USING btree (scheduled_start);


--
-- Name: ix_ask_otto_conversations_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ask_otto_conversations_company_id ON public.ask_otto_conversations USING btree (company_id);


--
-- Name: ix_ask_otto_conversations_shunya_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_ask_otto_conversations_shunya_conversation_id ON public.ask_otto_conversations USING btree (shunya_conversation_id);


--
-- Name: ix_ask_otto_conversations_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ask_otto_conversations_user_id ON public.ask_otto_conversations USING btree (user_id);


--
-- Name: ix_ask_otto_messages_conversation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ask_otto_messages_conversation_id ON public.ask_otto_messages USING btree (conversation_id);


--
-- Name: ix_ask_otto_messages_shunya_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_ask_otto_messages_shunya_message_id ON public.ask_otto_messages USING btree (shunya_message_id);


--
-- Name: ix_call_analyses_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_call_analyses_call_id ON public.call_analyses USING btree (call_id);


--
-- Name: ix_call_analyses_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_analyses_company_id ON public.call_analyses USING btree (company_id);


--
-- Name: ix_call_analyses_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_analyses_status ON public.call_analyses USING btree (status);


--
-- Name: ix_call_processing_jobs_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_processing_jobs_call_id ON public.call_processing_jobs USING btree (call_id);


--
-- Name: ix_call_processing_jobs_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_processing_jobs_company_id ON public.call_processing_jobs USING btree (company_id);


--
-- Name: ix_call_processing_jobs_shunya_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_call_processing_jobs_shunya_job_id ON public.call_processing_jobs USING btree (shunya_job_id);


--
-- Name: ix_call_processing_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_call_processing_jobs_status ON public.call_processing_jobs USING btree (status);


--
-- Name: ix_calls_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_company_id ON public.calls USING btree (company_id);


--
-- Name: ix_calls_contact_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_contact_card_id ON public.calls USING btree (contact_card_id);


--
-- Name: ix_calls_handled_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_handled_by_user_id ON public.calls USING btree (handled_by_user_id);


--
-- Name: ix_calls_lead_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_lead_id ON public.calls USING btree (lead_id);


--
-- Name: ix_calls_phone_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_calls_phone_number ON public.calls USING btree (phone_number);


--
-- Name: ix_company_integrations_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_company_integrations_company_id ON public.company_integrations USING btree (company_id);


--
-- Name: ix_contact_cards_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_cards_company_id ON public.contact_cards USING btree (company_id);


--
-- Name: ix_contact_cards_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_cards_email ON public.contact_cards USING btree (email);


--
-- Name: ix_contact_cards_primary_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_contact_cards_primary_phone ON public.contact_cards USING btree (primary_phone);


--
-- Name: ix_insight_jobs_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insight_jobs_company_id ON public.insight_jobs USING btree (company_id);


--
-- Name: ix_insight_jobs_shunya_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_insight_jobs_shunya_job_id ON public.insight_jobs USING btree (shunya_job_id);


--
-- Name: ix_insight_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_insight_jobs_status ON public.insight_jobs USING btree (status);


--
-- Name: ix_invitations_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invitations_company_id ON public.invitations USING btree (company_id);


--
-- Name: ix_invitations_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invitations_email ON public.invitations USING btree (email);


--
-- Name: ix_invitations_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invitations_expires_at ON public.invitations USING btree (expires_at);


--
-- Name: ix_invitations_inviter_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invitations_inviter_id ON public.invitations USING btree (inviter_id);


--
-- Name: ix_invitations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_invitations_status ON public.invitations USING btree (status);


--
-- Name: ix_invitations_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_invitations_token ON public.invitations USING btree (token);


--
-- Name: ix_leads_assigned_rep_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_leads_assigned_rep_id ON public.leads USING btree (assigned_rep_id);


--
-- Name: ix_leads_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_leads_company_id ON public.leads USING btree (company_id);


--
-- Name: ix_leads_contact_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_leads_contact_card_id ON public.leads USING btree (contact_card_id);


--
-- Name: ix_leads_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_leads_status ON public.leads USING btree (status);


--
-- Name: ix_pending_actions_appointment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_appointment_id ON public.pending_actions USING btree (appointment_id);


--
-- Name: ix_pending_actions_call_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_call_id ON public.pending_actions USING btree (call_id);


--
-- Name: ix_pending_actions_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_company_id ON public.pending_actions USING btree (company_id);


--
-- Name: ix_pending_actions_due_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_due_at ON public.pending_actions USING btree (due_at);


--
-- Name: ix_pending_actions_lead_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_lead_id ON public.pending_actions USING btree (lead_id);


--
-- Name: ix_pending_actions_owner_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_owner_id ON public.pending_actions USING btree (owner_id);


--
-- Name: ix_pending_actions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pending_actions_status ON public.pending_actions USING btree (status);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: appointments appointments_assigned_rep_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_assigned_rep_id_fkey FOREIGN KEY (assigned_rep_id) REFERENCES public.users(id);


--
-- Name: appointments appointments_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: appointments appointments_contact_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_contact_card_id_fkey FOREIGN KEY (contact_card_id) REFERENCES public.contact_cards(id);


--
-- Name: appointments appointments_interaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_interaction_id_fkey FOREIGN KEY (interaction_id) REFERENCES public.calls(id) ON DELETE SET NULL;


--
-- Name: appointments appointments_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appointments
    ADD CONSTRAINT appointments_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: ask_otto_conversations ask_otto_conversations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ask_otto_conversations
    ADD CONSTRAINT ask_otto_conversations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: ask_otto_conversations ask_otto_conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ask_otto_conversations
    ADD CONSTRAINT ask_otto_conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: ask_otto_messages ask_otto_messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ask_otto_messages
    ADD CONSTRAINT ask_otto_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.ask_otto_conversations(id);


--
-- Name: call_analyses call_analyses_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_analyses
    ADD CONSTRAINT call_analyses_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: call_analyses call_analyses_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_analyses
    ADD CONSTRAINT call_analyses_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: call_processing_jobs call_processing_jobs_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_processing_jobs
    ADD CONSTRAINT call_processing_jobs_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: call_processing_jobs call_processing_jobs_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_processing_jobs
    ADD CONSTRAINT call_processing_jobs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: calls calls_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: calls calls_contact_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_contact_card_id_fkey FOREIGN KEY (contact_card_id) REFERENCES public.contact_cards(id);


--
-- Name: calls calls_handled_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_handled_by_user_id_fkey FOREIGN KEY (handled_by_user_id) REFERENCES public.users(id);


--
-- Name: calls calls_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.calls
    ADD CONSTRAINT calls_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: contact_cards contact_cards_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_cards
    ADD CONSTRAINT contact_cards_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: company_integrations fk_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_integrations
    ADD CONSTRAINT fk_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: insight_jobs insight_jobs_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.insight_jobs
    ADD CONSTRAINT insight_jobs_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: invitations invitations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: invitations invitations_inviter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_inviter_id_fkey FOREIGN KEY (inviter_id) REFERENCES public.users(id);


--
-- Name: leads leads_assigned_rep_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_assigned_rep_id_fkey FOREIGN KEY (assigned_rep_id) REFERENCES public.users(id);


--
-- Name: leads leads_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: leads leads_contact_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_contact_card_id_fkey FOREIGN KEY (contact_card_id) REFERENCES public.contact_cards(id);


--
-- Name: pending_actions pending_actions_appointment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_appointment_id_fkey FOREIGN KEY (appointment_id) REFERENCES public.appointments(id);


--
-- Name: pending_actions pending_actions_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.calls(id);


--
-- Name: pending_actions pending_actions_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: pending_actions pending_actions_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id);


--
-- Name: pending_actions pending_actions_owner_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_actions
    ADD CONSTRAINT pending_actions_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id);


--
-- Name: users users_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- PostgreSQL database dump complete
--

\unrestrict D19LZbGB8yyCU2lF6pnRT9IWrlATVWOyrgb6cRPv9CkP87fbMLwV0WnSt2Nf2eU

