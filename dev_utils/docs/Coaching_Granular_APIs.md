# Otto Coaching API - Granular Section Endpoints

Documentation for the 7 individual coaching section endpoints created for the Otto coaching dashboard.

## Overview

These endpoints break down the combined individual dashboard into granular, independently accessible sections. Each endpoint returns a specific coaching data category with the same response structure as the combined dashboard, but can be called separately for more flexibility and performance optimization.

**Base URL:** `/api/v1/coaching/reps/{user_id}`

**Authentication:** All endpoints require `EXECUTIVE` role

**Company Scoping:** All endpoints require `company_id` query parameter for data scoping

---

## 1. Get Rep Coaching Issues

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/issues
```

### Description
Returns coaching issues grouped by type, sorted by frequency. Issues are identified patterns where the rep needs improvement.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get issues for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `start_date` | date | No | 30 days ago | Start date for filtering (YYYY-MM-DD) |
| `end_date` | date | No | Today | End date for filtering (YYYY-MM-DD) |

### Response Structure
```json
{
  "rep_id": "uuid",
  "rep_name": "string",
  "total_issues": 0,
  "issues": [
    {
      "issue": "string",
      "severity": "high|medium|low",
      "frequency": 1,
      "why_it_matters": "string",
      "how_to_fix": "string",
      "example_language": "string",
      "transcript_evidence": ["string"],
      "related_sop_metric": "string",
      "call_ids": ["string"]
    }
  ]
}
```

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/issues?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&start_date=2026-03-15&end_date=2026-03-25
```

### Example Response
```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "total_issues": 3,
  "issues": [
    {
      "issue": "Not asking discovery questions",
      "severity": "high",
      "frequency": 5,
      "why_it_matters": "Discovery questions help qualify the lead and understand their needs",
      "how_to_fix": "Start every call with 'What's prompting you to look into this today?'",
      "example_language": "What's your biggest concern with your current roof?",
      "transcript_evidence": [
        "Rep jumped straight to pricing without asking about the customer's needs"
      ],
      "related_sop_metric": "qualification_score",
      "call_ids": ["call-id-1", "call-id-2"]
    }
  ]
}
```

### Data Source
**Local Database** - `coaching_issues` table

---

## 2. Get Rep Coaching Strengths

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/strengths
```

### Description
Returns coaching strengths grouped by behavior, sorted by frequency. Strengths are positive patterns that should be reinforced.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get strengths for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `start_date` | date | No | 30 days ago | Start date for filtering (YYYY-MM-DD) |
| `end_date` | date | No | Today | End date for filtering (YYYY-MM-DD) |

### Response Structure
```json
{
  "rep_id": "uuid",
  "rep_name": "string",
  "total_strengths": 0,
  "strengths": [
    {
      "behavior": "string",
      "frequency": 1,
      "why_effective": "string",
      "transcript_evidence": ["string"],
      "related_sop_metric": "string",
      "call_ids": ["string"]
    }
  ]
}
```

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/strengths?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&start_date=2026-03-15&end_date=2026-03-25
```

### Example Response
```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "total_strengths": 2,
  "strengths": [
    {
      "behavior": "Excellent rapport building",
      "frequency": 8,
      "why_effective": "Creates trust and makes customers comfortable sharing their concerns",
      "transcript_evidence": [
        "Rep used customer's name throughout the call and showed empathy"
      ],
      "related_sop_metric": "rapport_score",
      "call_ids": ["call-id-1", "call-id-2"]
    }
  ]
}
```

### Data Source
**Local Database** - `coaching_strengths` table

---

## 3. Get Rep Progression

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/progression
```

### Description
Returns weekly metric trends with anomaly detection. Shows how the rep's performance has changed over time.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get progression for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `weeks` | int | No | 8 | Number of weeks to analyze (4-52, Shunya API requirement) |

### Response Structure
```json
{
  "rep_id": "string",
  "rep_name": "string",
  "weeks": 8,
  "metrics": [
    {
      "metric": "string",
      "data_points": [
        {
          "week": "string",
          "value": 0,
          "is_anomaly": false,
          "trend": "up|down|stable"
        }
      ]
    }
  ]
}
```

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/progression?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&weeks=8
```

### Data Source
**Shunya API** - Proxied from `/api/v1/insights/agents/{rep_id}/progression`

### Notes
- Minimum weeks value is **4** (Shunya API requirement)
- May return null if Shunya service is unavailable

---

## 4. Get Rep Peer Benchmark

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/peer-benchmark
```

### Description
Returns rep vs team comparison on 5 key metrics. Shows how the rep performs compared to their peers.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get peer benchmark for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `days` | int | No | 30 | Analysis period in days (7-365) |

### Response Structure
```json
{
  "rep_id": "string",
  "rep_name": "string",
  "company_id": "string",
  "metrics": [
    {
      "metric": "string",
      "rank": 0,
      "percentile": 0,
      "rep_score": 0,
      "peer_average": 0,
      "top_score": 0,
      "gap_to_top": 0,
      "vs_avg": 0
    }
  ]
}
```

### Metrics Included
1. `compliance_score` - SOP compliance score
2. `booking_rate` - Appointment booking rate
3. `objection_handling` - Objection handling effectiveness
4. `rapport_score` - Customer rapport score
5. `script_adherence` - Script adherence score

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/peer-benchmark?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&days=30
```

### Example Response
```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
  "metrics": [
    {
      "metric": "compliance_score",
      "rank": 3,
      "percentile": 75,
      "rep_score": 85.5,
      "peer_average": 78.2,
      "top_score": 92.3,
      "gap_to_top": 6.8,
      "vs_avg": 7.3
    }
  ]
}
```

### Data Source
**Shunya API** - Proxied from `/api/v1/insights/agents/{rep_id}/peer-comparison`

### Notes
- May return null if Shunya service is unavailable
- Fetches all 5 metrics in parallel for performance

---

## 5. Get Rep Coaching Impact

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/impact
```

### Description
Returns coaching session history with baseline vs post-coaching scores. Shows the effectiveness of coaching interventions.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get coaching impact for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |

### Response Structure
```json
{
  "rep_id": "uuid",
  "rep_name": "string",
  "sessions": [
    {
      "session_id": "uuid",
      "coached_at": "2026-03-25T12:00:00Z",
      "focus_areas": ["string"],
      "status": "in_progress|completed",
      "follow_up_days": 14,
      "follow_up_end_date": "2026-04-08T12:00:00Z",
      "baseline_scores": {
        "compliance_score": 0.75,
        "booking_rate": 0.45
      },
      "impact_scores": {
        "compliance_score": 0.82,
        "booking_rate": 0.51
      },
      "overall_improved": true,
      "improvement_pct": 8.5,
      "targets_met": {
        "compliance_score": true,
        "booking_rate": false
      },
      "days_into_follow_up": 7
    }
  ]
}
```

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/impact?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37
```

### Data Source
**Local Database** - `coaching_sessions` table

### Notes
- Not date-filtered (returns all coaching sessions for the rep)
- Sessions are sorted by `coached_at` descending (most recent first)

---

## 6. Get Rep Objection Handling Stats

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/objections
```

### Description
Returns objection categories with rep overcome rate vs team average. Identifies objection types where the rep struggles.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get objections for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `start_date` | date | No | 30 days ago | Start date for filtering (YYYY-MM-DD) |
| `end_date` | date | No | Today | End date for filtering (YYYY-MM-DD) |

### Response Structure
```json
{
  "rep_id": "uuid",
  "rep_name": "string",
  "total_objections": 0,
  "categories": [
    {
      "category": "string",
      "total_count": 0,
      "overcome_count": 0,
      "rep_overcome_rate": 0,
      "team_avg_overcome_rate": 0,
      "delta_vs_team": 0
    }
  ]
}
```

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/objections?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&start_date=2026-03-15&end_date=2026-03-25
```

### Example Response
```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "total_objections": 45,
  "categories": [
    {
      "category": "Price",
      "total_count": 20,
      "overcome_count": 12,
      "rep_overcome_rate": 60.0,
      "team_avg_overcome_rate": 72.5,
      "delta_vs_team": -12.5
    },
    {
      "category": "Timing",
      "total_count": 15,
      "overcome_count": 13,
      "rep_overcome_rate": 86.7,
      "team_avg_overcome_rate": 78.0,
      "delta_vs_team": 8.7
    }
  ]
}
```

### Data Source
**Local Database** - `call_objection_details` table

### Notes
- Categories are sorted by total count (most frequent first)
- Negative `delta_vs_team` indicates the rep is below team average

---

## 7. Get Rep Smart Nudges

### Endpoint
```
GET /api/v1/coaching/reps/{user_id}/nudges
```

### Description
Returns AI-generated coaching recommendations based on issues, objections, and performance trends.

### Path Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | UUID | Yes | UUID of the rep to get nudges for |

### Query Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `company_id` | UUID | Yes | - | Company UUID for data scoping |
| `start_date` | date | No | 30 days ago | Start date for filtering (YYYY-MM-DD) |
| `end_date` | date | No | Today | End date for filtering (YYYY-MM-DD) |

### Response Structure
```json
{
  "rep_id": "uuid",
  "rep_name": "string",
  "nudges": [
    {
      "title": "string",
      "message": "string",
      "priority": "high|medium|low",
      "timing": "immediate|pre_call|weekly",
      "source": "coaching_issues|objection_history|progression",
      "related_data": {}
    }
  ]
}
```

### Nudge Generation Rules

**1. High-Frequency Issues (Immediate)**
- Trigger: Issue appears 3+ times with `severity="high"`
- Priority: `high`
- Timing: `immediate`

**2. Recurring Issues (Immediate)**
- Trigger: Issue appears 2+ times
- Priority: `medium`
- Timing: `immediate`

**3. Low Objection Overcome Rate (Pre-Call)**
- Trigger: Overcome rate < 30% with 3+ occurrences
- Priority: `high` if delta vs team < -20%, else `medium`
- Timing: `pre_call`

**4. Declining Performance (Weekly)**
- Trigger: Compliance score trending down
- Priority: `medium`
- Timing: `weekly`

**5. Improving Performance (Weekly)**
- Trigger: Compliance score trending up
- Priority: `low`
- Timing: `weekly`

### Example Request
```bash
GET /api/v1/coaching/reps/573c5f36-dcc5-4440-b8fd-58699807544a/nudges?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&start_date=2026-03-15&end_date=2026-03-25
```

### Example Response
```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "nudges": [
    {
      "title": "Not asking discovery questions",
      "message": "This issue appeared in 5 calls. Review the SOP and practice the recommended approach.",
      "priority": "high",
      "timing": "immediate",
      "source": "coaching_issues",
      "related_data": {}
    },
    {
      "title": "Upcoming Call: Price",
      "message": "You overcome 'Price' objections only 60% of the time (team avg: 73%). Practice the value framework for this objection type.",
      "priority": "high",
      "timing": "pre_call",
      "source": "objection_history",
      "related_data": {}
    }
  ]
}
```

### Data Source
**Computed** - Aggregates data from:
- `coaching_issues` table
- `call_objection_details` table
- `call_analyses` table (for compliance trends)

### Notes
- Nudges are sorted by priority (high → medium → low)
- Combines data from multiple sources for comprehensive recommendations

---

## Common Response Codes

### Success Codes
| Code | Description |
|------|-------------|
| 200 | Success - Data returned |

### Error Codes
| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid parameters (e.g., weeks < 4 for progression) |
| 401 | Unauthorized - Missing or invalid authentication |
| 403 | Forbidden - User does not have EXECUTIVE role or accessing different company |
| 404 | Not Found - User ID not found |
| 422 | Unprocessable Entity - Invalid query parameters from Shunya API |
| 500 | Internal Server Error - Database or application error |
| 503 | Service Unavailable - Shunya API unavailable (progression/peer-benchmark only) |

---

## Authentication

All endpoints require authentication with an `EXECUTIVE` role user. Include the bearer token in the request headers:

```bash
Authorization: Bearer <your-jwt-token>
```

---

## Company Scoping

All endpoints enforce company scoping:
- The `company_id` query parameter is **required**
- Executives can only access data for their own company
- Attempting to access another company's data returns `403 Forbidden`

---

## Testing

### Test Data Available

**Company:** `ce9091df-db37-4e7e-877c-2ed0cf2f4c37` (Arizona Roofers)

**Users with Data:**
- `573c5f36-dcc5-4440-b8fd-58699807544a` (Diva Shahpur) - Has objections, issues, strengths data
- `f7c41116-884b-4f0e-be96-34046a30fd5d` (William Ludewig) - Limited data

**Recommended Date Range for Testing:**
- `start_date=2026-03-02`
- `end_date=2026-03-25`

### Example Test Script

```bash
# Base URL
BASE_URL="http://localhost:8000/api/v1/coaching/reps"
USER_ID="573c5f36-dcc5-4440-b8fd-58699807544a"
COMPANY_ID="ce9091df-db37-4e7e-877c-2ed0cf2f4c37"

# Test all endpoints
curl "$BASE_URL/$USER_ID/issues?company_id=$COMPANY_ID"
curl "$BASE_URL/$USER_ID/strengths?company_id=$COMPANY_ID"
curl "$BASE_URL/$USER_ID/progression?company_id=$COMPANY_ID&weeks=4"
curl "$BASE_URL/$USER_ID/peer-benchmark?company_id=$COMPANY_ID&days=30"
curl "$BASE_URL/$USER_ID/impact?company_id=$COMPANY_ID"
curl "$BASE_URL/$USER_ID/objections?company_id=$COMPANY_ID"
curl "$BASE_URL/$USER_ID/nudges?company_id=$COMPANY_ID"
```

---

## Performance Notes

1. **Database Endpoints** (issues, strengths, objections, impact, nudges):
   - Fast response times (typically < 200ms)
   - Data fetched from local PostgreSQL database
   - Sequential execution for thread safety

2. **Shunya Endpoints** (progression, peer-benchmark):
   - Slower response times (typically 500-2000ms)
   - Depends on external Shunya API availability
   - May return null if Shunya is unavailable
   - Progression: minimum 4 weeks required
   - Peer-benchmark: fetches 5 metrics in parallel

3. **Computed Endpoints** (nudges):
   - Moderate response times (200-500ms)
   - Aggregates data from multiple tables
   - Applies business logic for nudge generation

---

## Migration from Combined Dashboard

If you're currently using `/api/v1/coaching/individual-dashboard/{user_id}`, you can migrate to granular endpoints:

**Before:**
```bash
GET /api/v1/coaching/individual-dashboard/{user_id}?company_id=xxx
# Returns all 7 sections in one call
```

**After (Granular):**
```bash
# Fetch only what you need
GET /api/v1/coaching/reps/{user_id}/issues?company_id=xxx
GET /api/v1/coaching/reps/{user_id}/strengths?company_id=xxx
# etc.
```

**Benefits:**
- Fetch only the sections you need
- Faster response times for individual sections
- Better error isolation (one section failing doesn't affect others)
- More flexible caching strategies

---

## Changelog

### v1.0.0 (2026-03-25)
- Initial release of 7 granular coaching endpoints
- Fixed progression endpoint to require minimum 4 weeks (Shunya API requirement)
- Fixed nudges endpoint database session concurrency issue
- Added RepProgressionResponse type for better type safety

---

## Support

For questions or issues with these APIs, contact the Otto development team or refer to the main API documentation.
