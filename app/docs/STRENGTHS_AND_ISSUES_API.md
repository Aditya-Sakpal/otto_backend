# Strengths & Issues API

**Endpoint:** `GET /api/v1/metrics/coaching/strengths-and-issues`

**Description:** Unified endpoint that combines Shunya's coaching profile (15 canonical categories with severity distributions and representative call excerpts) with Otto's DB performance metrics (booking rate, conversion rate, objection-based coaching needs, trends). Returns a complete picture of a rep's strengths and weaknesses in a single call.

**Authentication:** Required (Bearer JWT)

---

## Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `user_id` | UUID | Yes | - | Rep/CSR user UUID (also used as Shunya `rep_id`) |
| `company_id` | UUID | No | Auto-resolved from user | Company UUID. If omitted, resolved from DB or JWT token. |
| `window_days` | int (7-180) | No | 30 | Time window for Shunya coaching aggregation |
| `force_refresh` | bool | No | false | Force Shunya to rebuild the profile (may take 30-60s on first call) |
| `start_date` | date (YYYY-MM-DD) | No | 30 days ago | Start date for DB performance metrics |
| `end_date` | date (YYYY-MM-DD) | No | Today | End date for DB performance metrics |

---

## cURL Example

```bash
curl -X GET "https://your-host/api/v1/metrics/coaching/strengths-and-issues?user_id=573c5f36-dcc5-4440-b8fd-58699807544a&company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37&window_days=30&force_refresh=false" \
  -H "Authorization: Bearer <your_jwt_token>"
```

---

## Response (200 OK)

```json
{
  "rep_id": "573c5f36-dcc5-4440-b8fd-58699807544a",
  "rep_name": "Diva Shahpur",
  "company_id": "ce9091df-db37-4e7e-877c-2ed0cf2f4c37",
  "window_start": "2026-03-03T15:35:02.564000",
  "window_end": "2026-04-02T15:35:02.564000",
  "calls_analyzed": 476,

  "top_weaknesses": [
    {
      "category": "Needs Discovery",
      "count": 218,
      "severity_distribution": { "high": 85, "medium": 119, "low": 14 },
      "representative_examples": [
        "After the caller explained they needed proof for insurance...",
        "After the caller described active water intrusion...",
        "After the homeowner explained they mainly want a skylight removal..."
      ],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-04-01T23:04:13.308000"
    }
  ],

  "top_strengths": [
    {
      "category": "Greeting & Rapport",
      "count": 221,
      "severity_distribution": null,
      "representative_examples": [
        "Opened with a professional greeting including the company name..."
      ],
      "related_sop_metrics": [],
      "latest_occurrence": "2026-04-01T23:45:44.606000"
    }
  ],

  "all_weakness_buckets": [ "... (all 15 categories)" ],
  "all_strength_buckets": [ "... (all categories with counts)" ],

  "db_performance_metrics": {
    "total_calls": 500,
    "calls_answered": 480,
    "calls_answered_percentage": 96.0,
    "missed_calls": 20,
    "missed_calls_status": "low",
    "booking_rate": 45.2,
    "conversion_rate": 12.5,
    "avg_response_time": 8.3,
    "response_time_status": "on_target",
    "avg_sop_compliance_score": 72.4,
    "qualified_leads": 120,
    "booked_appointments": 54,
    "rank": 2,
    "total_csrs": 8,
    "top_objections": [
      {
        "objection": "Price",
        "pct_unbooked": 42.5,
        "unbooked_qualified_ratio": "17/40",
        "unbooked_count": 17,
        "qualified_count": 40
      }
    ],
    "booking_rate_trend": [
      {
        "period_start": "2026-03-05T00:00:00",
        "period_end": "2026-03-12T00:00:00",
        "booking_rate": 38.5,
        "booked": 5,
        "qualified": 13
      }
    ]
  },

  "calculated_at": "2026-04-02T15:36:30.426439",
  "data_sources": ["shunya_coaching_profile", "otto_db_metrics"]
}
```

---

## Response Field Reference

### Top-Level Fields

| Field | Type | Source | Description |
|---|---|---|---|
| `rep_id` | string | Shunya | Rep identifier |
| `rep_name` | string | Shunya | Rep display name |
| `company_id` | string | Shunya | Company identifier |
| `window_start` | datetime | Shunya | Start of coaching analysis window |
| `window_end` | datetime | Shunya | End of coaching analysis window |
| `calls_analyzed` | int | Shunya | Number of calls analyzed by Shunya |
| `top_weaknesses` | array | Shunya | Top 3 weakness categories by count |
| `top_strengths` | array | Shunya | Top 3 strength categories by count |
| `all_weakness_buckets` | array | Shunya | All 15 canonical weakness categories |
| `all_strength_buckets` | array | Shunya | All strength categories with counts |
| `db_performance_metrics` | object | Otto DB | Performance metrics from our database |
| `calculated_at` | datetime | Shunya | When the profile was last computed |
| `data_sources` | array | Both | Which data sources contributed to this response |

### Coaching Bucket Object (Strengths & Weaknesses)

| Field | Type | Description |
|---|---|---|
| `category` | string | One of 15 canonical categories (see list below) |
| `count` | int | Total occurrences across all calls in the time window |
| `severity_distribution` | object/null | `{"high": N, "medium": N, "low": N}` (weaknesses only; null for strengths) |
| `representative_examples` | array | Up to 3 real call excerpts showing the behavior |
| `related_sop_metrics` | array | SOP metric IDs associated with this category |
| `latest_occurrence` | datetime | Most recent occurrence in this category |

### 15 Canonical Categories

1. Needs Discovery
2. Setting Expectations
3. Follow-Up & Next Steps
4. Closing Technique
5. Scheduling & Booking
6. Qualification (BANT)
7. Greeting & Rapport
8. Compliance & Script Adherence
9. Active Listening
10. Objection Handling
11. Product/Service Knowledge
12. Empathy & Tone
13. Price Presentation
14. Urgency Creation
15. Other

### DB Performance Metrics Object

| Field | Type | Description |
|---|---|---|
| `total_calls` | int | Total calls handled by this rep |
| `calls_answered` | int | Number of calls answered |
| `calls_answered_percentage` | float | % of calls answered |
| `missed_calls` | int | Number of missed calls |
| `missed_calls_status` | string | `"low"` / `"medium"` / `"high"` |
| `booking_rate` | float | Booking rate percentage |
| `conversion_rate` | float | Won appointments / qualified leads % |
| `avg_response_time` | float | Average response time in seconds |
| `response_time_status` | string | `"on_target"` / `"above_target"` / `"below_target"` |
| `avg_sop_compliance_score` | float | Average SOP compliance score (0-100) |
| `qualified_leads` | int | Number of qualified leads |
| `booked_appointments` | int | Number of booked appointments |
| `rank` | int/null | Rank among CSRs in the company (1-based) |
| `total_csrs` | int | Total CSRs in the company |
| `top_objections` | array | Top 3 objection-based coaching needs (see below) |
| `booking_rate_trend` | array | Weekly booking rate trend (last 4 weeks) |

### Top Objections Object

| Field | Type | Description |
|---|---|---|
| `objection` | string | Objection category name |
| `pct_unbooked` | float | % of qualified leads with this objection that were NOT booked |
| `unbooked_qualified_ratio` | string | e.g. `"17/40"` |
| `unbooked_count` | int | Number of unbooked qualified leads with this objection |
| `qualified_count` | int | Total qualified leads with this objection |

### Booking Rate Trend Object

| Field | Type | Description |
|---|---|---|
| `period_start` | datetime | Week start |
| `period_end` | datetime | Week end |
| `booking_rate` | float | Booking rate for this week |
| `booked` | int | Appointments booked |
| `qualified` | int | Qualified leads |

---

## Graceful Degradation

The endpoint is resilient to partial failures:

| Scenario | Behavior |
|---|---|
| Shunya unavailable | Returns empty coaching buckets + full DB metrics |
| Database unavailable | Returns full Shunya coaching data + zeroed DB metrics |
| Both available | Returns the complete unified response |

The `data_sources` field indicates which sources contributed: `["shunya_coaching_profile", "otto_db_metrics"]` or a subset.

---

## Performance Notes

- First request with `force_refresh=true` may take 30-60s (Shunya classifies items in batches of 50)
- Subsequent requests return Shunya's cached profile (24h TTL)
- DB metrics are computed on each request (no caching)
- Nightly job at 03:00 UTC rebuilds Shunya profiles for reps with recent calls

---

## Files Changed

| File | Change |
|---|---|
| `app/domain/schemas/metrics.py` | Added `StrengthsAndIssuesResponse`, `CoachingBucket`, `SeverityDistribution`, `DBPerformanceMetrics`, `ObjectionCoachingNeed` schemas |
| `app/infrastructure/integrations/shoonya.py` | Added `get_coaching_profile()` method to `ShoonyaClient` |
| `app/services/metrics_service.py` | Added `get_strengths_and_issues()` method to `MetricsService` |
| `app/routes/v1/metrics.py` | Added `GET /coaching/strengths-and-issues` endpoint |
