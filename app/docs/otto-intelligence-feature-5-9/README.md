# 🤖 Otto Intelligence Service

**AI-Powered Call Intelligence, Insights, and Conversational AI**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Deployment](#deployment)
- [Contributing](#contributing)

---

## 🎯 Overview

Otto Intelligence is a production-ready microservice that provides AI-powered capabilities for sales call analysis and interaction. It processes call audio, generates insights, offers an intelligent chat interface, and enables dynamic SOP-based performance evaluation.

### Key Capabilities

1. **Call Processing Pipeline** - Automated transcription, summarization, and RAG indexing
2. **Weekly Insights Engine** - Company-wide and customer-specific analytics with scheduled generation
3. **Ask Otto Chat** - Conversational AI for querying call data with RAG search and LangGraph orchestration
4. **SOP Document Ingestion** - Upload SOP documents to dynamically extract performance metrics
5. **BANT Lead Scoring** - Intelligent lead qualification with explainable scoring breakdown
6. **SOP Version Control** - Version tracking, scheduled activation, and call re-analysis
7. **Coaching Impact Measurement** - Closed-loop coaching with baseline comparison and ROI tracking
8. **Agent Progression Tracking** - Weekly metrics, trend detection, and peer comparison
9. **Conversation Phase Detection** - Semantic phase identification with LLM-based analysis

---

## ✨ Features

### 🎙️ Call Processing Pipeline

- **Audio Transcription** - Integration with Shunya/AssemblyAI (with mock fallback)
- **Intelligent Chunking** - Dynamic token-based segmentation (120K tokens per chunk)
- **Rolling Summarization** - Context-aware summaries using GROQ LLM
- **JSON Validation** - Schema-based output validation
- **RAG Indexing** - Vector embeddings in Milvus for semantic search
- **Background Processing** - FastAPI BackgroundTasks for async processing
- **Status Tracking** - Real-time Redis-based job status updates

### 📊 Weekly Insights Engine

- **Company Insights** - Aggregated performance metrics with week-over-week trends
- **Customer Insights** - Per-customer interaction analysis with priority scoring
- **Objection Analysis** - Category-based trend detection and best response identification
- **MongoDB Aggregations** - Efficient data processing pipelines
- **Scheduled Generation** - APScheduler-based automatic weekly insights (Sundays at 00:00 UTC)
- **On-Demand Generation** - Manual trigger via API endpoints

### 💬 Ask Otto Chat

- **Multi-turn Conversations** - Full context preservation with 24-hour expiry
- **RAG Search** - Semantic search across call summaries and SOP documents
- **Customer Context** - Automatic customer data retrieval with fuzzy phone number matching
- **LangGraph Orchestration** - Intelligent tool routing with multi-source queries
- **Real-time Responses** - GROQ-powered fast inference (llama-3.3-70b-versatile)
- **Source Citations** - Transparent reference to original call data

### 📄 SOP Document Ingestion (Feature 4)

- **Document Upload** - Accept PDF and Word documents via REST API
- **Text Extraction** - Extract structured text from PDF, DOC, DOCX formats
- **SOP Validation** - LLM-based validation to confirm valid SOP documents
- **Dynamic Chunking** - Context-aware chunking for large documents
- **Metric Generation** - Automatic extraction of role-specific performance metrics
- **Multi-tenant Storage** - Company and role-based metric organization
- **Pipeline Integration** - Inject SOP metrics into call evaluation
- **RAG Integration** - Index SOP content for Ask Otto queries

### 🎯 BANT Lead Scoring (Feature 5)

- **BANT Algorithm** - Budget, Authority, Need, Timeline scoring (25 points each)
- **Explainable Scores** - Full breakdown showing how each component was scored
- **Objection Penalties** - Deductions based on severity and type of unresolved objections
- **Bonus Points** - Extra points for urgency signals, referrals, inbound leads
- **Lead Bands** - Automatic classification into Hot (75+), Warm (50-74), Cold (0-49)
- **Proportional Weighting** - Handles incomplete BANT data gracefully
- **API Endpoints** - List leads, view distribution, track score history per customer

### 📋 SOP Version Control (Feature 6)

- **Version Tracking** - Auto-increment version numbers on new uploads
- **Archive Management** - Automatic archiving of previous versions
- **Scheduled Activation** - Set future activation dates for new SOP versions
- **Call Re-analysis** - Re-evaluate historical calls against new SOP versions
- **Duplicate Detection** - Prevent re-uploading identical documents
- **Version Comparison** - Compare metrics between versions
- **Background Jobs** - Scheduled activation check and re-analysis processing

### 🎓 Coaching Impact Measurement (Feature 7)

- **Session Tracking** - Log coaching sessions with focus areas and targets
- **Baseline Calculation** - Auto-calculate pre-coaching performance (5 calls minimum)
- **Outlier Removal** - Statistical outlier exclusion for accurate baselines
- **Impact Measurement** - Compare baseline vs follow-up performance
- **Follow-up Tracking** - 2-week default follow-up with automatic extension
- **Coach Effectiveness** - Per-coach metrics and skill-specific success rates
- **ROI Dashboard** - Company-wide coaching impact and top performers

### 📈 Agent Progression Tracking (Feature 8)

- **Weekly Metrics** - Track performance at weekly granularity
- **Trend Detection** - Identify improving, stable, or declining patterns (5% threshold)
- **Anomaly Detection** - Flag sudden changes exceeding 20%
- **Confidence Levels** - Low/high confidence based on call volume (5+ calls)
- **Peer Comparison** - On-demand ranking against company peers
- **Manager Dashboard** - Summary view of all agents with alerts
- **Multi-metric Support** - Track compliance, booking rate, qualification, etc.

### 🔍 Conversation Phase Detection (Feature 9)

- **6 Core Phases** - Greeting, Problem Discovery, Qualification, Objection Handling, Closing, Post-Close
- **LLM-based Detection** - Semantic phase identification using AI
- **Timestamp Mapping** - Estimated or actual timestamps for each phase
- **Phase Analytics** - Time distribution and missing phase flagging
- **Quality Scoring** - Per-phase execution quality assessment
- **Search by Phase** - Find calls with or without specific phases
- **Company Analytics** - Aggregated phase patterns across calls

---

## 🏗️ Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Service                         │
│  ┌────────────┐  ┌─────────────┐  ┌──────────────┐         │
│  │ Call API   │  │ Insights    │  │ Ask Otto     │         │
│  │ Endpoints  │  │ Endpoints   │  │ Endpoints    │         │
│  └────┬───────┘  └──────┬──────┘  └──────┬───────┘         │
│       │                 │                 │                  │
│  ┌────▼─────────────────▼─────────────────▼──────────┐     │
│  │       Background Tasks (FastAPI BackgroundTasks)   │     │
│  │  • Call Processing    • Insight Generation         │     │
│  └────┬───────────────────────────────────┬───────────┘     │
│       │                                   │                  │
│  ┌────▼──────────────────────────┐  ┌────▼─────────────┐   │
│  │     APScheduler (Async)       │  │  SOP Processing   │   │
│  │  • Weekly Insights (Sundays)  │  │  • Doc Extraction │   │
│  └───────────────────────────────┘  └──────────────────┘   │
└───────┼───────────────────────────────────┼────────────────┘
        │                                   │
   ┌────▼─────┐  ┌──────────┐  ┌──────────▼────┐  ┌─────────┐
   │ MongoDB  │  │  Milvus  │  │  Redis (SSL)  │  │  GROQ   │
   │ (Atlas)  │  │ (Zilliz) │  │  (Upstash)    │  │   API   │
   └──────────┘  └──────────┘  └───────────────┘  └─────────┘
```

### Key Design Decisions

#### Background Task Processing

**Implementation**: FastAPI BackgroundTasks + APScheduler  
**Status Tracking**: Redis (Upstash with SSL)

**Why This Architecture?**:
- ✅ **Simplicity**: No separate worker process needed
- ✅ **SSL Compatibility**: Works perfectly with Upstash Redis SSL
- ✅ **Single Process**: Easier deployment and monitoring
- ✅ **Async Native**: Fully async/await throughout
- ✅ **Scheduled Tasks**: APScheduler handles cron-like jobs
- ✅ **Production Ready**: Handles real-world workloads efficiently

**When to Consider Celery**:
- Multiple distributed worker servers needed
- Tasks longer than 30 minutes
- Advanced retry mechanisms with complex workflows
- Massive scale (1000s of concurrent tasks)

**Note**: Legacy Celery configuration files exist in the repo (docker-compose.yml references) but are not actively used. The service runs entirely on FastAPI BackgroundTasks + APScheduler.

---

## 🛠️ Tech Stack

### Core Framework
- **FastAPI** (0.109.0) - Modern async web framework
- **Python** (3.11+) - Programming language
- **Pydantic** (2.5.3) - Data validation and settings
- **APScheduler** (3.10.4) - Background task scheduling

### AI & ML
- **GROQ** - LLM inference (llama-3.3-70b-versatile)
- **HuggingFace Sentence Transformers** - Open-source sentence embeddings (all-MiniLM-L6-v2, 384-dim)
- **LangGraph** (0.0.20) - AI workflow orchestration
- **LangChain** (0.1.5) - LLM application framework
- **Tiktoken** (0.5.2) - Token counting

### Databases & Storage
- **MongoDB** (Motor 3.3.2) - Primary document database
- **Milvus** (Zilliz Cloud, pymilvus 2.4.4+) - Vector database for RAG
- **Redis** (Upstash SSL, redis 5.0.1) - Caching, job status tracking, and session management
- **AWS S3** (boto3 1.34.34) - Audio file storage

### External Services
- **Shunya/AssemblyAI** - Audio transcription services
- **GROQ API** - Fast LLM completions (OpenAI-compatible)

### Document Processing
- **PyPDF2** (3.0.1) - PDF text extraction
- **pdfplumber** (0.11.0) - Advanced PDF parsing
- **python-docx** (1.1.0) - Word document processing
- **python-magic** (0.4.27) - File type detection

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- MongoDB instance (Atlas recommended or local)
- Redis instance (Upstash with SSL or local)
- Milvus/Zilliz Cloud instance
- GROQ API key (for LLM completions)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/otto-intelligence.git
cd otto-intelligence
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
# Create .env file with the following variables
nano .env
```

Required environment variables:
```bash
# API Configuration
API_KEY=your_secure_api_key_here
API_HOST=0.0.0.0
API_PORT=9000
ENVIRONMENT=development

# MongoDB
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=otto-ai-storage

# Redis (Upstash SSL)
REDIS_URL=rediss://default:password@host:6379

# Milvus (Zilliz Cloud)
MILVUS_URI=https://your-cluster.zillizcloud.com
MILVUS_TOKEN=your_milvus_token
MILVUS_COLLECTION=otto_intelligence_v1

# GROQ (LLM)
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_BASE=https://api.groq.com/openai/v1

# HuggingFace (Embeddings - uses local model)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```

5. **Initialize Milvus collection (optional, auto-created on first use)**
```bash
python scripts/setup_milvus.py
```

6. **Run the service**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

The service will be available at `http://localhost:9000`

### Quick Start with Docker (Note: Partially Configured)

The repository includes `docker-compose.yml` and `Dockerfile`, but note that the service currently uses FastAPI BackgroundTasks instead of Celery, so the Celery worker/beat containers in docker-compose are legacy references.

To run just the API:
```bash
docker build -t otto-intelligence:latest .
docker run -d \
  --name otto-intelligence \
  -p 9000:9000 \
  --env-file .env \
  otto-intelligence:latest
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# API Configuration
API_KEY=your_secure_api_key_here
API_HOST=0.0.0.0
API_PORT=9000
ENVIRONMENT=development
LOG_LEVEL=INFO

# MongoDB
MONGODB_URL=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=otto-ai-storage

# Redis (Upstash SSL)
REDIS_URL=rediss://default:password@host.upstash.io:6379

# Milvus (Zilliz Cloud)
MILVUS_URI=https://your-cluster.zillizcloud.com
MILVUS_TOKEN=your_milvus_token
MILVUS_COLLECTION=otto_intelligence_v1

# GROQ (LLM)
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_BASE=https://api.groq.com/openai/v1

# HuggingFace (Embeddings)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384

# AWS S3 (Audio Storage - Optional)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
S3_BUCKET=your-audio-bucket

# Transcription Services (Optional)
SHUNYA_API_URL=https://api.shunya.ai
SHUNYA_API_KEY=your_shunya_key
ASSEMBLYAI_API_KEY=your_assemblyai_key

# Optional: OpenAI (not currently used, GROQ is primary)
OPENAI_API_KEY=sk-your-openai-key
```

### Collections Created in MongoDB

The service automatically creates the following collections:
- `calls` - Call metadata and processing status
- `call_summaries` - Processed call summaries (includes lead scores)
- `chunk_summaries` - Individual chunk summaries for RAG
- `weekly_insights` - Company, customer, and objection insights
- `conversations` - Ask Otto conversation sessions
- `messages` - Ask Otto message history
- `sop_documents` - SOP document metadata
- `sop_metrics` - Extracted performance metrics from SOPs
- `sop_chunks` - Chunked SOP content for RAG
- `sop_version_history` - SOP version tracking and history
- `call_reanalysis` - Re-analysis results for calls
- `reanalysis_jobs` - Re-analysis job tracking
- `coaching_sessions` - Coaching session data with baselines
- `coach_effectiveness` - Aggregated coach performance
- `call_phases` - Conversation phase detection results

### Milvus Collection Schema

The service uses a single Milvus collection (`otto_intelligence_v1`) with the following schema:
- **Vector Field**: `embedding` (384 dimensions, FLOAT_VECTOR)
- **Metadata Fields**: 
  - `corpus_type` (call_summary, chunk_summary, sop_document, etc.)
  - `source_id` (call_id, chunk_id, sop_id)
  - `company_id`
  - `created_at`

---

## 📚 API Documentation

### Interactive API Docs

- **Swagger UI**: http://localhost:9000/docs
- **ReDoc**: http://localhost:9000/redoc

### API Overview

The service exposes 50+ endpoints across 9 feature areas:

#### 1. Call Processing (8 endpoints)
- `POST /api/v1/call-processing/process` - Submit call for processing
- `GET /api/v1/call-processing/status/{job_id}` - Check processing status
- `GET /api/v1/call-processing/summary/{call_id}` - Get call summary
- `GET /api/v1/call-processing/chunks/{call_id}` - Get chunk summaries
- `POST /api/v1/call-processing/retry/{job_id}` - Retry failed job
- `GET /api/v1/call-processing/calls/{call_id}/phases` - Get conversation phases
- `GET /api/v1/call-processing/phases/search` - Search calls by phase
- `GET /api/v1/call-processing/phases/analytics` - Get phase analytics

#### 2. Weekly Insights (5 endpoints)
- `POST /api/v1/insights/generate` - Trigger insights generation
- `GET /api/v1/insights/status/{job_id}` - Check generation status
- `GET /api/v1/insights/company/{company_id}/current` - Get company insights
- `GET /api/v1/insights/customers?company_id=X` - List customer insights
- `GET /api/v1/insights/objections/{company_id}` - Get objection insights

#### 3. Ask Otto Chat (5 endpoints)
- `POST /api/v1/ask-otto/conversations` - Create conversation
- `POST /api/v1/ask-otto/conversations/{id}/messages` - Send message
- `GET /api/v1/ask-otto/conversations/{id}/messages` - Get message history
- `GET /api/v1/ask-otto/conversations/{id}` - Get conversation details
- `DELETE /api/v1/ask-otto/conversations/{id}` - Delete conversation

#### 4. SOP Document Ingestion (7 endpoints)
- `POST /api/v1/sop/documents/upload` - Upload SOP document
- `GET /api/v1/sop/documents/status/{job_id}` - Check processing status
- `GET /api/v1/sop/metrics/{company_id}` - Get company SOP metrics
- `GET /api/v1/sop/documents/{sop_id}` - Get SOP document details
- `GET /api/v1/sop/documents?company_id=X` - List SOP documents
- `PATCH /api/v1/sop/documents/{sop_id}/status` - Update SOP status
- `DELETE /api/v1/sop/documents/{sop_id}` - Delete SOP document

#### 5. Lead Scoring (3 endpoints)
- `GET /api/v1/insights/leads` - List leads with filtering (band, score range)
- `GET /api/v1/insights/leads/distribution` - Get lead score distribution stats
- `GET /api/v1/insights/leads/{customer_id}/history` - Get customer score history

#### 6. SOP Version Control (5 endpoints)
- `POST /api/v1/sop/documents/{sop_id}/versions` - Upload new SOP version
- `GET /api/v1/sop/documents/{sop_id}/versions` - Get version history
- `GET /api/v1/sop/documents/{sop_id}/versions/{version}` - Get specific version
- `POST /api/v1/sop/documents/{sop_id}/reanalyze` - Trigger call re-analysis
- `GET /api/v1/sop/reanalysis/{job_id}` - Get re-analysis results

#### 7. Coaching (6 endpoints)
- `POST /api/v1/coaching/sessions` - Create coaching session
- `GET /api/v1/coaching/sessions` - List coaching sessions
- `GET /api/v1/coaching/sessions/{session_id}` - Get session details
- `GET /api/v1/coaching/sessions/{session_id}/impact` - Get impact report
- `GET /api/v1/coaching/coaches/{coach_id}/effectiveness` - Get coach metrics
- `GET /api/v1/coaching/roi` - Get company coaching ROI

#### 8. Agent Progression (3 endpoints)
- `GET /api/v1/insights/agents/{rep_id}/progression` - Get agent progression
- `GET /api/v1/insights/agents/{rep_id}/peer-comparison` - Compare to peers
- `GET /api/v1/insights/agents/summary` - Get all agents summary

### Quick API Examples

#### Health Check
```bash
curl http://localhost:9000/health
```

#### Call Processing
```bash
curl -X POST "http://localhost:9000/api/v1/call-processing/process" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "call_001",
    "company_id": "company_123",
    "audio_url": "https://example.com/audio.mp3",
    "phone_number": "+1234567890"
  }'
```

#### Generate Insights
```bash
curl -X POST "http://localhost:9000/api/v1/insights/generate" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "week_start": "2026-01-06",
    "week_end": "2026-01-12"
  }'
```

#### Ask Otto Chat
```bash
# Create conversation
curl -X POST "http://localhost:9000/api/v1/ask-otto/conversations" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "company_123",
    "user_id": "user_001"
  }'

# Send message (use conversation_id from response)
curl -X POST "http://localhost:9000/api/v1/ask-otto/conversations/{conversation_id}/messages" \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How many calls did we process this week?",
    "context": {
      "include_customer_context": true,
      "max_rag_results": 5
    }
  }'
```

#### SOP Upload
```bash
curl -X POST "http://localhost:9000/api/v1/sop/documents/upload" \
  -H "X-API-Key: your_api_key" \
  -F "file=@/path/to/sop.pdf" \
  -F "company_id=company_123" \
  -F "sop_name=Sales Call Guidelines" \
  -F "target_role=sales_rep"
```

---

## 🧪 Testing

### Comprehensive Test Suite

The repository includes a comprehensive test suite in the `tests/` directory:

```bash
# Run all features test
./tests/test_all_features.sh

# Test individual features
./tests/test_feature1_e2e.sh  # Call processing
./tests/test_feature3_e2e.sh  # Ask Otto
./tests/test_feature4_e2e.sh  # SOP ingestion

# Test SOP functionality
./tests/test_new_sop_upload.sh
./tests/test_sop_questions.sh

# Performance tests
./tests/test_redis_caching.sh
./tests/test_embedding_performance.sh
```

### Manual Testing

#### Test Call Processing
```bash
curl -X POST "http://localhost:9000/api/v1/call-processing/process" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "test_001",
    "company_id": "acme_roofing",
    "audio_url": "https://example.com/audio.wav",
    "phone_number": "+1234567890"
  }'

# Check status (use job_id from response)
curl "http://localhost:9000/api/v1/call-processing/status/{job_id}" \
  -H "X-API-Key: $API_KEY"
```

#### Test Insights Generation
```bash
curl -X POST "http://localhost:9000/api/v1/insights/generate" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "week_start": "2026-01-06",
    "week_end": "2026-01-12"
  }'
```

#### Test Ask Otto
```bash
# Create conversation
CONV_RESPONSE=$(curl -X POST "http://localhost:9000/api/v1/ask-otto/conversations" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": "acme_roofing",
    "user_id": "user_123"
  }')

CONVERSATION_ID=$(echo $CONV_RESPONSE | jq -r '.conversation_id')

# Send message
curl -X POST "http://localhost:9000/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me the latest calls",
    "context": {
      "include_customer_context": true,
      "max_rag_results": 5
    }
  }'
```

### Testing Documentation

For detailed testing instructions, see:
- `docs/COMPREHENSIVE_TESTING_GUIDE.md` - Complete testing guide
- `docs/QUICK_TEST_REFERENCE.md` - Quick reference
- `docs/TEST_RESULTS_FINAL.md` - Latest test results

---

## 📦 Deployment

### Production Checklist

- [ ] Set strong `API_KEY` in environment
- [ ] Use production MongoDB cluster with appropriate indexes
- [ ] Configure Redis SSL certificates (Upstash recommended)
- [ ] Set up Milvus/Zilliz Cloud production cluster
- [ ] Configure S3 bucket with proper IAM permissions
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure CORS for your domain in `app/main.py`
- [ ] Set up monitoring and logging
- [ ] Enable rate limiting
- [ ] Review and optimize APScheduler job schedules
- [ ] Set up health check monitoring
- [ ] Configure backup strategies for MongoDB

### Docker Deployment

```bash
# Build image
docker build -t otto-intelligence:latest .

# Run container
docker run -d \
  --name otto-intelligence \
  -p 9000:9000 \
  --env-file .env \
  otto-intelligence:latest
```

### Production Architecture Notes

**Single Container Deployment**: The service runs as a single FastAPI application with:
- HTTP server (Uvicorn)
- Background task processing (FastAPI BackgroundTasks)
- Scheduled jobs (APScheduler)

**Scaling Considerations**:
- For horizontal scaling, use a load balancer (nginx, AWS ALB)
- Ensure Redis is shared across instances for job status
- APScheduler jobs will run on each instance (use leader election if needed)
- Consider moving to Celery for distributed task processing at high scale

**Resource Requirements**:
- Minimum: 2 CPU cores, 4GB RAM
- Recommended: 4 CPU cores, 8GB RAM
- GPU optional (speeds up embeddings if using CUDA-enabled transformers)

---

## 📊 Monitoring

### Health Check

```bash
curl http://localhost:9000/health
```

Response:
```json
{
  "status": "healthy",
  "service": "otto-intelligence",
  "version": "1.0.0",
  "environment": "production"
}
```

### Scheduler Status

Check the status of background scheduled jobs:

```bash
curl http://localhost:9000/api/v1/scheduler/status
```

Response:
```json
{
  "running": true,
  "jobs_count": 1,
  "jobs": [
    {
      "id": "weekly_insights_generation",
      "name": "Weekly Insights Generation",
      "next_run_time": "2026-01-12T00:00:00+00:00",
      "trigger": "cron[day_of_week='sun', hour='0', minute='0']"
    }
  ]
}
```

### Logs

Structured logging with timestamps:
- Request/Response logs with unique request IDs
- Error tracking with stack traces
- Performance metrics (response times)
- Background task progress updates

Log format:
```
2026-01-09 10:30:45 - app.main - INFO - Request: GET /health [req_id: abc123]
2026-01-09 10:30:45 - app.services.call_processing - INFO - Processing call: call_001
```

### Metrics (Future Enhancement)

The service is ready for Prometheus integration via `/metrics` endpoint (not yet implemented).

---

## 🔒 Security

- **API Key Authentication**: Required for all endpoints
- **HTTPS**: Enforced in production
- **Input Validation**: Pydantic models for all requests
- **Rate Limiting**: Configurable per endpoint
- **CORS**: Configurable allowed origins
- **Secret Management**: Environment variables only

---

## 📈 Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Health Check | < 50ms | Simple status endpoint |
| Call Submit | < 100ms | Returns job_id immediately |
| Ask Otto Response | 1-3s | Depends on RAG search + LLM |
| Background Task | Async, non-blocking | Processing happens in background |
| Insights Generation | 5-15 min | Depends on data volume |
| SOP Processing | 30s - 5min | Depends on document size |
| Embedding Generation | ~100ms/chunk | Uses local HuggingFace model |
| Vector Search (Milvus) | < 200ms | For typical query sizes |

### Optimization Notes

- **Embeddings**: Pre-loaded on startup, uses GPU if available (CUDA)
- **Caching**: Redis caching for job status, customer context, and metrics
- **Database**: MongoDB indexes on frequently queried fields
- **Async**: Fully async/await throughout for I/O operations

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone and setup
git clone https://github.com/yourusername/otto-intelligence.git
cd otto-intelligence

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies (if available)
pip install black ruff mypy pytest pytest-asyncio

# Run linting
black app/
ruff check app/

# Run type checking
mypy app/
```

### Code Style

- Follow PEP 8 guidelines
- Use type hints for all function signatures
- Write docstrings for all public functions and classes
- Keep functions focused and modular
- Use async/await for I/O operations

### Testing

Before submitting a PR:
- Ensure all existing tests pass: `./tests/test_all_features.sh`
- Add tests for new features
- Update documentation as needed
- Test with real API credentials (MongoDB, Redis, Milvus, GROQ)

---

## 📁 Project Structure

```
otto-intelligence/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── config.py                  # Configuration management
│   │
│   ├── api/v1/                    # API endpoints
│   │   ├── call_processing.py     # Call processing endpoints (5)
│   │   ├── insights.py            # Insights endpoints (5)
│   │   ├── ask_otto.py            # Ask Otto chat endpoints (5)
│   │   └── sop.py                 # SOP document endpoints (7)
│   │
│   ├── core/                      # Core infrastructure
│   │   ├── database.py            # MongoDB connection
│   │   ├── redis_client.py        # Redis connection
│   │   ├── milvus_client.py       # Milvus vector DB
│   │   ├── scheduler.py           # APScheduler setup
│   │   ├── middleware.py          # Auth & logging
│   │   └── exceptions.py          # Custom exceptions
│   │
│   ├── models/                    # Data models
│   │   ├── enums.py               # All enum definitions
│   │   ├── call.py                # Call models
│   │   ├── insight.py             # Insight models
│   │   ├── conversation.py        # Chat models
│   │   └── sop.py                 # SOP models
│   │
│   ├── schemas/                   # Pydantic schemas
│   │   ├── call.py                # Call API schemas
│   │   ├── insight.py             # Insights API schemas
│   │   ├── ask_otto.py            # Ask Otto schemas
│   │   └── sop.py                 # SOP API schemas
│   │
│   ├── services/                  # Business logic
│   │   ├── call_processing/       # Feature 1: Call Processing
│   │   │   ├── audio_service.py
│   │   │   ├── transcription_service.py
│   │   │   ├── chunking_service.py
│   │   │   ├── summary_service.py
│   │   │   ├── validation_service.py
│   │   │   ├── rag_service.py
│   │   │   └── embedding_service.py
│   │   │
│   │   ├── insights/              # Feature 2: Weekly Insights
│   │   │   ├── company_insights.py
│   │   │   ├── customer_insights.py
│   │   │   └── objection_insights.py
│   │   │
│   │   ├── ask_otto/              # Feature 3: Ask Otto Chat
│   │   │   ├── conversation_service.py
│   │   │   ├── rag_search_service.py
│   │   │   ├── customer_context_service.py
│   │   │   └── langgraph_service.py
│   │   │
│   │   └── sop/                   # Feature 4: SOP Ingestion
│   │       ├── document_service.py
│   │       ├── extraction_service.py
│   │       ├── chunking_service.py
│   │       ├── metric_extraction_service.py
│   │       ├── validation_service.py
│   │       └── evaluation_service.py
│   │
│   └── tasks/                     # Background tasks
│       ├── call_tasks.py          # Call processing tasks
│       ├── insight_tasks.py       # Insights generation
│       └── sop_tasks.py           # SOP processing tasks
│
├── docs/                          # Documentation
│   ├── ARCHITECTURE_*.md          # Architecture docs
│   ├── COMPREHENSIVE_TESTING_GUIDE.md
│   ├── STARTUP_GUIDE.md
│   └── TEST_RESULTS_FINAL.md
│
├── scripts/                       # Utility scripts
│   ├── setup_milvus.py            # Initialize Milvus
│   └── reindex_sop.py             # Reindex SOP data
│
├── tests/                         # Test scripts
│   ├── test_all_features.sh       # Complete test suite
│   ├── test_feature1_e2e.sh       # Call processing tests
│   ├── test_feature3_e2e.sh       # Ask Otto tests
│   └── test_feature4_e2e.sh       # SOP tests
│
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container configuration
├── docker-compose.yml             # Multi-container setup
├── .env                           # Environment variables
└── README.md                      # This file
```

---

## 📝 Documentation

### Architecture Documentation
- **ARCHITECTURE_README.md** - Overall architecture overview
- **ARCHITECTURE_FEATURE_1_CALL_PIPELINE.md** - Call processing pipeline details
- **ARCHITECTURE_FEATURE_2_INSIGHTS_ENGINE.md** - Weekly insights engine
- **ARCHITECTURE_FEATURE_3_ASK_OTTO.md** - Ask Otto chat system
- **ARCHITECTURE_FEATURE_4_DOCUMENT_INGESTION.md** - SOP document processing
- **INDEPENDENT_SERVICE_ARCHITECTURE_OVERVIEW.md** - Service independence design

### Implementation Guides
- **STARTUP_GUIDE.md** - Quick startup instructions
- **COMPREHENSIVE_TESTING_GUIDE.md** - Complete testing guide
- **DEPLOYMENT_CHECKLIST.md** - Production deployment checklist
- **IMPLEMENTATION_COMPLETE.md** - Implementation summary

### Status & Results
- **FINAL_IMPLEMENTATION_COMPLETE.md** - Complete feature status
- **TEST_RESULTS_FINAL.md** - Latest test results
- **FEATURE_3_4_FINAL_TEST_RESULTS.md** - Feature 3 & 4 test results
- **PROJECT_DELIVERY_SUMMARY.md** - Overall project summary

### API Documentation
- **Swagger UI**: http://localhost:9000/docs
- **ReDoc**: http://localhost:9000/redoc

---

## 🐛 Troubleshooting

### Common Issues

#### "Failed to connect to MongoDB"
- Check `MONGODB_URL` in `.env`
- Verify network connectivity
- Check MongoDB Atlas whitelist (add your IP or 0.0.0.0/0 for testing)
- Ensure database user has read/write permissions

#### "Failed to connect to Redis"
- Verify `REDIS_URL` format (use `rediss://` for SSL)
- Check Upstash dashboard for connection details
- Ensure SSL is enabled in Redis URL
- Test Redis connectivity: `redis-cli -u $REDIS_URL ping`

#### "Milvus collection not found"
- Run `python scripts/setup_milvus.py` to create collection
- Verify Milvus URI and token in `.env`
- Check collection name matches `MILVUS_COLLECTION`
- Ensure Zilliz Cloud cluster is running

#### "GROQ API error"
- Verify `GROQ_API_KEY` is valid
- Check API quota/limits at https://console.groq.com
- Verify model name is correct (llama-3.3-70b-versatile)
- Check network connectivity to api.groq.com

#### "Embedding model not loading"
- Ensure `sentence-transformers` is installed
- Check disk space for model cache (~90MB for all-MiniLM-L6-v2)
- Model downloads to `~/.cache/huggingface/`
- For GPU: Ensure CUDA is properly configured

#### "Background tasks not running"
- Check FastAPI server logs for errors
- Verify Redis connection (tasks use Redis for status tracking)
- Ensure sufficient memory is available
- Check `app/core/background_tasks.py` for task manager status

#### "Scheduled jobs not running"
- Check scheduler status: `GET /api/v1/scheduler/status`
- Verify APScheduler is running (check startup logs)
- Ensure system time is correct (jobs are timezone-aware)
- Check `app/core/scheduler.py` configuration

For more issues and solutions, see:
- `docs/COMPREHENSIVE_TESTING_GUIDE.md`
- `docs/CELERY_SSL_ISSUE_AND_SOLUTION.md` (historical reference)
- GitHub Issues: https://github.com/yourusername/otto-intelligence/issues

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👥 Team

**Otto Intelligence Team**
- Lead Developer: [Your Name]
- AI/ML: [Team Member]
- Backend: [Team Member]

---

## 🙏 Acknowledgments

- **FastAPI** - Modern async web framework
- **GROQ** - Fast LLM inference with competitive pricing
- **HuggingFace** - Open-source transformer models and embeddings
- **Milvus/Zilliz** - High-performance vector database
- **MongoDB** - Flexible document storage
- **Upstash** - Serverless Redis hosting
- **LangChain/LangGraph** - LLM orchestration framework
- **Sentence Transformers** - State-of-the-art sentence embeddings

---

## 📞 Support

- **Documentation**: https://docs.otto-intelligence.com
- **Issues**: https://github.com/yourusername/otto-intelligence/issues
- **Email**: support@otto-intelligence.com

---

## 🗺️ Roadmap

### ✅ Completed (Q4 2025 - Q1 2026)
- [x] Call Processing Pipeline
- [x] Weekly Insights Engine with APScheduler
- [x] Ask Otto Chat with LangGraph
- [x] SOP Document Ingestion & Dynamic Metrics
- [x] FastAPI BackgroundTasks implementation
- [x] HuggingFace local embeddings
- [x] GROQ LLM integration
- [x] Redis caching layer
- [x] MongoDB multi-collection architecture
- [x] Milvus vector search
- [x] **BANT Lead Scoring** - Intelligent lead qualification with breakdown
- [x] **SOP Version Control** - Version tracking and call re-analysis
- [x] **Coaching Impact Measurement** - Closed-loop coaching with ROI
- [x] **Agent Progression Tracking** - Weekly metrics and trend detection
- [x] **Conversation Phase Detection** - Semantic phase identification

### Q2 2026
- [ ] WebSocket support for real-time Ask Otto responses
- [ ] Advanced analytics dashboard
- [ ] Multi-language support for transcription
- [ ] Custom LLM fine-tuning for domain-specific tasks
- [ ] Enhanced SOP compliance scoring
- [ ] Prometheus metrics integration

### Q3 2026
- [ ] Mobile app integration APIs
- [ ] Voice synthesis for call playback
- [ ] Advanced objection handling workflows
- [ ] A/B testing framework for insights
- [ ] Call sentiment analysis
- [ ] Real-time call monitoring

### Q4 2026
- [ ] Multi-tenant white-labeling
- [ ] Advanced role-based access control (RBAC)
- [ ] Call quality scoring AI model
- [ ] Integration marketplace (CRM, dialers, etc.)
- [ ] Advanced reporting and export features

### Future Considerations
- [ ] Migrate to Celery for distributed processing (if scale requires)
- [ ] GPU-accelerated embedding generation
- [ ] Real-time transcription streaming
- [ ] Custom vocabulary training
- [ ] Multi-modal analysis (audio + text + metadata)

---

## 🚀 Quick Links

- [API Documentation](http://localhost:9000/docs)
- [Health Check](http://localhost:9000/health)
- [Scheduler Status](http://localhost:9000/api/v1/scheduler/status)
- [ReDoc](http://localhost:9000/redoc)
- [GitHub Repository](https://github.com/yourusername/otto-intelligence)
- [GitHub Issues](https://github.com/yourusername/otto-intelligence/issues)

---

## 📊 Project Statistics

| Metric | Count |
|--------|-------|
| **Total Features** | 9 (Call Processing, Insights, Ask Otto, SOP, Lead Scoring, Version Control, Coaching, Progression, Phases) |
| **API Endpoints** | 50+ endpoints |
| **Services** | 30+ service modules |
| **Database Collections** | 15+ MongoDB collections |
| **Background Jobs** | 4+ scheduled (Weekly Insights, Coach Effectiveness, Coaching Follow-ups, SOP Activation) |
| **Vector Dimensions** | 384 (all-MiniLM-L6-v2) |
| **Supported File Types** | PDF, DOC, DOCX, WAV, MP3 |
| **LLM Provider** | GROQ (llama-3.3-70b-versatile) |
| **Embedding Model** | HuggingFace Sentence Transformers (local) |

---

## 🏆 Production Ready Features

✅ **All 9 Core Features Implemented**  
✅ **50+ API Endpoints Active**  
✅ **Full Async Architecture**  
✅ **Redis Caching Layer**  
✅ **Vector Search (Milvus)**  
✅ **Background Task Processing**  
✅ **Scheduled Job Execution**  
✅ **Comprehensive Error Handling**  
✅ **API Key Authentication**  
✅ **Request Logging**  
✅ **Health Monitoring**  
✅ **Docker Ready**

---

**Last Updated**: January 28, 2026  
**Version**: 2.0.0  
**Status**: Production Ready ✅

