# TenantConfiguration Default Specification

This document outlines the default values and structures for the `TenantConfiguration` model.

## Top-Level Fields

| Field | Default Value |
|-------|---------------|
| config_id | **Required** (No default) |
| company_id | **Required** (No default) |
| company_name | **Required** (No default) |
| industry | `"home_services"` |
| primary_services | `[]` |
| version | `1` |
| is_active | `True` |
| created_at | `datetime.utcnow()` |
| updated_at | `datetime.utcnow()` |
| created_by | `None` |
| updated_by | `None` |
| service_area | `[]` |

---

## Nested Configurations

### 1. QualificationThresholds

| Field | Default Value |
|-------|---------------|
| hot_min_score | `0.75` |
| warm_min_score | `0.5` |
| cold_min_score | `0.25` |
| need_weight | `0.3` |
| budget_weight | `0.2` |
| authority_weight | `0.2` |
| timeline_weight | `0.3` |

### 2. QualificationRules

- **Default:** `[]` (Empty list)
- **Structure:**
  - `rule_id`: Required
  - `name`: Required
  - `description`: Required
  - `condition`: Required
  - `action`: Required
  - `action_value`: `None`
  - `priority`: `0`
  - `enabled`: `True`

### 3. ServicePrioritization

| Field | Default Value |
|-------|---------------|
| services | `[]` |
| defer_low_ticket_during_high_demand | `False` |
| high_demand_threshold | `None` |
| default_priority | `ServicePriority.NORMAL` |

**ServiceConfig** (within services):

- `service_type`: Required
- `display_name`: Required
- `priority`: `NORMAL`
- `current_wait_time_weeks`: `None`
- `is_active`: `True`
- `qualification_boost`: `0.0`
- `notes`: `None`

### 4. CustomKeywords

| Field | Default Value |
|-------|---------------|
| urgency_keywords | `[]` |
| budget_keywords | `[]` |
| objection_keywords | `[]` |
| service_keywords | `{}` |

### 5. BusinessHours

| Field | Default Value |
|-------|---------------|
| timezone | `"America/Phoenix"` |
| weekday_start | `"08:00"` |
| weekday_end | `"18:00"` |
| saturday_start | `"09:00"` |
| saturday_end | `"14:00"` |
| sunday_closed | `True` |
| holidays | `[]` |

### 6. PropertyDetailsConfig

| Field | Default Value |
|-------|---------------|
| extract_roof_type | `True` |
| extract_roof_age | `True` |
| extract_hoa_status | `True` |
| extract_gated_status | `True` |
| extract_pets | `True` |
| extract_solar | `True` |
| custom_property_fields | `[]` |

### 7. ScopeConfig

| Field | Default Value |
|-------|---------------|
| excluded_tags | `["production", "accounting"]` |
| excluded_call_path_options | `["4"]` |
| tag_confidence | `{"production": 0.9, "accounting": 0.85}` |
| call_path_confidence | `0.8` |
| llm_confidence_threshold | `0.7` |
| custom_out_of_scope_signals | `[]` |
| custom_in_scope_signals | `[]` |

### 8. IndustryContext

| Field | Default Value |
|-------|---------------|
| industry_description | `None` |
| service_focus | `[]` |
| geographic_region | `None` |
| high_urgency_signals | `["active leak", "water coming in", "emergency", "storm damage", "hail damage"]` |
| medium_urgency_signals | `["before monsoon", "insurance deadline", "inspection period"]` |
| custom_urgency_signals | `[]` |
| extractable_fields | *(See below)* |
| call_stages | `["Greeting & Identification", "Needs Discovery", "Qualifying", "Scheduling", "Setting Expectations", "Close & Confirmation"]` |
| call_stage_descriptions | `{}` |
| decision_maker_indicators | *(See below)* |

**Default Extractable Fields:**

- `roof_type`: tile, shingle, flat, metal, foam
- `property_stories`: single story, two story
- `hoa_status`: in an HOA or not
- `gated_community`: gated or not gated
- `pets_on_property`: dogs, cats on property
- `solar_panels`: solar on the roof or not
- `roof_age`: age of roof in years

**Decision Maker Indicators:**

- `primary`: `["I decide", "it's my house", "I'm the owner"]`
- `secondary`: `["spouse", "husband", "wife", "partner"]`
- `approval_needed`: `["need to check with", "husband has to see", "need approval"]`

### 9. ScoringConfig

| Field | Default Value |
|-------|---------------|
| objection_penalties | `{"high": -10, "medium": -5, "low": -2}` |
| objection_type_multipliers | `{"price": 1.5, "competitor": 1.2, "timing": 1.0, "trust": 1.3, "authority": 1.1, "need": 0.8, "other": 1.0}` |
| bonuses | `{"urgency_high": 10, "urgency_medium": 5, "referral": 10, "inbound": 5, "multiple_decision_makers": 5, "explicit_need": 5}` |
| urgent_timeline_keywords | `["asap", "immediately", "urgent", "emergency", "this week", "next week", "today", "tomorrow"]` |
| nearterm_timeline_keywords | `["30 days", "1 month", "this month", "next month", "60 days", "2 months"]` |
| medium_timeline_keywords | `["90 days", "3 months", "quarter", "few months"]` |

### 10. CoachingConfig

| Field | Default Value |
|-------|---------------|
| min_calls_for_baseline | `5` |
| min_calls_for_validation | `5` |
| default_follow_up_days | `14` |
| extension_days | `7` |
| max_extensions | `1` |
| outlier_percentile | `0.10` |
| improvement_threshold | `0.05` |

### 11. CoachingAggregationConfig

| Field | Default Value |
|-------|---------------|
| aggregation_window_days | `30` |
| canonical_categories | `["Greeting & Rapport", "Needs Discovery", "Qualification (BANT)", "Objection Handling", "Closing Technique", "Scheduling & Booking", "Setting Expectations", "Follow-Up & Next Steps", "Empathy & Tone", "Product/Service Knowledge", "Compliance & Script Adherence", "Urgency Creation", "Active Listening", "Price Presentation", "Other"]` |
| min_calls_for_profile | `3` |
| max_examples_per_bucket | `3` |

### 12. InsightsConfig

| Field | Default Value |
|-------|---------------|
| change_threshold | `0.05` |
| booking_rate_threshold | `0.5` |
| objection_similarity_threshold | `0.5` |
| objection_handling_threshold | `0.8` |
| default_qualification_status | `"cold"` |

---

## Database Fallback Logic

When no tenant configuration is found for a `company_id`, `get_default_tenant_config()` initializes a configuration with the following overrides:

- **config_id:** `default_{company_id}`
- **industry:** `"home_services"`
- **primary_services:** `["general"]`
- **services:** Includes one `ServiceConfig` with:
  - `service_type`: `"general"`
  - `display_name`: `"General Service"`
  - `priority`: `NORMAL`
