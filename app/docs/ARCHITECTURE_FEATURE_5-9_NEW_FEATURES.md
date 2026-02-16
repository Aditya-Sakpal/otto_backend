# Features 5-9: Advanced Analytics & Intelligence

**Version:** 2.0  
**Date:** February 4, 2026  
**Service:** Independent Microservice Architecture  
**Implementation:** FastAPI + MongoDB + Redis

> **Last Updated:** February 2026 - All features fully implemented with detailed focus area score extraction, proportional BANT weighting, and enhanced coaching metrics.

---

## Overview

Features 5-9 extend the Otto Intelligence Service with advanced analytics, version management, and impact measurement capabilities. These features build upon the core call processing pipeline (Feature 1) and provide deeper business intelligence.

| Feature | Name | Primary Purpose |
|---------|------|-----------------|
| **5** | BANT Lead Scoring Enhancement | Score leads using Budget, Authority, Need, Timeline framework |
| **6** | SOP Version Control | Manage SOP versions with history, scheduling, and re-analysis |
| **7** | Coaching Impact Measurement | Track coaching effectiveness with baseline vs. follow-up comparison |
| **8** | Agent Progression Tracking | Monitor agent performance trends over time |
| **9** | Conversation Phase Detection | Semantically identify call phases (greeting, discovery, closing, etc.) |

---

# Feature 5: BANT Lead Scoring Enhancement

## Overview

BANT Lead Scoring provides a standardized framework for evaluating lead quality based on four key criteria: **Budget**, **Authority**, **Need**, and **Timeline**. The system includes objection penalties and bonus points to provide nuanced scoring.

### Scoring Framework

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BANT LEAD SCORING FRAMEWORK                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  BASE BANT SCORING (100 points total):                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐      │   │
│  │   │  BUDGET    │ │ AUTHORITY  │ │   NEED     │ │  TIMELINE  │      │   │
│  │   │  25 pts    │ │  25 pts    │ │  25 pts    │ │  25 pts    │      │   │
│  │   │            │ │            │ │            │ │            │      │   │
│  │   │ • Explicit │ │ • Decision │ │ • Urgency  │ │ • Scheduled│      │   │
│  │   │   budget   │ │   maker    │ │   level    │ │   date     │      │   │
│  │   │ • Range    │ │ • Final    │ │ • Problem  │ │ • ASAP flag│      │   │
│  │   │   given    │ │   approval │ │   severity │ │ • Window   │      │   │
│  │   └────────────┘ └────────────┘ └────────────┘ └────────────┘      │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  OBJECTION PENALTIES (Variable):                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Severity     Base Penalty    Type Multipliers                      │   │
│  │  ─────────    ────────────    ────────────────                      │   │
│  │  HIGH         -10 pts         Price:     1.5x                       │   │
│  │  MEDIUM       -5 pts          Competitor: 1.2x                      │   │
│  │  LOW          -2 pts          Trust:     1.3x                       │   │
│  │                               Authority: 1.1x                       │   │
│  │  Note: Overcome objections do NOT penalize                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  BONUS POINTS (Up to +35):                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • High Urgency ("ASAP", "emergency"):    +10 pts                   │   │
│  │  • Medium Urgency ("soon", "this month"): +5 pts                    │   │
│  │  • Referral (from existing customer):     +10 pts                   │   │
│  │  • Inbound Call (customer initiated):     +5 pts                    │   │
│  │  • Explicit Need ("I need", "must have"): +5 pts                    │   │
│  │  • Multiple Decision Makers (positive):   +5 pts                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  BAND THRESHOLDS (Fixed):                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │   HOT:   75-100  │█████████████████████████│  Ready to close        │   │
│  │   WARM:  50-74   │████████████████         │  Needs nurturing       │   │
│  │   COLD:  0-49    │████████                 │  Early stage           │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions Implemented

| Decision | Question | Implementation |
|----------|----------|----------------|
| Q25 | How to weight BANT components? | Equal: 25 pts each |
| Q26 | Objection penalty calculation? | Severity × Type multiplier |
| Q27 | Bonus point triggers? | Urgency, referral, inbound, explicit need |
| Q28 | Band thresholds? | Hot 75+, Warm 50-74, Cold <50 |
| Q29 | Customizable thresholds? | Fixed (v1.0) |
| Q31 | Recalculation trigger? | On each new call |
| Q33 | Missing BANT components? | Proportional weighting |

### Score Breakdown Model

```python
class LeadScore:
    total_score: int           # 0-100 final score
    lead_band: LeadBand        # HOT/WARM/COLD
    breakdown: List[ScoreBreakdown]  # Detailed per-component
    algorithm_version: str     # "1.0"
    confidence: str            # high/medium/low

class ScoreBreakdown:
    component: str             # "budget", "authority", etc.
    points_possible: int       # Max points for component
    points_earned: Optional[int]  # Actual points (None = unknown)
    reason: str                # Human-readable explanation
    evidence: Optional[str]    # Supporting transcript quote
```

### Proportional Weighting Algorithm

When BANT components are incomplete (e.g., budget not discussed), the system uses proportional weighting:

```python
# If only 2 of 4 BANT factors available with scores 40/50:
# Scale: (40/50) * 100 = 80/100 base BANT score
# Then add bonuses/penalties on top
```

### Integration with Call Processing

Lead scoring is integrated into the call processing pipeline (Feature 1) at Step 4:

```
Call Processing Pipeline
        │
        ▼
┌─────────────────────────────┐
│ STEP 4: QUALIFICATION       │
│ EXTRACTION                  │
│                             │
│ 1. Extract BANT signals     │
│ 2. Calculate lead score     │
│ 3. Store breakdown          │
└────────────┬────────────────┘
             │
             ▼
    call_summaries.lead_score
```

---

# Feature 6: SOP Version Control & Change Management

## Overview

SOP Version Control enables companies to manage multiple versions of Standard Operating Procedures with full history tracking, scheduled activations, and historical call re-analysis.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SOP VERSION CONTROL SYSTEM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    VERSION LIFECYCLE                                 │   │
│  │                                                                      │   │
│  │    ┌──────────┐      ┌──────────┐      ┌──────────┐                │   │
│  │    │ UPLOAD   │──────│ SCHEDULED│──────│  ACTIVE  │                │   │
│  │    │ NEW      │      │ (future  │      │ (current)│                │   │
│  │    │ VERSION  │      │  date)   │      │          │                │   │
│  │    └──────────┘      └──────────┘      └────┬─────┘                │   │
│  │                                              │                      │   │
│  │                           When new version   │                      │   │
│  │                           activates:         ▼                      │   │
│  │                                        ┌──────────┐                │   │
│  │                                        │ ARCHIVED │                │   │
│  │                                        │ (history)│                │   │
│  │                                        └──────────┘                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    VERSION HISTORY STORAGE                           │   │
│  │                                                                      │   │
│  │  sop_version_history:                                                │   │
│  │  {                                                                   │   │
│  │    history_id: "sop_hist_abc123",                                   │   │
│  │    sop_id: "sop_xyz",                                               │   │
│  │    company_id: "acme_roofing",                                      │   │
│  │    version: 3,                                                      │   │
│  │    created_at: "2026-01-28T10:00:00Z",                             │   │
│  │    created_by: "manager_123",                                       │   │
│  │    activation_date: "2026-02-01T00:00:00Z",                        │   │
│  │    archived_at: null,                                               │   │
│  │    status: "scheduled",  // active | scheduled | archived           │   │
│  │    metrics_snapshot: [...],  // Full metrics at this version        │   │
│  │    file_hash: "sha256:...",  // Duplicate detection                 │   │
│  │    original_filename: "sales_sop_v3.pdf"                           │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    RE-ANALYSIS WORKFLOW                              │   │
│  │                                                                      │   │
│  │  1. Manager uploads new SOP version                                 │   │
│  │  2. System archives current version (immediate)                     │   │
│  │  3. New version activates (immediate or scheduled)                  │   │
│  │  4. Manager triggers re-analysis:                                   │   │
│  │                                                                      │   │
│  │     POST /api/v1/sop/documents/{sop_id}/reanalyze                  │   │
│  │     {                                                                │   │
│  │       "date_range_start": "2026-01-01",                            │   │
│  │       "date_range_end": "2026-01-27"                               │   │
│  │     }                                                                │   │
│  │                                                                      │   │
│  │  5. Background job processes historical calls:                      │   │
│  │     - Fetch calls in date range                                     │   │
│  │     - Re-evaluate compliance against new SOP                        │   │
│  │     - Store results in call_reanalysis collection                   │   │
│  │     - Update job status in reanalysis_jobs                          │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions Implemented

| Decision | Question | Implementation |
|----------|----------|----------------|
| Q1 | Version numbering? | Auto-increment (v1, v2, v3...) |
| Q2 | Old version handling? | Immediate archive |
| Q4 | Scheduled activation? | Optional future date supported |
| Q5 | Version comparison? | Basic metric diff in v1.0 |
| Q6 | Re-analysis on new version? | Background job triggered |
| Q7 | Historical version lookup? | Get version active at specific time |

### API Endpoints

```
POST   /api/v1/sop/documents/{sop_id}/versions     # Upload new version
GET    /api/v1/sop/documents/{sop_id}/versions     # Get version history
GET    /api/v1/sop/documents/{sop_id}/versions/{v} # Get specific version
POST   /api/v1/sop/documents/{sop_id}/reanalyze    # Trigger re-analysis
GET    /api/v1/sop/reanalysis/{job_id}             # Get re-analysis status
```

### MongoDB Collections

```javascript
// sop_version_history
{
  history_id: "sop_hist_abc123",
  sop_id: "sop_xyz",
  company_id: "acme_roofing",
  version: 3,
  status: "active",  // "active" | "scheduled" | "archived"
  created_at: ISODate(),
  created_by: "manager_123",
  activation_date: ISODate(),
  archived_at: ISODate() | null,
  metrics_snapshot: [...],
  total_metrics: 15,
  file_hash: "sha256:..."
}

// reanalysis_jobs
{
  job_id: "reanalyze_abc123",
  sop_id: "sop_xyz",
  company_id: "acme_roofing",
  sop_version: 3,
  status: "processing",  // "pending" | "processing" | "completed" | "failed"
  date_range_start: ISODate(),
  date_range_end: ISODate(),
  total_calls: 145,
  processed_calls: 87,
  created_at: ISODate()
}

// call_reanalysis
{
  call_id: "5002",
  reanalysis_job_id: "reanalyze_abc123",
  sop_version: 3,
  original_compliance_score: 0.82,
  new_compliance_score: 0.78,
  score_change: -0.04,
  processed_at: ISODate()
}
```

### Scheduled Activation Background Job

A background task runs periodically to activate scheduled versions:

```python
async def check_scheduled_activations():
    """
    Runs every 5 minutes to activate scheduled SOP versions.
    
    1. Find versions where activation_date <= now AND status = "scheduled"
    2. Archive current active version
    3. Set scheduled version to "active"
    4. Update SOP document and metrics
    5. Clear Redis cache
    """
```

---

# Feature 7: Coaching Impact Measurement

## Overview

Coaching Impact Measurement tracks the effectiveness of coaching sessions by comparing pre-coaching baseline performance to post-coaching results. It provides data-driven insights into which coaching interventions work best.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COACHING IMPACT MEASUREMENT                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    COACHING SESSION LIFECYCLE                        │   │
│  │                                                                      │   │
│  │   ┌────────────────────────────────────────────────────────────┐    │   │
│  │   │ 1. CREATE SESSION                                          │    │   │
│  │   │                                                             │    │   │
│  │   │    Manager identifies rep needing coaching                  │    │   │
│  │   │    ↓                                                        │    │   │
│  │   │    System auto-calculates BASELINE:                         │    │   │
│  │   │    • Get last 5 calls for rep                              │    │   │
│  │   │    • Extract scores for focus areas                        │    │   │
│  │   │    • Remove outliers (top/bottom 10%)                      │    │   │
│  │   │    • Calculate averages                                    │    │   │
│  │   │    • Flag confidence (high if ≥5 calls, else low)         │    │   │
│  │   └────────────────────────────────────────────────────────────┘    │   │
│  │                              │                                       │   │
│  │                              ▼                                       │   │
│  │   ┌────────────────────────────────────────────────────────────┐    │   │
│  │   │ 2. COACHING OCCURS (Outside System)                        │    │   │
│  │   │                                                             │    │   │
│  │   │    Manager coaches rep on focus areas                       │    │   │
│  │   │    Status: "in_progress"                                    │    │   │
│  │   └────────────────────────────────────────────────────────────┘    │   │
│  │                              │                                       │   │
│  │                              ▼ (After follow_up_period_days)        │   │
│  │   ┌────────────────────────────────────────────────────────────┐    │   │
│  │   │ 3. MEASURE IMPACT (Auto-triggered)                         │    │   │
│  │   │                                                             │    │   │
│  │   │    Daily background job checks sessions where:              │    │   │
│  │   │    follow_up_end_date <= now AND status = "in_progress"    │    │   │
│  │   │                                                             │    │   │
│  │   │    ↓                                                        │    │   │
│  │   │    Calculate post-coaching scores:                          │    │   │
│  │   │    • Get calls since coached_at                            │    │   │
│  │   │    • Compare to baseline                                   │    │   │
│  │   │    • Determine trend (improving/stable/declining)          │    │   │
│  │   │    • Check if targets met                                  │    │   │
│  │   │                                                             │    │   │
│  │   │    ↓                                                        │    │   │
│  │   │    Decision logic:                                          │    │   │
│  │   │    IF calls < 5 AND not_extended:                          │    │   │
│  │   │       Extend by 7 days, status = "extended"                │    │   │
│  │   │    ELSE IF calls < 5 AND already_extended:                 │    │   │
│  │   │       Status = "insufficient_data"                         │    │   │
│  │   │    ELSE:                                                    │    │   │
│  │   │       Status = "completed"                                 │    │   │
│  │   └────────────────────────────────────────────────────────────┘    │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    IMPACT REPORT                                     │   │
│  │                                                                      │   │
│  │  {                                                                   │   │
│  │    "session_id": "coach_abc123",                                    │   │
│  │    "rep_name": "Travis",                                            │   │
│  │    "focus_areas": ["objection_handling", "needs_assessment"],       │   │
│  │    "baseline": {                                                    │   │
│  │      "objection_handling": 0.45,                                    │   │
│  │      "needs_assessment": 0.60                                       │   │
│  │    },                                                                │   │
│  │    "current": {                                                     │   │
│  │      "objection_handling": 0.68,  // +51% improvement              │   │
│  │      "needs_assessment": 0.72     // +20% improvement              │   │
│  │    },                                                                │   │
│  │    "targets_met": {                                                 │   │
│  │      "objection_handling": true,  // Target was 0.65               │   │
│  │      "needs_assessment": false    // Target was 0.75               │   │
│  │    },                                                                │   │
│  │    "overall_improved": true                                         │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    COACH EFFECTIVENESS                               │   │
│  │                                                                      │   │
│  │  Aggregated metrics per coach over 90-day period:                   │   │
│  │                                                                      │   │
│  │  {                                                                   │   │
│  │    "coach_id": "manager_123",                                       │   │
│  │    "coach_name": "John Manager",                                    │   │
│  │    "total_sessions": 15,                                            │   │
│  │    "reps_coached": 8,                                               │   │
│  │    "reps_improved": 12,                                             │   │
│  │    "improvement_rate": 0.80,  // 80% of sessions show improvement  │   │
│  │    "avg_improvement_percentage": 18.5,                              │   │
│  │    "best_focus_area": "objection_handling",   // Most effective    │   │
│  │    "worst_focus_area": "budget_qualification" // Least effective   │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions Implemented

| Decision | Question | Implementation |
|----------|----------|----------------|
| Q14 | Calls needed? | 10 total (5 baseline + 5 validation) |
| Q15 | Minimum for baseline? | 5 calls |
| Q16 | Insufficient calls? | Proceed with low-confidence flag |
| Q17 | Outlier handling? | Remove top/bottom 10% |
| Q19 | Follow-up period? | 2 weeks default |
| Q20 | Impact timing? | Automatic at follow-up end |
| Q21 | Insufficient follow-up? | Extend 1 week, then flag |
| Q22 | Meaningful improvement? | ≥5% positive change |

### API Endpoints

```
POST   /api/v1/coaching/sessions                      # Create session (auto-calculates baseline)
GET    /api/v1/coaching/sessions/{session_id}         # Get session details
GET    /api/v1/coaching/sessions                      # List sessions (filtered)
GET    /api/v1/coaching/sessions/{session_id}/impact  # Get impact report
PATCH  /api/v1/coaching/sessions/{session_id}/status  # Update status (with extension support)
GET    /api/v1/coaching/coaches/{coach_id}/effectiveness  # Coach effectiveness
GET    /api/v1/coaching/roi                           # Company-wide ROI
```

### MongoDB Collections

```javascript
// coaching_sessions
{
  session_id: "coach_abc123",
  company_id: "acme_roofing",
  rep_id: "travis_rep",
  rep_name: "Travis",
  coach_id: "manager_123",
  coach_name: "John Manager",
  coached_at: ISODate(),
  focus_areas: ["objection_handling", "needs_assessment"],
  targets: {
    "objection_handling": 0.65,
    "needs_assessment": 0.75
  },
  baseline: {
    calls_analyzed: 5,
    scores: {...},
    confidence: "high"
  },
  impact: {
    calls_analyzed: 7,
    scores: {...},
    improvements: {...},
    overall_improved: true
  },
  follow_up_period_days: 14,
  follow_up_end_date: ISODate(),
  extended_count: 0,
  status: "completed"  // "in_progress" | "extended" | "completed" | "insufficient_data"
}

// coach_effectiveness
{
  coach_id: "manager_123",
  company_id: "acme_roofing",
  period_start: ISODate(),
  period_end: ISODate(),
  total_sessions: 15,
  improvement_rate: 0.80,
  skill_effectiveness: {...}
}
```

### Focus Area Score Extraction

The coaching service maps focus areas to specific call summary fields:

| Focus Area | Source Field | Calculation |
|------------|--------------|-------------|
| `compliance_score` | `compliance.sop_compliance.score` | Direct value |
| `sop_compliance` | `compliance.sop_compliance.score` | Direct value |
| `needs_assessment` | `qualification.bant_scores.need` | Direct value |
| `need_discovery` | `qualification.bant_scores.need` | Direct value |
| `budget_qualification` | `qualification.bant_scores.budget` | Direct value |
| `timeline_qualification` | `qualification.bant_scores.timeline` | Direct value |
| `authority_qualification` | `qualification.bant_scores.authority` | Direct value |
| `overall_qualification` | `qualification.overall_score` | Direct value |
| `objection_handling` | `objections.overcome_count / total` | Calculated ratio |
| `booking_rate` | `qualification.booking_status` | 1.0 if "booked", else 0.0 |
| `customer_sentiment` | `summary.sentiment_score` | Direct value |
| `lead_score` | `lead_score.total_score / 100` | Normalized to 0-1 |

### Configuration Constants

```python
MIN_CALLS_FOR_BASELINE = 5
MIN_CALLS_FOR_VALIDATION = 5
DEFAULT_FOLLOW_UP_DAYS = 14
EXTENSION_DAYS = 7
MAX_EXTENSIONS = 1
OUTLIER_PERCENTILE = 0.10  # Remove top/bottom 10%
IMPROVEMENT_THRESHOLD = 0.05  # 5% = meaningful improvement
```

### Background Jobs

| Job | Schedule | Description |
|-----|----------|-------------|
| `check_coaching_follow_ups` | Daily at 01:00 UTC | Completes/extends sessions past follow-up date |
| `calculate_weekly_coach_effectiveness` | Monday at 02:00 UTC | Updates coach effectiveness metrics |

---

# Feature 8: Agent Progression Tracking

## Overview

Agent Progression Tracking monitors rep performance over time with weekly granularity. It detects trends, identifies anomalies, and enables peer comparisons.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AGENT PROGRESSION TRACKING                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    WEEKLY METRICS CALCULATION                        │   │
│  │                                                                      │   │
│  │  For each week, calculate:                                          │   │
│  │                                                                      │   │
│  │  Week 1   Week 2   Week 3   Week 4   Week 5   Week 6   Week 7   Week 8 │
│  │  ├────────┼────────┼────────┼────────┼────────┼────────┼────────┤    │   │
│  │  │  0.72  │  0.75  │  0.73  │  0.78  │  0.80  │  0.82  │  0.85  │    │   │
│  │  │  5     │  7     │  4     │  6     │  8     │  6     │  7     │calls│   │
│  │  │  high  │  high  │  low   │  high  │  high  │  high  │  high  │conf │   │
│  │  └────────┴────────┴────────┴────────┴────────┴────────┴────────┘    │   │
│  │                                                                      │   │
│  │  Confidence: high if ≥5 calls, low otherwise                        │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    TREND DETECTION                                   │   │
│  │                                                                      │   │
│  │  Compare first week to last week:                                   │   │
│  │                                                                      │   │
│  │  IF (last - first) / first >= 5%:   IMPROVING  ▲                   │   │
│  │  IF (last - first) / first <= -5%:  DECLINING  ▼                   │   │
│  │  OTHERWISE:                         STABLE     ─                    │   │
│  │                                                                      │   │
│  │  Example:                                                           │   │
│  │  compliance_score: 0.72 → 0.85 = +18% → IMPROVING                  │   │
│  │  booking_rate:     0.45 → 0.43 = -4%  → STABLE                     │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    ANOMALY DETECTION                                 │   │
│  │                                                                      │   │
│  │  Week-over-week change > 20% = ANOMALY                              │   │
│  │                                                                      │   │
│  │  Week 4 → Week 5:                                                   │   │
│  │  0.60 → 0.78 = +30% change → SPIKE anomaly flagged                 │   │
│  │                                                                      │   │
│  │  Anomaly Types:                                                     │   │
│  │  • SPIKE:  Sudden positive change (>20%)                           │   │
│  │  • DROP:   Sudden negative change (>20%)                           │   │
│  │                                                                      │   │
│  │  Output:                                                            │   │
│  │  {                                                                  │   │
│  │    "week_index": 5,                                                 │   │
│  │    "direction": "spike",                                            │   │
│  │    "change_magnitude": 0.30,                                        │   │
│  │    "previous_value": 0.60,                                          │   │
│  │    "current_value": 0.78                                            │   │
│  │  }                                                                  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PEER COMPARISON (On-Demand)                       │   │
│  │                                                                      │   │
│  │  Compare rep's score to all peers in same company:                  │   │
│  │                                                                      │   │
│  │  GET /api/v1/insights/agents/{rep_id}/peer-comparison?metric=compliance_score │
│  │                                                                      │   │
│  │  Response:                                                          │   │
│  │  {                                                                  │   │
│  │    "rep_id": "travis_rep",                                          │   │
│  │    "rep_score": 0.85,                                               │   │
│  │    "rep_rank": 3,            // 3rd out of 12 reps                 │   │
│  │    "peer_count": 12,                                                │   │
│  │    "peer_average": 0.72,                                            │   │
│  │    "peer_median": 0.71,                                             │   │
│  │    "percentile": 75          // Top 25%                            │   │
│  │  }                                                                  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions Implemented

| Decision | Question | Implementation |
|----------|----------|----------------|
| Q37 | Time granularity? | Weekly only |
| Q38 | Minimum calls? | 5 per week for confidence |
| Q39 | Insufficient calls? | Show low-confidence trend |
| Q41 | Trend threshold? | ≥5% = improving/declining |
| Q44 | Anomaly detection? | Flag >20% week-over-week change |
| Q46 | Peer comparison? | On-demand only |

### API Endpoints

```
GET /api/v1/insights/agents/{rep_id}/progression
    ?metrics=compliance_score,booking_rate
    &weeks=8

GET /api/v1/insights/agents/{rep_id}/peer-comparison
    ?metric=compliance_score
    &days=30

GET /api/v1/insights/agents/summary
    ?company_id=acme_roofing
```

### Response Structure

```json
{
  "rep_id": "travis_rep",
  "rep_name": "Travis",
  "timeframe_weeks": 8,
  "total_calls": 45,
  "overall_confidence": "high",
  "metrics": {
    "compliance_score": {
      "metric_name": "compliance_score",
      "current_value": 0.85,
      "period_change": 0.13,
      "period_change_percent": 18.0,
      "trend": {
        "direction": "improving",
        "magnitude": 0.18,
        "start_value": 0.72,
        "end_value": 0.85
      },
      "anomalies": [
        {
          "week_index": 5,
          "direction": "spike",
          "change_magnitude": 0.25
        }
      ],
      "data_points": [...]
    }
  },
  "improving_metrics": ["compliance_score"],
  "declining_metrics": [],
  "stable_metrics": ["booking_rate"]
}
```

---

# Feature 9: Conversation Phase Detection

## Overview

Conversation Phase Detection uses LLM-based semantic analysis to identify distinct phases within a sales call transcript. It helps understand call flow, identify missing phases, and measure phase quality.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CONVERSATION PHASE DETECTION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    6 CORE PHASES                                     │   │
│  │                                                                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  │ GREETING │→│ PROBLEM  │→│ QUALIFI- │→│ OBJECTION│→│ CLOSING  │→│ POST-    │ │
│  │  │          │ │ DISCOVERY│ │ CATION   │ │ HANDLING │ │          │ │ CLOSE    │ │
│  │  │          │ │          │ │          │ │          │ │          │ │          │ │
│  │  │ "Hi, this│ │ "What    │ │ "What's  │ │ "I under-│ │ "We have │ │ "You'll  │ │
│  │  │ is..."   │ │ brings   │ │ your     │ │ stand    │ │ availa-  │ │ receive  │ │
│  │  │          │ │ you in?" │ │ budget?" │ │ your..." │ │ bility..." │ confirmation"│ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  │                                                                      │   │
│  │  Note: Phases can overlap and may not all be present               │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    DETECTION PROCESS                                 │   │
│  │                                                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ 1. Transcript Input                                           │  │   │
│  │  │                                                                │  │   │
│  │  │    "Hi, this is Travis from Arizona Roofers. How can I       │  │   │
│  │  │    help you today? ... What brings you in? ... We have       │  │   │
│  │  │    availability next Tuesday..."                              │  │   │
│  │  └────────────────────────────┬──────────────────────────────────┘  │   │
│  │                               │                                      │   │
│  │                               ▼                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ 2. LLM Analysis (Primary) or Rule-Based (Fallback)           │  │   │
│  │  │                                                                │  │   │
│  │  │    Prompt instructs LLM to:                                   │  │   │
│  │  │    • Identify which phases are present                        │  │   │
│  │  │    • Extract key phrases for each phase                       │  │   │
│  │  │    • Provide confidence scores (0.0-1.0)                      │  │   │
│  │  │    • Estimate word index boundaries                           │  │   │
│  │  │    • Assess quality of execution                              │  │   │
│  │  └────────────────────────────┬──────────────────────────────────┘  │   │
│  │                               │                                      │   │
│  │                               ▼                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ 3. Timestamp Estimation (from word count)                     │  │   │
│  │  │                                                                │  │   │
│  │  │    • 150 words/minute average speaking rate                   │  │   │
│  │  │    • Linear interpolation based on word position              │  │   │
│  │  │    • Scale to actual call duration if provided                │  │   │
│  │  │                                                                │  │   │
│  │  │    Example:                                                   │  │   │
│  │  │    Word index 0-50 → 0ms - 20,000ms (first 50 words)         │  │   │
│  │  └────────────────────────────┬──────────────────────────────────┘  │   │
│  │                               │                                      │   │
│  │                               ▼                                      │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │ 4. Build Analytics                                            │  │   │
│  │  │                                                                │  │   │
│  │  │    • Time distribution per phase                              │  │   │
│  │  │    • Missing phases list                                      │  │   │
│  │  │    • Phase sequence order                                     │  │   │
│  │  │    • Dominant phase (longest duration)                        │  │   │
│  │  │    • Overall flow score                                       │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PHASE DETECTION OUTPUT                            │   │
│  │                                                                      │   │
│  │  {                                                                   │   │
│  │    "call_id": "5002",                                               │   │
│  │    "phases": {                                                      │   │
│  │      "greeting": {                                                  │   │
│  │        "detected": true,                                            │   │
│  │        "confidence": 0.95,                                          │   │
│  │        "timestamps": {                                              │   │
│  │          "start_ms": 0,                                             │   │
│  │          "end_ms": 15000,                                           │   │
│  │          "duration_ms": 15000                                       │   │
│  │        },                                                           │   │
│  │        "key_phrases": ["Hi, this is Travis", "How can I help"],    │   │
│  │        "quality_score": 0.9,                                        │   │
│  │        "quality_notes": "Excellent introduction with name..."       │   │
│  │      },                                                             │   │
│  │      "problem_discovery": { ... },                                  │   │
│  │      "qualification": { "detected": false, ... },                   │   │
│  │      ...                                                            │   │
│  │    },                                                               │   │
│  │    "analytics": {                                                   │   │
│  │      "phases_detected": 5,                                          │   │
│  │      "phases_missing": ["qualification"],                           │   │
│  │      "phase_sequence": ["greeting", "problem_discovery", ...],      │   │
│  │      "dominant_phase": "problem_discovery",                         │   │
│  │      "time_distribution": {                                         │   │
│  │        "greeting": 15000,                                           │   │
│  │        "problem_discovery": 120000,                                 │   │
│  │        ...                                                          │   │
│  │      }                                                              │   │
│  │    },                                                               │   │
│  │    "overall_flow_score": 0.75,                                      │   │
│  │    "has_missing_phases": true                                       │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions Implemented

| Decision | Question | Implementation |
|----------|----------|----------------|
| Q49 | Which phases? | 6 core phases |
| Q50 | Detection method? | LLM-based semantic analysis |
| Q51 | Phase overlap? | Allowed (phases can blend) |
| Q52 | Timestamps? | Estimate from word count |
| Q56 | Missing phases? | Flag in output |
| Q57 | Time distribution? | Track per-phase duration |

### API Endpoints

```
GET /api/v1/call-processing/calls/{call_id}/phases
    # Get detected phases for a specific call

GET /api/v1/call-processing/phases/search
    ?company_id=acme_roofing
    &missing_phases=qualification
    &date_range_start=2026-01-01
    # Search for calls with specific phase patterns

GET /api/v1/call-processing/phases/analytics
    ?company_id=acme_roofing
    &days=30
    # Company-wide phase analytics
```

### Integration with Call Processing Pipeline

Phase detection is integrated as Step 7 in the call processing pipeline:

```
Call Processing Pipeline
        │
        ▼
┌─────────────────────────────┐
│ STEP 7: PHASE DETECTION     │
│ (Non-blocking)              │
│                             │
│ 1. Get full transcript      │
│ 2. Call PhaseDetectionService │
│ 3. Store in call_phases     │
│ 4. Continue pipeline        │
└────────────┬────────────────┘
             │
             ▼
        db.call_phases
```

### MongoDB Collection

```javascript
// call_phases
{
  call_id: "5002",
  company_id: "acme_roofing",
  phases: {
    greeting: {
      detected: true,
      confidence: 0.95,
      timestamps: { start_ms: 0, end_ms: 15000, duration_ms: 15000 },
      key_phrases: ["Hi, this is Travis"],
      quality_score: 0.9
    },
    problem_discovery: { ... },
    ...
  },
  analytics: {
    phases_detected: 5,
    phases_missing: ["qualification"],
    phase_sequence: [...],
    time_distribution: {...}
  },
  overall_flow_score: 0.75,
  has_missing_phases: true,
  detection_method: "llm",
  processed_at: ISODate()
}
```

---

## MongoDB Indexes (All Features)

```javascript
// Lead Scoring
db.call_summaries.createIndex({ "lead_score.lead_band": 1, company_id: 1 })
db.call_summaries.createIndex({ "lead_score.total_score": -1, company_id: 1 })

// SOP Version Control
db.sop_version_history.createIndex({ sop_id: 1, version: -1 })
db.sop_version_history.createIndex({ company_id: 1, status: 1 })
db.sop_version_history.createIndex({ status: 1, activation_date: 1 })
db.sop_version_history.createIndex({ sop_id: 1, file_hash: 1 })

// Reanalysis
db.reanalysis_jobs.createIndex({ job_id: 1 }, { unique: true })
db.reanalysis_jobs.createIndex({ sop_id: 1, status: 1 })
db.call_reanalysis.createIndex({ reanalysis_job_id: 1, call_id: 1 })

// Coaching
db.coaching_sessions.createIndex({ session_id: 1 }, { unique: true })
db.coaching_sessions.createIndex({ company_id: 1, rep_id: 1, coached_at: -1 })
db.coaching_sessions.createIndex({ company_id: 1, coach_id: 1, coached_at: -1 })
db.coaching_sessions.createIndex({ status: 1, follow_up_end_date: 1 })

// Agent Progression
db.calls.createIndex({ company_id: 1, "metadata.rep_id": 1, call_date: -1 })

// Phase Detection
db.call_phases.createIndex({ call_id: 1 }, { unique: true })
db.call_phases.createIndex({ company_id: 1, has_missing_phases: 1 })
db.call_phases.createIndex({ company_id: 1, "phases.greeting.detected": 1 })
```

---

## Performance Optimizations

### Caching Strategy

| Feature | Cache Key Pattern | TTL |
|---------|-------------------|-----|
| Lead Scoring | N/A (computed on demand) | - |
| SOP Versions | `sop:active:{company_id}:{role}` | 24h |
| Coaching | N/A (database queries) | - |
| Progression | `progression:{rep_id}:{weeks}` | 1h |
| Phase Detection | N/A (computed once, stored) | - |

### Background Jobs

| Feature | Job | Schedule |
|---------|-----|----------|
| SOP Versions | `check_scheduled_activations` | Every 5 minutes |
| Coaching | `check_coaching_follow_ups` | Daily at 01:00 UTC |
| Coaching | `calculate_weekly_coach_effectiveness` | Monday at 02:00 UTC |
| Insights | `weekly_insights_generation` | Sunday at 00:00 UTC |

---

## Success Metrics

| Feature | Metric | Target |
|---------|--------|--------|
| Lead Scoring | Calculation time | < 100ms |
| Lead Scoring | Score accuracy | > 85% (vs manual) |
| SOP Versions | Version switch time | < 5s |
| SOP Versions | Re-analysis rate | 1000 calls/hour |
| Coaching | Baseline calculation | < 2s |
| Coaching | Impact measurement | < 5s |
| Progression | Weekly metrics query | < 1s |
| Progression | 8-week progression | < 3s |
| Phase Detection | LLM detection time | < 10s |
| Phase Detection | Phase accuracy | > 80% |

---

## Summary

Features 5-9 provide advanced analytics and intelligence capabilities:

| Feature | Business Value |
|---------|---------------|
| **5 - Lead Scoring** | Prioritize leads, focus on high-value opportunities |
| **6 - SOP Versioning** | Track SOP changes, re-evaluate historical performance |
| **7 - Coaching Impact** | Measure coaching ROI, identify effective techniques |
| **8 - Agent Progression** | Spot trends, detect anomalies, compare peers |
| **9 - Phase Detection** | Understand call flow, identify coaching opportunities |

### Total API Endpoints: 17

```
Lead Scoring:        3 endpoints (GET leads, distribution, history)
SOP Versioning:      5 endpoints
Coaching:            7 endpoints (including status update)
Agent Progression:   3 endpoints
Phase Detection:     3 endpoints
```

### MongoDB Collections: 7

```
sop_version_history    # Version audit trail
reanalysis_jobs        # Re-analysis tracking
call_reanalysis        # Per-call comparison
coaching_sessions      # Session data + baseline + impact
coach_effectiveness    # Weekly effectiveness metrics
call_phases            # Phase detection results
weekly_insights        # Agent progression data (shared)
```

### Implementation Highlights

| Feature | Key Implementation Detail |
|---------|--------------------------|
| **Lead Scoring** | Proportional weighting for incomplete BANT (not penalized) |
| **SOP Versioning** | Scheduled activation with background task |
| **Coaching** | Automatic baseline from last 5 calls, outlier removal |
| **Progression** | 5% threshold for trend detection, 20% for anomalies |
| **Phase Detection** | Hybrid alignment of LLM + API segments |

---

**Previous:** [Feature 4: SOP Document Ingestion](./ARCHITECTURE_FEATURE_4_DOCUMENT_INGESTION.md)

**Complete Architecture Documents:**
1. [Overview](./INDEPENDENT_SERVICE_ARCHITECTURE_OVERVIEW.md) - Main service architecture
2. [Feature 1](./ARCHITECTURE_FEATURE_1_CALL_PIPELINE.md) - Call Processing Pipeline APIs
3. [Feature 2](./ARCHITECTURE_FEATURE_2_INSIGHTS_ENGINE.md) - Weekly Insights Engine APIs
4. [Feature 3](./ARCHITECTURE_FEATURE_3_ASK_OTTO.md) - Ask Otto Chat Enhancement APIs
5. [Feature 4](./ARCHITECTURE_FEATURE_4_DOCUMENT_INGESTION.md) - SOP Document Ingestion
6. **[Features 5-9](./ARCHITECTURE_FEATURE_5-9_NEW_FEATURES.md) - Advanced Analytics (This Document)**
