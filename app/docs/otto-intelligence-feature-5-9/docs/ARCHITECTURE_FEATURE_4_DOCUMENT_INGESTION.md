# Feature 4: SOP Document Ingestion & Dynamic Metrics Engine

**Version:** 2.0  
**Date:** February 4, 2026  
**Service:** Independent Microservice Architecture  
**Implementation:** FastAPI BackgroundTasks (No Celery)

> **Last Updated:** February 2026 - Added URL-based upload support, document download service, single active SOP rule, version control integration, and scheduled activation support.

---

## Overview

The SOP Document Ingestion feature enables companies to upload Standard Operating Procedure (SOP) documents (PDF/Word) of any length, extract and validate content, and dynamically generate role-specific performance metrics. These metrics are then used throughout the Otto Intelligence pipeline to evaluate sales representatives during call processing and guide responses in Ask Otto.

**Implementation Status**: ✅ **Fully Implemented** - Uses FastAPI BackgroundTasks for async processing, local HuggingFace embeddings, and GROQ LLM.

### Key Enhancements (v2.0)

| Enhancement | Description |
|-------------|-------------|
| **URL-Based Upload** | Support S3, HTTP/HTTPS, and local file URLs |
| **Document Download Service** | Unified download from multiple sources |
| **Single Active SOP Rule** | Only one active SOP per company/role |
| **Version Control** | Full version history with scheduled activation |
| **Re-analysis Workflow** | Re-evaluate historical calls against new SOP |
| **Legacy SOP Migration** | Auto-creates version 1 for pre-versioning SOPs |

### Key Capabilities

| Capability | Description |
|------------|-------------|
| **Document Upload** | Accept PDF/Word via file upload OR URL |
| **Text Extraction** | PDF (pdfplumber), DOCX/DOC (python-docx) |
| **SOP Validation** | LLM-based validation with fallback to keyword matching |
| **Dynamic Chunking** | Section-aware with token-based fallback (8000 tokens max) |
| **Metric Generation** | Rolling extraction across chunks with deduplication |
| **Multi-tenant Storage** | MongoDB + Redis with company/role isolation |
| **Pipeline Integration** | SOP metrics injected into call compliance evaluation |
| **RAG Integration** | Index SOP documents + metrics in Milvus |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               SOP DOCUMENT INGESTION - COMPLETE FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    CLIENT (Dashboard / Otto Backend)                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │    POST /api/v1/sop/documents/upload                                │   │
│  │                                                                      │   │
│  │    Request (multipart/form-data):                                   │   │
│  │    {                                                                 │   │
│  │      "file": <PDF or Word file>,                                    │   │
│  │      "company_id": "acme_roofing",                                  │   │
│  │      "target_role": "sales_rep",  // Optional: null = company-wide  │   │
│  │      "sop_name": "Sales Call Guidelines v2.1",                      │   │
│  │      "metadata": {                                                  │   │
│  │        "department": "sales",                                       │   │
│  │        "version": "2.1",                                            │   │
│  │        "effective_date": "2026-01-01"                               │   │
│  │      }                                                               │   │
│  │    }                                                                 │   │
│  │                                                                      │   │
│  │    Response (202 Accepted):                                          │   │
│  │    {                                                                 │   │
│  │      "job_id": "sop_job_abc123",                                    │   │
│  │      "status": "queued",                                             │   │
│  │      "message": "SOP document processing initiated",                │   │
│  │      "status_url": "/api/v1/sop/documents/status/sop_job_abc123"   │   │
│  │    }                                                                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      FILE STORAGE (S3/Local)                        │   │
│  │                                                                      │   │
│  │  s3://otto-sop-documents/{company_id}/{sop_id}/{filename}           │   │
│  │  │                                                                  │   │
│  │  Metadata stored in MongoDB:                                        │   │
│  │  • Original filename                                                │   │
│  │  • File size, type, hash                                            │   │
│  │  • Upload timestamp                                                 │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               FASTAPI BACKGROUND TASK                                │   │
│  │                                                                      │   │
│  │  BackgroundTask picks up → Updates Redis status to "processing"     │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               STEP 1: TEXT EXTRACTION SERVICE                        │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │  PDF Processing (PyPDF2 / pdfplumber):                         │ │   │
│  │  │  • Extract text from all pages                                 │ │   │
│  │  │  • Preserve structure (headers, lists, tables)                 │ │   │
│  │  │  • Handle multi-column layouts                                 │ │   │
│  │  │  • Extract tables as structured data                           │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │  Word Processing (python-docx):                                │ │   │
│  │  │  • Extract paragraphs, headings                                │ │   │
│  │  │  • Extract tables with structure                               │ │   │
│  │  │  • Preserve formatting context (bold = important)              │ │   │
│  │  │  • Handle nested lists                                         │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  Output:                                                            │   │
│  │  {                                                                  │   │
│  │    "raw_text": "...",                                               │   │
│  │    "page_count": 15,                                                │   │
│  │    "word_count": 8500,                                              │   │
│  │    "sections": [                                                    │   │
│  │      {"title": "Introduction", "content": "..."},                   │   │
│  │      {"title": "Call Guidelines", "content": "..."},                │   │
│  │      {"title": "Performance Metrics", "content": "..."}             │   │
│  │    ],                                                               │   │
│  │    "tables": [...],                                                 │   │
│  │    "metadata": {"title": "...", "author": "..."}                    │   │
│  │  }                                                                  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "extracting", "progress": 15}           │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               STEP 2: SOP VALIDATION SERVICE                         │   │
│  │                                                                      │   │
│  │  LLM Classification Prompt:                                         │   │
│  │  """                                                                 │   │
│  │  Analyze this document and determine if it is a Standard            │   │
│  │  Operating Procedure (SOP) document.                                │   │
│  │                                                                      │   │
│  │  Document Content (first 5000 chars):                               │   │
│  │  {document_preview}                                                 │   │
│  │                                                                      │   │
│  │  Return JSON:                                                       │   │
│  │  {                                                                  │   │
│  │    "is_sop": true/false,                                            │   │
│  │    "confidence": 0.0-1.0,                                           │   │
│  │    "sop_type": "sales_sop" | "support_sop" | "general_sop" | null, │   │
│  │    "detected_roles": ["sales_rep", "manager", ...],                 │   │
│  │    "has_metrics": true/false,                                       │   │
│  │    "has_procedures": true/false,                                    │   │
│  │    "rejection_reason": "..." // if not SOP                          │   │
│  │  }                                                                  │   │
│  │  """                                                                 │   │
│  │                                                                      │   │
│  │  Validation Criteria:                                               │   │
│  │  ✓ Contains procedural steps/guidelines                             │   │
│  │  ✓ Has role-specific instructions                                   │   │
│  │  ✓ Includes evaluation criteria or metrics                          │   │
│  │  ✓ Structured with sections/headers                                 │   │
│  │                                                                      │   │
│  │  If NOT SOP → Return Error:                                         │   │
│  │  {                                                                   │   │
│  │    "error": "INVALID_DOCUMENT",                                     │   │
│  │    "message": "Please upload a valid SOP document",                 │   │
│  │    "details": {                                                     │   │
│  │      "rejection_reason": "Document appears to be a marketing...",   │   │
│  │      "suggestions": [                                               │   │
│  │        "Ensure document contains procedural guidelines",            │   │
│  │        "Include role-specific instructions",                        │   │
│  │        "Add measurable performance metrics"                         │   │
│  │      ]                                                              │   │
│  │    }                                                                 │   │
│  │  }                                                                   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "validating", "progress": 25}           │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               STEP 3: DOCUMENT CHUNKING SERVICE                      │   │
│  │                                                                      │   │
│  │  Chunking Strategy (Context-Aware):                                 │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │  1. Section-Based Chunking (Primary):                          │ │   │
│  │  │     • Chunk at section/header boundaries                       │ │   │
│  │  │     • Preserve complete sections when possible                 │ │   │
│  │  │     • Maintain parent-child section hierarchy                  │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │  2. Token-Based Chunking (Fallback for large sections):        │ │   │
│  │  │     • Max chunk size: 8000 tokens                              │ │   │
│  │  │     • Overlap: 500 tokens                                      │ │   │
│  │  │     • Break at sentence boundaries                             │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │  3. Semantic Chunking (For metrics extraction):                │ │   │
│  │  │     • Group related procedures together                        │ │   │
│  │  │     • Keep metric definitions with evaluation criteria         │ │   │
│  │  │     • Preserve role-specific contexts                          │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  Output:                                                            │   │
│  │  [                                                                  │   │
│  │    {                                                                │   │
│  │      "chunk_id": "sop_chunk_001",                                   │   │
│  │      "chunk_index": 1,                                              │   │
│  │      "section_title": "Call Opening Guidelines",                    │   │
│  │      "text": "...",                                                 │   │
│  │      "token_count": 2500,                                           │   │
│  │      "chunk_type": "procedure",                                     │   │
│  │      "parent_section": "Sales Call Process"                         │   │
│  │    },                                                               │   │
│  │    ...                                                              │   │
│  │  ]                                                                  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "chunking", "progress": 35}             │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │          STEP 4: ROLLING METRIC EXTRACTION (Per Chunk)              │   │
│  │                                                                      │   │
│  │  For each chunk, extract metrics with LLM:                          │   │
│  │                                                                      │   │
│  │  Chunk 1 → LLM → Partial Metrics                                    │   │
│  │  Chunk 2 + Previous → LLM → Merged Metrics                          │   │
│  │  Chunk N + Previous → LLM → FINAL Metrics                           │   │
│  │                                                                      │   │
│  │  LLM Extraction Prompt:                                             │   │
│  │  """                                                                 │   │
│  │  You are extracting performance metrics from an SOP document.       │   │
│  │                                                                      │   │
│  │  PREVIOUS EXTRACTED METRICS:                                        │   │
│  │  {previous_metrics}                                                 │   │
│  │                                                                      │   │
│  │  NEW SECTION TO ANALYZE:                                            │   │
│  │  {chunk_text}                                                       │   │
│  │                                                                      │   │
│  │  Extract and MERGE performance metrics. For each metric include:    │   │
│  │  - metric_id: Unique identifier (snake_case)                        │   │
│  │  - metric_name: Human-readable name                                 │   │
│  │  - description: What this metric measures                           │   │
│  │  - evaluation_method: How to evaluate (from document)               │   │
│  │  - target_value: Expected score/value if specified                  │   │
│  │  - weight: Relative importance (0.0-1.0)                            │   │
│  │  - applicable_roles: Which roles this applies to                    │   │
│  │  - evaluation_criteria: Specific criteria for scoring               │   │
│  │  - source_section: Section where this was found                     │   │
│  │                                                                      │   │
│  │  Return JSON matching SOPMetrics schema.                            │   │
│  │  """                                                                 │   │
│  │                                                                      │   │
│  │  Example Extracted Metric:                                          │   │
│  │  {                                                                  │   │
│  │    "metric_id": "greeting_quality",                                 │   │
│  │    "metric_name": "Greeting Quality",                               │   │
│  │    "description": "Rep properly introduces themselves and company",│   │
│  │    "evaluation_method": "Check if rep states name, company name,   │   │
│  │                         and asks how they can help within 15 sec", │   │
│  │    "target_value": 1.0,                                             │   │
│  │    "weight": 0.15,                                                  │   │
│  │    "applicable_roles": ["sales_rep", "customer_service"],           │   │
│  │    "evaluation_criteria": {                                         │   │
│  │      "excellent": "All elements present, natural delivery",         │   │
│  │      "good": "All elements present, slightly rushed",               │   │
│  │      "needs_improvement": "Missing 1-2 elements",                   │   │
│  │      "poor": "Missing most elements or unprofessional"              │   │
│  │    },                                                               │   │
│  │    "source_section": "Call Opening Guidelines"                      │   │
│  │  }                                                                  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "extracting_metrics", "progress": 55}   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │          STEP 5: METRIC VALIDATION & NORMALIZATION                   │   │
│  │                                                                      │   │
│  │  1. Deduplicate metrics (same metric_id or semantic similarity)     │   │
│  │  2. Validate weight distribution (should sum to ~1.0 per role)      │   │
│  │  3. Ensure all required fields populated                            │   │
│  │  4. Normalize evaluation criteria format                            │   │
│  │  5. Assign default weights where missing                            │   │
│  │                                                                      │   │
│  │  Output: Validated SOPMetricsDocument                               │   │
│  │  {                                                                  │   │
│  │    "sop_id": "sop_abc123",                                          │   │
│  │    "company_id": "acme_roofing",                                    │   │
│  │    "sop_name": "Sales Call Guidelines v2.1",                        │   │
│  │    "sop_type": "sales_sop",                                         │   │
│  │    "target_role": "sales_rep",  // null if company-wide             │   │
│  │    "is_company_wide": false,                                        │   │
│  │    "metrics": [                                                     │   │
│  │      {...}, {...}, {...}  // 10-20 metrics typically                │   │
│  │    ],                                                               │   │
│  │    "total_metrics": 15,                                             │   │
│  │    "version": "2.1",                                                │   │
│  │    "status": "active",                                              │   │
│  │    "created_at": "2026-01-09T10:00:00Z",                            │   │
│  │    "updated_at": "2026-01-09T10:00:00Z"                             │   │
│  │  }                                                                  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "validating_metrics", "progress": 70}   │
│                                   │                                         │
│         ┌─────────────────────────┴──────────────────────────┐             │
│         │                 PARALLEL STORAGE                     │             │
│         │                                                      │             │
│         ▼                                                      ▼             │
│  ┌──────────────────────────┐              ┌──────────────────────────┐    │
│  │  STEP 6A: MONGODB        │              │  STEP 6B: REDIS          │    │
│  │  STORAGE                 │              │  CACHE                   │    │
│  │                          │              │                          │    │
│  │  Collections:            │              │  Keys:                   │    │
│  │  • sop_documents         │              │  • sop:metrics:{company} │    │
│  │  • sop_metrics           │              │    :{role}               │    │
│  │  • sop_chunks            │              │  • sop:active:{company}  │    │
│  │                          │              │  • sop:evaluation_schema │    │
│  │  See "MongoDB Schema"    │              │    :{sop_id}             │    │
│  │  section below           │              │                          │    │
│  │                          │              │  TTL: 24 hours           │    │
│  │                          │              │  (refreshed on access)   │    │
│  └─────────┬────────────────┘              └─────────┬────────────────┘    │
│            │                                          │                     │
│            └──────────────────┬───────────────────────┘                     │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │          STEP 7: RAG INDEXING (Milvus Zilliz Cloud)                 │   │
│  │                                                                      │   │
│  │  Index SOP content for Ask Otto retrieval:                          │   │
│  │                                                                      │   │
│  │  For each chunk:                                                    │   │
│  │  1. Generate embedding (local HuggingFace Sentence Transformers)    │   │
│  │  2. Insert to Milvus with metadata:                                 │   │
│  │     • corpus_type: "sop_document"                                   │   │
│  │     • doc_id: sop_id                                                │   │
│  │     • chunk_id: chunk identifier                                    │   │
│  │     • tenant_id: company_id                                         │   │
│  │     • target_role: role or "all"                                    │   │
│  │     • section_title: section name                                   │   │
│  │                                                                      │   │
│  │  Also index:                                                        │   │
│  │  • Metric definitions (corpus_type: "sop_metric")                   │   │
│  │  • Evaluation criteria (corpus_type: "sop_criteria")                │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   │                                         │
│           Update Redis: {"status": "indexing", "progress": 90}             │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │          STEP 8: FINALIZE & ACTIVATE                                │   │
│  │                                                                      │   │
│  │  1. Mark SOP as "active" in MongoDB                                 │   │
│  │  2. Optionally deactivate previous version                          │   │
│  │  3. Update job status to "completed"                                │   │
│  │  4. Send webhook callback (if provided)                             │   │
│  │  5. Clear old cache entries                                         │   │
│  │                                                                      │   │
│  │  Response:                                                          │   │
│  │  {                                                                   │   │
│  │    "job_id": "sop_job_abc123",                                      │   │
│  │    "status": "completed",                                            │   │
│  │    "sop_id": "sop_abc123",                                          │   │
│  │    "metrics_extracted": 15,                                         │   │
│  │    "chunks_indexed": 12,                                            │   │
│  │    "applicable_roles": ["sales_rep", "customer_service"],           │   │
│  │    "is_company_wide": false                                         │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration with Call Processing (Feature 1)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│           SOP METRICS INTEGRATION IN CALL PROCESSING                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  During STEP 4 of Call Processing (Rolling Summary Generation):            │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   ENHANCED SUMMARY PROMPT                            │   │
│  │                                                                      │   │
│  │  BEFORE (Current Implementation):                                   │   │
│  │  """                                                                 │   │
│  │  Analyze call transcript and generate summary with:                 │   │
│  │  - summary, key_points, objections, qualification                   │   │
│  │  """                                                                 │   │
│  │                                                                      │   │
│  │  AFTER (With SOP Integration):                                      │   │
│  │  """                                                                 │   │
│  │  Analyze call transcript according to company SOP guidelines.       │   │
│  │                                                                      │   │
│  │  SOP METRICS TO EVALUATE:                                           │   │
│  │  {dynamic_sop_metrics}                                              │   │
│  │                                                                      │   │
│  │  For each metric, provide:                                          │   │
│  │  - score: 0.0-1.0                                                   │   │
│  │  - evidence: Quote from transcript supporting score                 │   │
│  │  - improvement_suggestion: If score < target                        │   │
│  │                                                                      │   │
│  │  Output JSON with standard fields PLUS:                             │   │
│  │  sop_evaluation: {                                                  │   │
│  │    sop_id: "...",                                                   │   │
│  │    overall_compliance: 0.0-1.0,                                     │   │
│  │    metric_scores: [...]                                             │   │
│  │  }                                                                   │   │
│  │  """                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   SOP METRICS LOADING FLOW                           │   │
│  │                                                                      │   │
│  │  1. Before summarization, load applicable SOP metrics:              │   │
│  │                                                                      │   │
│  │     def get_applicable_sop_metrics(company_id, rep_role):           │   │
│  │         # Check Redis cache first                                   │   │
│  │         cache_key = f"sop:metrics:{company_id}:{rep_role}"          │   │
│  │         cached = redis.get(cache_key)                               │   │
│  │         if cached:                                                  │   │
│  │             return json.loads(cached)                               │   │
│  │                                                                      │   │
│  │         # Query MongoDB for active SOP                              │   │
│  │         sop = db.sop_metrics.find_one({                             │   │
│  │             "company_id": company_id,                               │   │
│  │             "status": "active",                                     │   │
│  │             "$or": [                                                │   │
│  │                 {"target_role": rep_role},                          │   │
│  │                 {"is_company_wide": True}                           │   │
│  │             ]                                                        │   │
│  │         })                                                          │   │
│  │                                                                      │   │
│  │         # Cache and return                                          │   │
│  │         redis.setex(cache_key, 86400, json.dumps(sop))              │   │
│  │         return sop                                                  │   │
│  │                                                                      │   │
│  │  2. Inject metrics into summary generation prompt                   │   │
│  │  3. Validate SOP scores in response                                 │   │
│  │  4. Store SOP evaluation with call summary                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   CHUNK-LEVEL SOP EVALUATION                         │   │
│  │                                                                      │   │
│  │  For each transcript chunk:                                         │   │
│  │  • Evaluate applicable metrics (some may span chunks)               │   │
│  │  • Track partial evidence                                           │   │
│  │  • Accumulate scores                                                │   │
│  │                                                                      │   │
│  │  For final summary:                                                 │   │
│  │  • Merge chunk evaluations                                          │   │
│  │  • Calculate weighted overall compliance                            │   │
│  │  • Generate improvement recommendations                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                   ENHANCED SUMMARY OUTPUT                            │   │
│  │                                                                      │   │
│  │  {                                                                   │   │
│  │    "call_id": "5002",                                               │   │
│  │    "summary": {...},                                                │   │
│  │    "compliance": {...},                                             │   │
│  │    "objections": {...},                                             │   │
│  │    "qualification": {...},                                          │   │
│  │                                                                      │   │
│  │    // NEW: SOP-based evaluation                                     │   │
│  │    "sop_evaluation": {                                              │   │
│  │      "sop_id": "sop_abc123",                                        │   │
│  │      "sop_name": "Sales Call Guidelines v2.1",                      │   │
│  │      "overall_compliance": 0.82,                                    │   │
│  │      "metric_scores": [                                             │   │
│  │        {                                                            │   │
│  │          "metric_id": "greeting_quality",                           │   │
│  │          "metric_name": "Greeting Quality",                         │   │
│  │          "score": 0.9,                                              │   │
│  │          "target": 1.0,                                             │   │
│  │          "weight": 0.15,                                            │   │
│  │          "weighted_score": 0.135,                                   │   │
│  │          "evidence": "Rep said 'Hi, this is Travis from...'",       │   │
│  │          "rating": "excellent"                                      │   │
│  │        },                                                           │   │
│  │        {                                                            │   │
│  │          "metric_id": "needs_assessment",                           │   │
│  │          "metric_name": "Needs Assessment",                         │   │
│  │          "score": 0.7,                                              │   │
│  │          "target": 1.0,                                             │   │
│  │          "weight": 0.20,                                            │   │
│  │          "weighted_score": 0.14,                                    │   │
│  │          "evidence": "Asked about roof issue but didn't...",        │   │
│  │          "rating": "good",                                          │   │
│  │          "improvement": "Ask about budget and timeline earlier"     │   │
│  │        }                                                            │   │
│  │      ],                                                             │   │
│  │      "top_strengths": [                                             │   │
│  │        "Excellent greeting and rapport building",                   │   │
│  │        "Professional tone throughout"                               │   │
│  │      ],                                                             │   │
│  │      "improvement_areas": [                                         │   │
│  │        "Probe deeper during needs assessment",                      │   │
│  │        "Address objections more proactively"                        │   │
│  │      ],                                                             │   │
│  │      "evaluated_at": "2026-01-09T10:32:00Z"                         │   │
│  │    }                                                                │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Integration with Ask Otto (Feature 3)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              SOP INTEGRATION IN ASK OTTO CHAT                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               ENHANCED LANGGRAPH ROUTING                             │   │
│  │                                                                      │   │
│  │  NODE 1: CLASSIFY & EXTRACT (Updated)                               │   │
│  │                                                                      │   │
│  │  New Intent Types:                                                  │   │
│  │  • "query_sop_guidelines" - Questions about procedures              │   │
│  │  • "query_sop_metrics" - Questions about evaluation criteria        │   │
│  │  • "evaluate_against_sop" - Evaluate specific call vs SOP           │   │
│  │                                                                      │   │
│  │  Example Classifications:                                           │   │
│  │  "How should reps handle pricing objections?"                       │   │
│  │    → intent: "query_sop_guidelines"                                 │   │
│  │    → requires: {sop_search: true}                                   │   │
│  │                                                                      │   │
│  │  "What metrics is Travis evaluated on?"                             │   │
│  │    → intent: "query_sop_metrics"                                    │   │
│  │    → requires: {sop_metrics: true, customer_context: false}         │   │
│  │                                                                      │   │
│  │  "Did Kevin's call follow our greeting protocol?"                   │   │
│  │    → intent: "evaluate_against_sop"                                 │   │
│  │    → requires: {sop_search: true, rag_search: true}                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               NEW TOOL: SOP SEARCH                                   │   │
│  │                                                                      │   │
│  │  async def sop_search_tool(query: str, company_id: str):            │   │
│  │      """                                                            │   │
│  │      Search SOP documents for relevant guidelines.                  │   │
│  │      """                                                            │   │
│  │      # Generate embedding                                           │   │
│  │      embedding = await get_embedding(query)                         │   │
│  │                                                                      │   │
│  │      # Search Milvus for SOP content                                │   │
│  │      results = milvus.search(                                       │   │
│  │          collection_name="otto_intelligence_v1",                    │   │
│  │          data=[embedding],                                          │   │
│  │          filter=f"""                                                │   │
│  │              tenant_id == '{company_id}' &&                         │   │
│  │              corpus_type in ['sop_document', 'sop_metric',          │   │
│  │                              'sop_criteria']                        │   │
│  │          """,                                                       │   │
│  │          limit=5,                                                   │   │
│  │          output_fields=["doc_id", "text_content", "section_title",  │   │
│  │                        "target_role", "corpus_type"]                │   │
│  │      )                                                              │   │
│  │                                                                      │   │
│  │      return results                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               NEW TOOL: SOP METRICS LOOKUP                           │   │
│  │                                                                      │   │
│  │  async def sop_metrics_tool(company_id: str, role: str = None):     │   │
│  │      """                                                            │   │
│  │      Get active SOP metrics for company/role.                       │   │
│  │      """                                                            │   │
│  │      # Check Redis cache                                            │   │
│  │      cache_key = f"sop:metrics:{company_id}:{role or 'all'}"        │   │
│  │      cached = await redis.get(cache_key)                            │   │
│  │      if cached:                                                     │   │
│  │          return json.loads(cached)                                  │   │
│  │                                                                      │   │
│  │      # Query MongoDB                                                │   │
│  │      query = {                                                      │   │
│  │          "company_id": company_id,                                  │   │
│  │          "status": "active"                                         │   │
│  │      }                                                              │   │
│  │      if role:                                                       │   │
│  │          query["$or"] = [                                           │   │
│  │              {"target_role": role},                                 │   │
│  │              {"is_company_wide": True}                              │   │
│  │          ]                                                          │   │
│  │                                                                      │   │
│  │      sop_metrics = await db.sop_metrics.find_one(query)             │   │
│  │                                                                      │   │
│  │      # Cache and return                                             │   │
│  │      await redis.setex(cache_key, 86400, json.dumps(sop_metrics))   │   │
│  │      return sop_metrics                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               UPDATED GRAPH DEFINITION                               │   │
│  │                                                                      │   │
│  │  # Add new nodes                                                    │   │
│  │  workflow.add_node("sop_search", sop_search_node)                   │   │
│  │  workflow.add_node("sop_metrics", sop_metrics_node)                 │   │
│  │                                                                      │   │
│  │  # Updated routing (parallel with other tools)                      │   │
│  │  workflow.add_edge("classify", "customer_context")                  │   │
│  │  workflow.add_edge("classify", "rag_search")                        │   │
│  │  workflow.add_edge("classify", "sop_search")      # NEW             │   │
│  │  workflow.add_edge("classify", "sop_metrics")     # NEW             │   │
│  │  workflow.add_edge("classify", "analytics")                         │   │
│  │                                                                      │   │
│  │  # All tools merge                                                  │   │
│  │  workflow.add_edge("sop_search", "merge")                           │   │
│  │  workflow.add_edge("sop_metrics", "merge")                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               ENHANCED RESPONSE SYNTHESIS                            │   │
│  │                                                                      │   │
│  │  Updated system prompt includes:                                    │   │
│  │  """                                                                 │   │
│  │  You are Otto, an AI sales assistant with access to company SOPs.   │   │
│  │                                                                      │   │
│  │  When answering questions about procedures or evaluations:          │   │
│  │  1. Reference specific SOP sections                                 │   │
│  │  2. Cite metric definitions when discussing performance             │   │
│  │  3. Explain evaluation criteria from the SOP                        │   │
│  │  4. If SOP guidance exists, prioritize it over general knowledge    │   │
│  │                                                                      │   │
│  │  SOP Context Retrieved:                                             │   │
│  │  {sop_context}                                                      │   │
│  │                                                                      │   │
│  │  Active Metrics:                                                    │   │
│  │  {sop_metrics}                                                      │   │
│  │  """                                                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               EXAMPLE INTERACTIONS                                   │   │
│  │                                                                      │   │
│  │  User: "How should reps handle pricing objections?"                 │   │
│  │                                                                      │   │
│  │  Otto: "According to your Sales SOP (Section 4.2 - Objection        │   │
│  │  Handling), reps should:                                            │   │
│  │                                                                      │   │
│  │  1. Acknowledge the concern: 'I understand budget is important'     │   │
│  │  2. Reframe value: Focus on ROI and long-term savings               │   │
│  │  3. Offer options: Present financing or payment plans               │   │
│  │  4. Use social proof: Reference similar customers                   │   │
│  │                                                                      │   │
│  │  This is evaluated under the 'objection_handling' metric with       │   │
│  │  a weight of 20%. Target score is 0.8."                             │   │
│  │                                                                      │   │
│  │  Sources: [Sales SOP v2.1 - Section 4.2]                            │   │
│  │  ─────────────────────────────────────────                          │   │
│  │                                                                      │   │
│  │  User: "How did Travis do on his last call with Kevin?"             │   │
│  │                                                                      │   │
│  │  Otto: "Travis's call with Kevin (Call #5002) received an           │   │
│  │  overall SOP compliance score of 82%.                               │   │
│  │                                                                      │   │
│  │  Strengths:                                                         │   │
│  │  ✓ Greeting Quality: 90% (excellent)                                │   │
│  │  ✓ Active Listening: 85% (good)                                     │   │
│  │                                                                      │   │
│  │  Areas to Improve:                                                  │   │
│  │  ○ Needs Assessment: 70% - Should ask about budget earlier          │   │
│  │  ○ Objection Handling: 65% - Timeline objection not fully addressed │   │
│  │                                                                      │   │
│  │  Would you like coaching tips for these areas?"                     │   │
│  │                                                                      │   │
│  │  Sources: [Call #5002, Sales SOP v2.1]                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Upload SOP Document

**Endpoint:** `POST /api/v1/sop/documents/upload`

**Description:** Upload a PDF or Word document for SOP processing. Returns immediately with job ID.

**Request Headers:**
```http
X-API-Key: {api_key}
Content-Type: multipart/form-data
```

**Request Body (multipart/form-data):**
```
file: <PDF or DOCX file>
company_id: "acme_roofing"
target_role: "sales_rep"  // Optional - null for company-wide
sop_name: "Sales Call Guidelines v2.1"
metadata: {"department": "sales", "version": "2.1"}  // Optional JSON
webhook_url: "https://callback.url"  // Optional
```

**Response (202 Accepted):**
```json
{
  "job_id": "sop_job_abc123def456",
  "status": "queued",
  "message": "SOP document processing initiated",
  "file_name": "sales_sop_v2.1.pdf",
  "file_size": 245678,
  "status_url": "/api/v1/sop/documents/status/sop_job_abc123def456",
  "created_at": "2026-01-09T10:00:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid file type or missing required fields
- `401 Unauthorized` - Invalid API key
- `413 Payload Too Large` - File exceeds 50MB limit
- `422 Unprocessable Entity` - Document is not a valid SOP

---

### 2. Check Processing Status

**Endpoint:** `GET /api/v1/sop/documents/status/{job_id}`

**Description:** Poll the processing status of SOP document upload.

**Response (200 OK) - Processing:**
```json
{
  "job_id": "sop_job_abc123def456",
  "status": "processing",
  "progress": {
    "percent": 55,
    "current_step": "extracting_metrics",
    "steps_completed": ["uploaded", "extracted", "validated", "chunked"],
    "steps_remaining": ["extracting_metrics", "validating_metrics", "storing", "indexing"]
  },
  "started_at": "2026-01-09T10:00:05Z",
  "updated_at": "2026-01-09T10:02:30Z"
}
```

**Response (200 OK) - Completed:**
```json
{
  "job_id": "sop_job_abc123def456",
  "status": "completed",
  "progress": {
    "percent": 100,
    "current_step": "completed"
  },
  "results": {
    "sop_id": "sop_abc123",
    "sop_name": "Sales Call Guidelines v2.1",
    "sop_type": "sales_sop",
    "is_company_wide": false,
    "target_role": "sales_rep",
    "metrics_extracted": 15,
    "chunks_indexed": 12,
    "page_count": 15,
    "word_count": 8500
  },
  "started_at": "2026-01-09T10:00:05Z",
  "completed_at": "2026-01-09T10:05:30Z",
  "duration_seconds": 325
}
```

**Response (200 OK) - Failed (Not SOP):**
```json
{
  "job_id": "sop_job_abc123def456",
  "status": "failed",
  "error": {
    "code": "INVALID_SOP_DOCUMENT",
    "message": "Please upload a valid SOP document",
    "details": {
      "rejection_reason": "Document appears to be a marketing brochure, not a Standard Operating Procedure",
      "confidence": 0.92,
      "suggestions": [
        "Ensure document contains procedural guidelines",
        "Include role-specific instructions",
        "Add measurable performance metrics or evaluation criteria"
      ]
    }
  },
  "started_at": "2026-01-09T10:00:05Z",
  "failed_at": "2026-01-09T10:01:15Z"
}
```

---

### 3. Get SOP Metrics

**Endpoint:** `GET /api/v1/sop/metrics/{company_id}`

**Description:** Retrieve active SOP metrics for a company.

**Query Parameters:**
- `role` (optional): Filter by target role
- `sop_id` (optional): Get specific SOP version
- `include_inactive` (optional): Include deactivated SOPs

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "active_sops": [
    {
      "sop_id": "sop_abc123",
      "sop_name": "Sales Call Guidelines v2.1",
      "sop_type": "sales_sop",
      "target_role": "sales_rep",
      "is_company_wide": false,
      "version": "2.1",
      "total_metrics": 15,
      "metrics": [
        {
          "metric_id": "greeting_quality",
          "metric_name": "Greeting Quality",
          "description": "Rep properly introduces themselves and company",
          "evaluation_method": "Check if rep states name, company, purpose within 15 seconds",
          "target_value": 1.0,
          "weight": 0.15,
          "applicable_roles": ["sales_rep", "customer_service"],
          "evaluation_criteria": {
            "excellent": "All elements present, natural delivery",
            "good": "All elements present, slightly rushed",
            "needs_improvement": "Missing 1-2 elements",
            "poor": "Missing most elements"
          }
        },
        {
          "metric_id": "needs_assessment",
          "metric_name": "Needs Assessment",
          "description": "Rep thoroughly understands customer requirements",
          "evaluation_method": "Verify rep asks about problem, timeline, budget, decision makers",
          "target_value": 1.0,
          "weight": 0.20,
          "applicable_roles": ["sales_rep"],
          "evaluation_criteria": {
            "excellent": "All BANT questions covered naturally",
            "good": "3 of 4 BANT areas covered",
            "needs_improvement": "Only 2 areas covered",
            "poor": "Minimal discovery"
          }
        }
        // ... more metrics
      ],
      "created_at": "2026-01-09T10:05:30Z",
      "status": "active"
    }
  ],
  "company_wide_sops": [
    {
      "sop_id": "sop_xyz789",
      "sop_name": "Customer Communication Standards",
      "sop_type": "general_sop",
      "is_company_wide": true,
      "total_metrics": 8,
      "metrics": [...]
    }
  ]
}
```

---

### 4. Get SOP Document

**Endpoint:** `GET /api/v1/sop/documents/{sop_id}`

**Description:** Get SOP document details and extracted content.

**Response (200 OK):**
```json
{
  "sop_id": "sop_abc123",
  "company_id": "acme_roofing",
  "sop_name": "Sales Call Guidelines v2.1",
  "sop_type": "sales_sop",
  "target_role": "sales_rep",
  "is_company_wide": false,
  "file_info": {
    "original_filename": "sales_sop_v2.1.pdf",
    "file_size": 245678,
    "file_type": "application/pdf",
    "page_count": 15,
    "word_count": 8500,
    "s3_url": "s3://otto-sop-documents/acme_roofing/sop_abc123/sales_sop_v2.1.pdf"
  },
  "sections": [
    {
      "title": "Introduction",
      "page_start": 1,
      "page_end": 2
    },
    {
      "title": "Call Opening Guidelines",
      "page_start": 3,
      "page_end": 5
    },
    {
      "title": "Needs Assessment Process",
      "page_start": 6,
      "page_end": 8
    }
  ],
  "metrics_summary": {
    "total_metrics": 15,
    "by_category": {
      "opening": 3,
      "discovery": 4,
      "presentation": 3,
      "objection_handling": 3,
      "closing": 2
    }
  },
  "status": "active",
  "version": "2.1",
  "created_at": "2026-01-09T10:05:30Z",
  "updated_at": "2026-01-09T10:05:30Z"
}
```

---

### 5. Update SOP Status

**Endpoint:** `PATCH /api/v1/sop/documents/{sop_id}/status`

**Description:** Activate or deactivate an SOP document.

**Request Body:**
```json
{
  "status": "inactive",
  "reason": "Replaced by v2.2"
}
```

**Response (200 OK):**
```json
{
  "sop_id": "sop_abc123",
  "previous_status": "active",
  "new_status": "inactive",
  "updated_at": "2026-01-09T12:00:00Z"
}
```

---

### 6. List Company SOPs

**Endpoint:** `GET /api/v1/sop/documents`

**Description:** List all SOP documents for a company.

**Query Parameters:**
- `company_id` (required): Company identifier
- `status` (optional): Filter by status (active/inactive)
- `target_role` (optional): Filter by role
- `page` (optional): Page number
- `limit` (optional): Results per page

**Response (200 OK):**
```json
{
  "company_id": "acme_roofing",
  "total": 3,
  "page": 1,
  "limit": 20,
  "documents": [
    {
      "sop_id": "sop_abc123",
      "sop_name": "Sales Call Guidelines v2.1",
      "sop_type": "sales_sop",
      "target_role": "sales_rep",
      "status": "active",
      "metrics_count": 15,
      "created_at": "2026-01-09T10:05:30Z"
    },
    {
      "sop_id": "sop_xyz789",
      "sop_name": "Customer Communication Standards",
      "sop_type": "general_sop",
      "is_company_wide": true,
      "status": "active",
      "metrics_count": 8,
      "created_at": "2026-01-05T14:30:00Z"
    }
  ]
}
```

---

### 7. Delete SOP Document

**Endpoint:** `DELETE /api/v1/sop/documents/{sop_id}`

**Description:** Delete an SOP document and all associated data.

**Response (204 No Content)**

---

## MongoDB Collections

### Collection: `sop_documents`

```javascript
{
  _id: ObjectId("..."),
  sop_id: "sop_abc123",
  company_id: "acme_roofing",
  sop_name: "Sales Call Guidelines v2.1",
  sop_type: "sales_sop",  // "sales_sop" | "support_sop" | "general_sop"
  target_role: "sales_rep",  // null if company-wide
  is_company_wide: false,
  version: "2.1",
  status: "active",  // "active" | "inactive" | "processing" | "failed"
  
  file_info: {
    original_filename: "sales_sop_v2.1.pdf",
    file_type: "application/pdf",
    file_size: 245678,
    file_hash: "sha256:abc123...",
    s3_key: "acme_roofing/sop_abc123/sales_sop_v2.1.pdf",
    page_count: 15,
    word_count: 8500
  },
  
  extracted_content: {
    raw_text: "...",  // Full extracted text
    sections: [
      {
        title: "Introduction",
        content: "...",
        page_start: 1,
        page_end: 2
      }
    ],
    tables: [
      {
        title: "Metric Weights",
        headers: ["Metric", "Weight", "Target"],
        rows: [...]
      }
    ]
  },
  
  processing_metadata: {
    job_id: "sop_job_abc123",
    started_at: ISODate("2026-01-09T10:00:05Z"),
    completed_at: ISODate("2026-01-09T10:05:30Z"),
    duration_seconds: 325,
    chunks_created: 12,
    vectors_indexed: 15
  },
  
  metadata: {
    department: "sales",
    effective_date: "2026-01-01",
    author: "Sales Manager",
    uploaded_by: "user_123"
  },
  
  created_at: ISODate("2026-01-09T10:05:30Z"),
  updated_at: ISODate("2026-01-09T10:05:30Z")
}
```

**Indexes:**
- `sop_id` (unique)
- `{company_id: 1, status: 1}`
- `{company_id: 1, target_role: 1, status: 1}`
- `{company_id: 1, is_company_wide: 1, status: 1}`

---

### Collection: `sop_metrics`

```javascript
{
  _id: ObjectId("..."),
  sop_id: "sop_abc123",
  company_id: "acme_roofing",
  target_role: "sales_rep",
  is_company_wide: false,
  status: "active",
  
  metrics: [
    {
      metric_id: "greeting_quality",
      metric_name: "Greeting Quality",
      description: "Rep properly introduces themselves and company",
      evaluation_method: "Check if rep states name, company name, and asks how they can help within 15 seconds",
      target_value: 1.0,
      weight: 0.15,
      applicable_roles: ["sales_rep", "customer_service"],
      evaluation_criteria: {
        excellent: {
          score_range: [0.9, 1.0],
          description: "All elements present, natural delivery"
        },
        good: {
          score_range: [0.7, 0.89],
          description: "All elements present, slightly rushed"
        },
        needs_improvement: {
          score_range: [0.5, 0.69],
          description: "Missing 1-2 elements"
        },
        poor: {
          score_range: [0.0, 0.49],
          description: "Missing most elements or unprofessional"
        }
      },
      source_section: "Call Opening Guidelines",
      category: "opening"
    },
    {
      metric_id: "needs_assessment",
      metric_name: "Needs Assessment",
      description: "Rep thoroughly understands customer requirements",
      evaluation_method: "Verify rep asks about: problem details, timeline, budget, decision makers",
      target_value: 1.0,
      weight: 0.20,
      applicable_roles: ["sales_rep"],
      evaluation_criteria: {...},
      source_section: "Discovery Process",
      category: "discovery"
    }
    // ... more metrics
  ],
  
  total_metrics: 15,
  total_weight: 1.0,  // Should sum to ~1.0
  
  categories: ["opening", "discovery", "presentation", "objection_handling", "closing"],
  
  created_at: ISODate("2026-01-09T10:05:30Z"),
  updated_at: ISODate("2026-01-09T10:05:30Z")
}
```

**Indexes:**
- `{sop_id: 1}` (unique)
- `{company_id: 1, status: 1}`
- `{company_id: 1, target_role: 1, status: 1}`

---

### Collection: `sop_chunks`

```javascript
{
  _id: ObjectId("..."),
  chunk_id: "sop_chunk_abc123_001",
  sop_id: "sop_abc123",
  company_id: "acme_roofing",
  
  chunk_index: 1,
  chunk_type: "procedure",  // "procedure" | "metric" | "criteria" | "general"
  section_title: "Call Opening Guidelines",
  parent_section: "Sales Call Process",
  
  text: "When answering a sales call, the representative should...",
  token_count: 2500,
  
  milvus_id: "vec_sop_abc123_chunk_001",
  
  created_at: ISODate("2026-01-09T10:05:30Z")
}
```

**Indexes:**
- `chunk_id` (unique)
- `{sop_id: 1, chunk_index: 1}`
- `{company_id: 1}`

---

### Updated Collection: `call_summaries` (Enhanced)

```javascript
{
  _id: ObjectId("..."),
  call_id: "5002",
  company_id: "acme_roofing",
  
  // ... existing fields ...
  
  // NEW: SOP Evaluation
  sop_evaluation: {
    sop_id: "sop_abc123",
    sop_name: "Sales Call Guidelines v2.1",
    sop_version: "2.1",
    
    overall_compliance: 0.82,
    
    metric_scores: [
      {
        metric_id: "greeting_quality",
        metric_name: "Greeting Quality",
        score: 0.9,
        target: 1.0,
        weight: 0.15,
        weighted_score: 0.135,
        rating: "excellent",
        evidence: "Rep said 'Hi, this is Travis from Arizona Roofers, how can I help you today?'",
        improvement_suggestion: null
      },
      {
        metric_id: "needs_assessment",
        metric_name: "Needs Assessment",
        score: 0.7,
        target: 1.0,
        weight: 0.20,
        weighted_score: 0.14,
        rating: "good",
        evidence: "Asked about roof issue and timeline but did not inquire about budget",
        improvement_suggestion: "Ask about budget constraints earlier in the conversation"
      }
    ],
    
    top_strengths: [
      "Excellent greeting and rapport building",
      "Professional tone throughout the call"
    ],
    
    improvement_areas: [
      {
        area: "Needs Assessment",
        suggestion: "Probe deeper during discovery to understand budget constraints",
        related_metrics: ["needs_assessment", "budget_discussion"]
      }
    ],
    
    evaluated_at: ISODate("2026-01-09T10:32:00Z")
  }
}
```

---

## Redis Cache Structure

### Active SOP Metrics Cache

```
Key: sop:metrics:{company_id}:{role}
Value: {
  "sop_id": "sop_abc123",
  "sop_name": "Sales Call Guidelines v2.1",
  "metrics": [...],
  "total_weight": 1.0,
  "cached_at": "2026-01-09T10:05:30Z"
}
TTL: 86400 seconds (24 hours)
Refresh: On access if > 1 hour old
```

### Active SOP List Cache

```
Key: sop:active:{company_id}
Value: [
  {
    "sop_id": "sop_abc123",
    "target_role": "sales_rep",
    "is_company_wide": false
  },
  {
    "sop_id": "sop_xyz789",
    "target_role": null,
    "is_company_wide": true
  }
]
TTL: 3600 seconds (1 hour)
```

### Evaluation Schema Cache

```
Key: sop:evaluation_schema:{sop_id}
Value: {
  "metrics": [...],
  "categories": [...],
  "prompt_template": "...",
  "validation_rules": {...}
}
TTL: 86400 seconds (24 hours)
```

### Job Status Cache

```
Key: sop:job:{job_id}:status
Value: {
  "job_id": "sop_job_abc123",
  "status": "processing",
  "progress": {...},
  "started_at": "...",
  "updated_at": "..."
}
TTL: 86400 seconds (24 hours)
```

---

## Milvus Zilliz Cloud Schema (Extended)

### New corpus_type Values

Add to existing `otto_intelligence_v1` collection:

```python
# New corpus types for SOP content
corpus_types = [
    "call",           # Existing: Call transcripts
    "call_summary",   # Existing: Call summaries
    "chunk_summary",  # Existing: Chunk summaries
    "sop_document",   # NEW: SOP document chunks
    "sop_metric",     # NEW: Individual metric definitions
    "sop_criteria",   # NEW: Evaluation criteria
    "faq"             # Existing: FAQ documents
]
```

### SOP Vector Entry

```python
{
    "id": "vec_sop_abc123_chunk_001",
    "tenant_id": "acme_roofing",
    "corpus_type": "sop_document",
    "doc_id": "sop_abc123",
    "chunk_id": "sop_chunk_abc123_001",
    "text_content": "When answering a sales call...",
    "summary_json": None,
    "created_at": 1736416530,
    "embedding": [...],  # 384 dimensions (HuggingFace all-MiniLM-L6-v2)
    
    # Dynamic fields
    "target_role": "sales_rep",
    "section_title": "Call Opening Guidelines",
    "sop_type": "sales_sop",
    "sop_version": "2.1"
}
```

### SOP Metric Vector Entry

```python
{
    "id": "vec_sop_metric_abc123_greeting",
    "tenant_id": "acme_roofing",
    "corpus_type": "sop_metric",
    "doc_id": "sop_abc123",
    "chunk_id": None,
    "text_content": "Greeting Quality: Rep properly introduces themselves...",
    "summary_json": {
        "metric_id": "greeting_quality",
        "metric_name": "Greeting Quality",
        "weight": 0.15,
        "evaluation_criteria": {...}
    },
    "created_at": 1736416530,
    "embedding": [...],
    
    "target_role": "sales_rep",
    "metric_category": "opening"
}
```

---

## Processing Algorithms

### Document Chunking Algorithm

```python
def chunk_sop_document(extracted_content: dict, max_tokens: int = 8000) -> List[dict]:
    """
    Chunk SOP document with context-aware splitting.
    
    Strategy:
    1. Try to chunk by sections first
    2. If section too large, split by paragraphs
    3. If still too large, split by tokens with overlap
    """
    chunks = []
    chunk_index = 0
    overlap_tokens = 500
    
    for section in extracted_content["sections"]:
        section_tokens = count_tokens(section["content"])
        
        if section_tokens <= max_tokens:
            # Section fits in one chunk
            chunks.append({
                "chunk_id": f"sop_chunk_{sop_id}_{chunk_index:03d}",
                "chunk_index": chunk_index,
                "section_title": section["title"],
                "text": section["content"],
                "token_count": section_tokens,
                "chunk_type": classify_chunk_type(section["content"])
            })
            chunk_index += 1
        else:
            # Section needs splitting
            paragraphs = split_into_paragraphs(section["content"])
            current_chunk = ""
            current_tokens = 0
            
            for para in paragraphs:
                para_tokens = count_tokens(para)
                
                if current_tokens + para_tokens <= max_tokens:
                    current_chunk += para + "\n\n"
                    current_tokens += para_tokens
                else:
                    # Save current chunk
                    if current_chunk:
                        chunks.append({
                            "chunk_id": f"sop_chunk_{sop_id}_{chunk_index:03d}",
                            "chunk_index": chunk_index,
                            "section_title": section["title"],
                            "text": current_chunk.strip(),
                            "token_count": current_tokens,
                            "chunk_type": classify_chunk_type(current_chunk)
                        })
                        chunk_index += 1
                    
                    # Handle oversized paragraph
                    if para_tokens > max_tokens:
                        # Token-based splitting with overlap
                        para_chunks = split_by_tokens(para, max_tokens, overlap_tokens)
                        for pc in para_chunks:
                            chunks.append({
                                "chunk_id": f"sop_chunk_{sop_id}_{chunk_index:03d}",
                                "chunk_index": chunk_index,
                                "section_title": section["title"],
                                "text": pc,
                                "token_count": count_tokens(pc),
                                "chunk_type": classify_chunk_type(pc)
                            })
                            chunk_index += 1
                        current_chunk = ""
                        current_tokens = 0
                    else:
                        current_chunk = para + "\n\n"
                        current_tokens = para_tokens
            
            # Don't forget last chunk
            if current_chunk:
                chunks.append({
                    "chunk_id": f"sop_chunk_{sop_id}_{chunk_index:03d}",
                    "chunk_index": chunk_index,
                    "section_title": section["title"],
                    "text": current_chunk.strip(),
                    "token_count": current_tokens,
                    "chunk_type": classify_chunk_type(current_chunk)
                })
                chunk_index += 1
    
    return chunks


def classify_chunk_type(text: str) -> str:
    """Classify chunk content type."""
    text_lower = text.lower()
    
    if any(kw in text_lower for kw in ["metric", "score", "evaluate", "measure", "kpi"]):
        return "metric"
    elif any(kw in text_lower for kw in ["criteria", "rating", "excellent", "good", "poor"]):
        return "criteria"
    elif any(kw in text_lower for kw in ["step", "procedure", "should", "must", "guideline"]):
        return "procedure"
    else:
        return "general"
```

### Rolling Metric Extraction Algorithm

```python
async def extract_metrics_rolling(chunks: List[dict], sop_id: str) -> dict:
    """
    Extract metrics from SOP chunks using rolling context.
    
    Each chunk builds on previous extraction to:
    1. Discover new metrics
    2. Refine existing metric definitions
    3. Merge duplicate metrics
    """
    accumulated_metrics = []
    
    for i, chunk in enumerate(chunks):
        # Build context from previous extraction
        context = {
            "previous_metrics": accumulated_metrics,
            "chunk_text": chunk["text"],
            "chunk_index": i + 1,
            "total_chunks": len(chunks),
            "section_title": chunk["section_title"]
        }
        
        # LLM extraction prompt
        prompt = build_metric_extraction_prompt(context)
        
        # Call LLM
        response = await llm_service.generate(
            prompt=prompt,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        # Parse response
        extracted = json.loads(response)
        
        # Merge with accumulated metrics
        accumulated_metrics = merge_metrics(
            accumulated_metrics,
            extracted.get("new_metrics", []),
            extracted.get("updated_metrics", [])
        )
        
        # Update progress
        await update_job_progress(
            sop_id,
            percent=35 + int((i + 1) / len(chunks) * 35),
            step=f"extracting_metrics_chunk_{i + 1}"
        )
    
    # Final validation and normalization
    validated_metrics = validate_and_normalize_metrics(accumulated_metrics)
    
    return {
        "sop_id": sop_id,
        "metrics": validated_metrics,
        "total_metrics": len(validated_metrics)
    }


def merge_metrics(existing: List[dict], new: List[dict], updates: List[dict]) -> List[dict]:
    """Merge new and updated metrics with existing."""
    metrics_map = {m["metric_id"]: m for m in existing}
    
    # Apply updates to existing metrics
    for update in updates:
        metric_id = update.get("metric_id")
        if metric_id in metrics_map:
            # Merge update into existing metric
            metrics_map[metric_id] = {**metrics_map[metric_id], **update}
    
    # Add new metrics (with deduplication)
    for new_metric in new:
        metric_id = new_metric.get("metric_id")
        if metric_id not in metrics_map:
            # Check semantic similarity to existing
            similar = find_similar_metric(new_metric, list(metrics_map.values()))
            if similar:
                # Merge with similar metric
                metrics_map[similar["metric_id"]] = merge_similar_metrics(
                    metrics_map[similar["metric_id"]],
                    new_metric
                )
            else:
                metrics_map[metric_id] = new_metric
    
    return list(metrics_map.values())
```

### SOP-Aware Call Evaluation Algorithm

```python
async def evaluate_call_against_sop(
    transcript_chunk: str,
    sop_metrics: List[dict],
    previous_evaluations: List[dict] = None
) -> dict:
    """
    Evaluate call transcript chunk against SOP metrics.
    """
    # Build evaluation prompt
    prompt = f"""
    You are evaluating a sales call against company SOP metrics.
    
    SOP METRICS TO EVALUATE:
    {json.dumps(sop_metrics, indent=2)}
    
    {"PREVIOUS CHUNK EVALUATIONS:" + json.dumps(previous_evaluations) if previous_evaluations else ""}
    
    TRANSCRIPT CHUNK:
    {transcript_chunk}
    
    For each applicable metric:
    1. Score from 0.0 to 1.0 based on evaluation_criteria
    2. Provide evidence quote from transcript
    3. Suggest improvement if score < target
    4. Determine rating (excellent/good/needs_improvement/poor)
    
    Some metrics may not be evaluable from this chunk - mark as "not_applicable"
    
    Return JSON:
    {{
      "metric_scores": [
        {{
          "metric_id": "...",
          "score": 0.0-1.0,
          "evidence": "...",
          "rating": "...",
          "improvement_suggestion": "..." or null,
          "applicable": true/false
        }}
      ],
      "chunk_observations": ["..."]
    }}
    """
    
    response = await llm_service.generate(
        prompt=prompt,
        max_tokens=2000,
        response_format={"type": "json_object"}
    )
    
    return json.loads(response)


async def merge_chunk_evaluations(chunk_evaluations: List[dict], sop_metrics: List[dict]) -> dict:
    """
    Merge evaluations from all chunks into final SOP compliance score.
    """
    # Aggregate scores per metric
    metric_aggregates = {}
    
    for chunk_eval in chunk_evaluations:
        for score_entry in chunk_eval.get("metric_scores", []):
            if not score_entry.get("applicable", True):
                continue
                
            metric_id = score_entry["metric_id"]
            if metric_id not in metric_aggregates:
                metric_aggregates[metric_id] = {
                    "scores": [],
                    "evidences": [],
                    "suggestions": []
                }
            
            metric_aggregates[metric_id]["scores"].append(score_entry["score"])
            if score_entry.get("evidence"):
                metric_aggregates[metric_id]["evidences"].append(score_entry["evidence"])
            if score_entry.get("improvement_suggestion"):
                metric_aggregates[metric_id]["suggestions"].append(
                    score_entry["improvement_suggestion"]
                )
    
    # Calculate final scores
    final_scores = []
    total_weighted_score = 0
    total_weight = 0
    
    for metric in sop_metrics:
        metric_id = metric["metric_id"]
        agg = metric_aggregates.get(metric_id)
        
        if agg and agg["scores"]:
            # Average score across chunks
            avg_score = sum(agg["scores"]) / len(agg["scores"])
            weight = metric.get("weight", 0.1)
            weighted_score = avg_score * weight
            
            total_weighted_score += weighted_score
            total_weight += weight
            
            final_scores.append({
                "metric_id": metric_id,
                "metric_name": metric["metric_name"],
                "score": round(avg_score, 2),
                "target": metric.get("target_value", 1.0),
                "weight": weight,
                "weighted_score": round(weighted_score, 3),
                "rating": get_rating(avg_score, metric.get("evaluation_criteria", {})),
                "evidence": agg["evidences"][0] if agg["evidences"] else None,
                "improvement_suggestion": agg["suggestions"][0] if agg["suggestions"] else None
            })
    
    # Calculate overall compliance
    overall_compliance = total_weighted_score / total_weight if total_weight > 0 else 0
    
    # Determine strengths and improvement areas
    strengths = [s for s in final_scores if s["score"] >= 0.8]
    improvement_areas = [s for s in final_scores if s["score"] < 0.7]
    
    return {
        "overall_compliance": round(overall_compliance, 2),
        "metric_scores": final_scores,
        "top_strengths": [
            f"{s['metric_name']}: {s['rating']}" for s in sorted(strengths, key=lambda x: -x['score'])[:3]
        ],
        "improvement_areas": [
            {
                "area": s["metric_name"],
                "suggestion": s.get("improvement_suggestion", "Focus on improving this area"),
                "current_score": s["score"]
            }
            for s in sorted(improvement_areas, key=lambda x: x['score'])[:3]
        ]
    }
```

---

## Error Handling

### Invalid Document Errors

```python
class InvalidSOPDocumentError(Exception):
    """Raised when uploaded document is not a valid SOP."""
    
    def __init__(self, reason: str, confidence: float, suggestions: List[str]):
        self.reason = reason
        self.confidence = confidence
        self.suggestions = suggestions
        super().__init__(f"Invalid SOP document: {reason}")


# API error response
{
    "error": "INVALID_SOP_DOCUMENT",
    "message": "Please upload a valid SOP document",
    "details": {
        "rejection_reason": "Document appears to be a product catalog...",
        "confidence": 0.95,
        "suggestions": [
            "Ensure document contains procedural guidelines",
            "Include role-specific instructions", 
            "Add measurable performance metrics"
        ]
    }
}
```

### Processing Errors

```python
# Extraction failure
{
    "error": "EXTRACTION_FAILED",
    "message": "Failed to extract text from document",
    "details": {
        "file_type": "application/pdf",
        "error_type": "CorruptedPDF",
        "suggestion": "Please ensure the PDF is not password-protected or corrupted"
    }
}

# Metric extraction failure
{
    "error": "METRIC_EXTRACTION_FAILED",
    "message": "Failed to extract metrics from SOP document",
    "details": {
        "chunks_processed": 8,
        "chunks_failed": 2,
        "error": "LLM response validation failed"
    },
    "retry_available": true
}
```

---

## Scope Handling Logic

### Company-Wide vs Role-Specific SOPs

```python
async def get_applicable_sop_for_call(
    company_id: str,
    rep_role: str = None
) -> Optional[dict]:
    """
    Get the most applicable SOP for a call evaluation.
    
    Priority:
    1. Role-specific SOP (if rep_role provided and SOP exists)
    2. Company-wide SOP (fallback)
    3. None (if no SOP configured)
    """
    # Check cache first
    cache_key = f"sop:applicable:{company_id}:{rep_role or 'any'}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Try role-specific first
    if rep_role:
        role_sop = await db.sop_metrics.find_one({
            "company_id": company_id,
            "target_role": rep_role,
            "status": "active"
        })
        if role_sop:
            await redis.setex(cache_key, 3600, json.dumps(role_sop))
            return role_sop
    
    # Fall back to company-wide
    company_sop = await db.sop_metrics.find_one({
        "company_id": company_id,
        "is_company_wide": True,
        "status": "active"
    })
    
    if company_sop:
        await redis.setex(cache_key, 3600, json.dumps(company_sop))
    
    return company_sop


async def merge_sop_metrics_for_evaluation(
    role_sop: dict = None,
    company_sop: dict = None
) -> List[dict]:
    """
    Merge role-specific and company-wide metrics.
    
    Rules:
    - Role-specific metrics take precedence for same metric_id
    - Company-wide metrics apply as baseline
    - Normalize weights to sum to 1.0
    """
    merged = {}
    
    # Add company-wide metrics first (as baseline)
    if company_sop:
        for metric in company_sop.get("metrics", []):
            merged[metric["metric_id"]] = metric
    
    # Override/add role-specific metrics
    if role_sop:
        for metric in role_sop.get("metrics", []):
            merged[metric["metric_id"]] = metric
    
    # Normalize weights
    metrics_list = list(merged.values())
    total_weight = sum(m.get("weight", 0.1) for m in metrics_list)
    
    if total_weight != 1.0 and total_weight > 0:
        for metric in metrics_list:
            metric["weight"] = metric.get("weight", 0.1) / total_weight
    
    return metrics_list
```

---

## Performance Optimizations

### 1. Parallel Processing
- Text extraction and validation run in parallel
- Chunk embedding generation parallelized (batch of 10)
- MongoDB and Redis storage parallelized

### 2. Caching Strategy
- Cache active SOP metrics in Redis (24-hour TTL)
- Pre-warm cache on SOP activation
- Cache evaluation schemas for fast call processing

### 3. Incremental Processing
- Stream large documents page by page
- Process chunks as they're created
- Early termination on validation failure

### 4. Resource Management
- Limit concurrent document processing (max 3 per company)
- Queue large documents during peak hours
- Use smaller embedding model for SOP content

---

## Success Metrics

| Metric | Target | Monitoring |
|--------|--------|------------|
| Document processing time | < 5 min (50 pages) | Job duration metric |
| SOP validation accuracy | > 95% | Manual audit sample |
| Metric extraction quality | > 90% coverage | LLM evaluation |
| API response time (upload) | < 500ms | HTTP middleware |
| Cache hit rate (metrics) | > 90% | Redis stats |
| Call evaluation overhead | < 2s additional | Processing timer |

---

## File Structure (Proposed)

```
app/
├── services/
│   └── sop/
│       ├── __init__.py
│       ├── document_service.py      # Upload, storage, retrieval
│       ├── extraction_service.py    # PDF/Word text extraction
│       ├── validation_service.py    # SOP document validation
│       ├── chunking_service.py      # Document chunking
│       ├── metric_extraction_service.py  # LLM metric extraction
│       └── evaluation_service.py    # Call evaluation against SOP
│
├── api/v1/
│   └── sop.py                       # API endpoints (7 endpoints)
│
├── models/
│   └── sop.py                       # MongoDB models
│
├── schemas/
│   └── sop.py                       # Pydantic schemas
│
└── tasks/
    └── sop_tasks.py                 # Background task functions (FastAPI BackgroundTasks)
```

---

## Summary

Feature 4: SOP Document Ingestion provides:

1. **Document Upload API** - Accept PDF/Word documents with validation
2. **Text Extraction** - Handle multi-format documents with structure preservation
3. **SOP Validation** - LLM-based classification to ensure valid SOP content
4. **Dynamic Chunking** - Context-aware splitting for large documents
5. **Metric Extraction** - Rolling extraction of performance metrics
6. **Multi-tenant Storage** - MongoDB + Redis with company/role isolation
7. **Call Processing Integration** - Inject SOP metrics into call evaluation
8. **Ask Otto Integration** - RAG search for SOP content in Q&A
9. **Scope Management** - Handle company-wide vs role-specific SOPs

### Integration Points

| Feature | Integration |
|---------|-------------|
| **Feature 1** | SOP metrics injected into call summary generation |
| **Feature 2** | Weekly insights include SOP compliance trends |
| **Feature 3** | Ask Otto retrieves SOP content for Q&A |

### API Endpoints (7)

```
POST   /api/v1/sop/documents/upload
GET    /api/v1/sop/documents/status/{job_id}
GET    /api/v1/sop/metrics/{company_id}
GET    /api/v1/sop/documents/{sop_id}
PATCH  /api/v1/sop/documents/{sop_id}/status
GET    /api/v1/sop/documents
DELETE /api/v1/sop/documents/{sop_id}
```

---

## Extended Features (v2.0)

### Feature 6: SOP Version Control & Change Management
See **[Features 5-9](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md)** for full details.

#### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/sop/documents/{sop_id}/versions` | Upload new version |
| `GET /api/v1/sop/documents/{sop_id}/versions` | Get version history |
| `GET /api/v1/sop/documents/{sop_id}/versions/{version}` | Get specific version |
| `POST /api/v1/sop/documents/{sop_id}/reanalyze` | Re-analyze calls against new SOP |
| `GET /api/v1/sop/reanalysis/{job_id}` | Get re-analysis status |

#### Version Control Implementation

**Version Creation:**
- Auto-increments version number (v1, v2, v3...)
- Archives current version immediately on new upload
- Supports scheduled activation via `activation_date`
- File hash duplicate detection (409 if exact match)

**Version History Model:**
```python
{
    "history_id": "sop_hist_abc123",
    "sop_id": "sop_xyz",
    "version": 3,
    "status": "active",  # active | archived | scheduled
    "metrics_snapshot": [...],
    "file_hash": "sha256:...",
    "activation_date": datetime,
    "archived_at": datetime | None
}
```

**Scheduled Activation:**
- Background task `check_scheduled_activations()` runs periodically
- Archives current version, activates scheduled version
- Updates SOP document and metrics

#### Re-analysis Workflow

**Process:**
- Manual trigger only (no automatic re-analysis)
- Default lookback: 14 days (configurable)
- Re-analyzes ALL calls in period (not just failures)
- Stores both original and new evaluations

**CallReanalysis Model:**
```python
{
    "reanalysis_id": "uuid",
    "call_id": "5002",
    "original_sop_version": 2,
    "new_sop_version": 3,
    "original_compliance": {score: 0.82, ...},
    "new_compliance": {score: 0.78, ...},
    "score_delta": -0.04,
    "metrics_changed": ["greeting_quality", "objection_handling"]
}
```

#### MongoDB Collections

| Collection | Purpose |
|------------|---------|
| `sop_version_history` | Full version audit trail with metrics snapshots |
| `reanalysis_jobs` | Re-analysis job tracking (status, progress, results) |
| `call_reanalysis` | Per-call re-analysis comparison records |

### Single Active SOP Rule

When saving metrics, the system deactivates other SOPs for the same company/role combination:

```python
# Only one active SOP per company/role
await db.sop_metrics.update_many(
    {"company_id": company_id, "target_role": role, "sop_id": {"$ne": current_sop_id}},
    {"$set": {"status": "inactive"}}
)
```

### File Structure

```
app/
├── api/v1/
│   └── sop.py                         # API endpoints (11 endpoints)
│
├── tasks/
│   └── sop_tasks.py                   # Background processing
│
├── services/sop/
│   ├── __init__.py
│   ├── document_service.py            # Upload, storage, retrieval
│   ├── document_download_service.py   # S3/HTTP/local download
│   ├── extraction_service.py          # PDF/Word text extraction
│   ├── validation_service.py          # SOP document validation
│   ├── chunking_service.py            # Document chunking
│   ├── metric_extraction_service.py   # LLM metric extraction
│   ├── evaluation_service.py          # Call evaluation against SOP
│   ├── version_service.py             # Version control
│   └── reanalysis_service.py          # Historical re-analysis
│
├── models/
│   └── sop.py                         # MongoDB models
│
└── schemas/
    └── sop.py                         # Pydantic schemas
```

---

**Previous:** [Feature 3: Ask Otto Chat Enhancement](./ARCHITECTURE_FEATURE_3_ASK_OTTO.md)

**Next:** [Features 5-9: Advanced Analytics](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md)