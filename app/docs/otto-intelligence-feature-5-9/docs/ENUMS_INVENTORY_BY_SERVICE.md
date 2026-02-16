# Enums Inventory by Service

**Date**: 2025-12-08  
**Status**: ✅ Complete  
**Purpose**: Comprehensive reference of all enums used across Shunya (ottoai-rag) services

---

## Table of Contents

1. [Lead Qualification Service](#lead-qualification-service)
2. [Performance Evaluation Service](#performance-evaluation-service)
3. [Pending Actions Service](#pending-actions-service)
4. [Meeting Segmentation Service](#meeting-segmentation-service)
5. [Opportunity Analysis Service](#opportunity-analysis-service)
6. [Objection Detection Service](#objection-detection-service)
7. [Transcription Service](#transcription-service)
8. [API Versioning](#api-versioning)
9. [Summary Table](#summary-table)

---

## Lead Qualification Service

**File**: `app/core/constants/lead_qualification_enums.py`  
**Purpose**: Enums for evaluating leads/customers (not rep performance)

### 1. QualificationStatus

**Enum**: `QualificationStatus`  
**Type**: `str, Enum`  
**Values**:
- `HOT = "hot"` - High urgency, ready to close, strong buying signals
- `WARM = "warm"` - Showing interest but not urgent, needs nurturing
- `COLD = "cold"` - Low interest, informational stage, long-term nurturing needed
- `UNQUALIFIED = "unqualified"` - Not a fit for our services or not a genuine lead

**Metadata**: Includes criteria, urgency_score, priority, typical_close_rate  
**Used In**: Lead qualification analysis, LLM prompts

---

### 2. BookingStatus

**Enum**: `BookingStatus`  
**Type**: `str, Enum`  
**Values**:
- `BOOKED = "booked"` - Appointment scheduled with confirmed date/time
- `NOT_BOOKED = "not_booked"` - No appointment scheduled yet, requires follow-up
- `SERVICE_NOT_OFFERED = "service_not_offered"` - Customer needs service we don't provide

**Metadata**: Includes requirements flags, success_metric, conversion_weight  
**Used In**: Appointment booking analysis, LLM prompts

---

### 3. AppointmentType

**Enum**: `AppointmentType`  
**Type**: `str, Enum`  
**Values**:
- `IN_PERSON = "in-person"` - Physical meeting at customer location or office
- `VIRTUAL = "virtual"` - Video call meeting (Zoom, Teams, Google Meet, etc.)
- `PHONE = "phone"` - Phone conversation appointment

**Metadata**: Includes requirements flags, typical_duration_minutes, close_rate_multiplier  
**Used In**: Appointment scheduling, LLM prompts (only if booking_status is "booked")

---

### 4. CallOutcomeCategory

**Enum**: `CallOutcomeCategory`  
**Type**: `str, Enum`  
**Values**:
- `QUALIFIED_AND_BOOKED = "qualified_and_booked"` - Lead is qualified and appointment successfully scheduled
- `QUALIFIED_SERVICE_NOT_OFFERED = "qualified_service_not_offered"` - Lead is qualified but we don't offer the service they need
- `QUALIFIED_BUT_UNBOOKED = "qualified_but_unbooked"` - Lead is qualified but no appointment scheduled yet

**Metadata**: Includes success_level, derived_from, expected_outcome, success_weight  
**Computed**: Yes (from qualification_status + booking_status)  
**Used In**: Call outcome analysis, reporting

---

## Performance Evaluation Service

**File**: `app/core/constants/performance_evaluation_enums.py`  
**Purpose**: Enums for evaluating sales rep/CSR performance (not customer/lead)

### 5. OutcomeDecision

**Enum**: `OutcomeDecision`  
**Type**: `str, Enum`  
**Values**:
- `PASS = "pass"` - Rep's call performance meets or exceeds standards (score >= 80)
- `NEEDS_COACHING = "needs_coaching"` - Rep's call performance acceptable but needs improvement (score 60-79)
- `FAIL = "fail"` - Rep's call performance below minimum standards or has critical errors (score < 60)

**Metadata**: Includes score_threshold_min/max, requires_coaching, critical_errors_allowed, action_required, rep_status  
**Computed**: Yes (from overall_outcome_score + has_critical_error)  
**Used In**: Compliance service, outcome scoring (Layer 2 evaluation), rep performance assessment

**Business Logic**:
1. Any critical error → fail (overrides score)
2. Score >= 80 → pass
3. Score >= 60 → needs_coaching
4. Score < 60 → fail

---

## Pending Actions Service

**File**: `app/core/constants/pending_action_types.py`  
**Purpose**: Enums for call analysis pending actions

### 6. ActionType

**Enum**: `ActionType`  
**Type**: `str, Enum`  
**Values** (30 total):

#### Callback / Follow-Up (CSR)
- `CALL_BACK = "call_back"` - Customer requested callback
- `FOLLOW_UP_CALL = "follow_up_call"` - Scheduled follow-up call
- `CHECK_IN = "check_in"` - Check on status or decision

#### Send Information (CSR)
- `SEND_QUOTE = "send_quote"` - Send pricing quote
- `SEND_ESTIMATE = "send_estimate"` - Send cost estimate
- `SEND_CONTRACT = "send_contract"` - Send contract/agreement
- `SEND_INFO = "send_info"` - Send general information
- `SEND_PHOTOS = "send_photos"` - Send photos/images
- `SEND_DETAILS = "send_details"` - Send specific details

#### Scheduling (CSR)
- `SCHEDULE_APPOINTMENT = "schedule_appointment"` - Book appointment
- `SCHEDULE_VISIT = "schedule_visit"` - Schedule site visit
- `RESCHEDULE = "reschedule"` - Change existing appointment
- `CONFIRM_APPOINTMENT = "confirm_appointment"` - Confirm existing booking

#### Field Work (REP)
- `SITE_VISIT = "site_visit"` - On-site visit
- `INSPECTION = "inspection"` - Inspection visit
- `MEASUREMENT = "measurement"` - Take measurements

#### Verification (CSR)
- `VERIFY_INSURANCE = "verify_insurance"` - Check insurance coverage
- `VERIFY_DETAILS = "verify_details"` - Confirm customer information
- `CHECK_AVAILABILITY = "check_availability"` - Check schedule availability
- `CONFIRM_ADDRESS = "confirm_address"` - Verify location

#### Documentation (CSR)
- `PREPARE_CONTRACT = "prepare_contract"` - Draft contract
- `COLLECT_DOCUMENTS = "collect_documents"` - Gather paperwork
- `SEND_INVOICE = "send_invoice"` - Send billing invoice

#### Escalation (MANAGER)
- `ESCALATE = "escalate"` - Escalate to manager
- `MANAGER_REVIEW = "manager_review"` - Manager review needed
- `GET_APPROVAL = "get_approval"` - Get approval

#### Financial (CSR)
- `SETUP_FINANCING = "setup_financing"` - Set up payment plan
- `PROCESS_PAYMENT = "process_payment"` - Process payment
- `SEND_PAYMENT_LINK = "send_payment_link"` - Send payment portal link

#### Custom (Fallback)
- `CUSTOM = "custom"` - Custom action

**Metadata**: Includes category, default_assignee, typical_contact_method, typical_due_timing, description, examples  
**Used In**: Summarization service, LLM prompts, task creation

---

### 7. ContactMethod

**Enum**: `ContactMethod`  
**Type**: `str, Enum`  
**Values**:
- `PHONE = "phone"` - Phone call
- `EMAIL = "email"` - Email
- `SMS = "sms"` - Text message
- `IN_PERSON = "in_person"` - In-person meeting
- `ANY = "any"` - Any method

**Used In**: Pending actions, task assignment

---

## Meeting Segmentation Service

**File**: `app/core/constants/meeting_segmentation_phases.py`  
**Purpose**: Enums for sales meeting segmentation phases

### 8. MeetingPhase

**Enum**: `MeetingPhase`  
**Type**: `str, Enum`  
**Values**:
- `RAPPORT_AGENDA = "rapport_agenda"` - Part 1: Relationship building, agenda setting, discovery, and needs assessment phase
- `PROPOSAL_CLOSE = "proposal_close"` - Part 2: Presentation of solutions, pricing discussion, objection handling, and closing phase

**Metadata**: Includes label, database_prefix, description, activities, indicators, typical_duration_percent, key_objectives  
**Used In**: Meeting segmentation analysis, sales appointment analysis

**Database Fields**:
- Part 1: `part1_start_time`, `part1_end_time`, `part1_duration`, `part1_content`, `part1_key_points`
- Part 2: `part2_start_time`, `part2_end_time`, `part2_duration`, `part2_content`, `part2_key_points`

---

## Opportunity Analysis Service

**File**: `app/core/constants/missed_opportunity_types.py`  
**Purpose**: Enums for missed opportunity classification

### 9. MissedOpportunityType

**Enum**: `MissedOpportunityType`  
**Type**: `str, Enum`  
**Values**:
- `DISCOVERY = "discovery"` - Missed questions during needs discovery phase
- `CROSS_SELL = "cross_sell"` - Missed opportunity to offer additional/complementary services
- `UPSELL = "upsell"` - Missed opportunity to suggest premium/upgraded options
- `QUALIFICATION = "qualification"` - Missed BANT (Budget, Authority, Need, Timeline) questions

**Metadata**: Includes label, category, severity, description, examples, common_patterns, training_focus, impact_level  
**Used In**: Opportunity analysis, coaching recommendations

**Categories**:
- `needs_assessment`: discovery, qualification
- `revenue_expansion`: cross_sell, upsell

---

## Objection Detection Service

**File**: `app/models/call_analysis.py` (ObjectionCategory model)  
**Database Table**: `objection_categories`  
**Purpose**: Master table for categorizing customer objections detected in calls

**Note**: Objection categories are stored in a database table (not a Python enum), but they represent a canonical list of values used throughout the system.

### Objection Categories (Database Master Table)

**Table**: `objection_categories`  
**Model**: `ObjectionCategory`  
**Total Categories**: 10

| ID | Category Text | Description |
|----|---------------|-------------|
| 1 | `Price/Budget` | Customer raises concerns about cost, affordability, or budget constraints |
| 2 | `Timing` | Customer indicates now is not the right time, wants to delay decision |
| 3 | `Competitor` | Customer mentions competitive offers or existing relationships |
| 4 | `Trust/Credibility` | Customer questions company reputation, reviews, or credibility |
| 5 | `Need/Fit` | Customer questions whether the product/service meets their needs |
| 6 | `Decision Authority` | Customer needs to consult with spouse, business partner, or decision maker |
| 7 | `Technical` | Customer has technical questions or concerns about implementation |
| 8 | `Contract Terms` | Customer objects to contract length, terms, or conditions |
| 9 | `DIY Alternative` | Customer considers doing it themselves or cheaper alternatives |
| 10 | `No Response` | Customer goes silent, stops responding, or avoids commitment |

**Database Schema**:
- `id` (Integer, Primary Key) - Auto-incrementing ID
- `category_text` (String(100), Unique) - Category name
- `description` (Text, Nullable) - Description of what this category means
- `is_active` (Boolean, Default: True) - Whether the category is active
- `created_at` (DateTime) - Timestamp
- `updated_at` (DateTime) - Timestamp

**Usage**:
- Objection detection service uses these categories to classify customer objections
- LLM prompts include these categories for consistent classification
- API responses reference categories by ID and text
- Used in analytics and reporting (top objections, objection trends)

**Related Model**: `CallObjection`
- `objection_category_id` (Foreign Key) - References `objection_categories.id`
- `objection_text` (Text) - The actual objection text from the call
- `overcome` (Boolean) - Whether the objection was overcome/addressed
- `severity` (String) - low, medium, high
- `confidence_score` (Float) - 0 to 1

**Seeding**: Categories are seeded via Alembic migration (`20251207_2103_initial_baseline.py`)

---

## Transcription Service

**File**: `app/routes/v1/transcription.py`  
**Purpose**: Enums for transcription service

### 10. CallType

**Enum**: `CallType`  
**Type**: `str, Enum`  
**Values**:
- `SALES_CALL = "sales_call"` - Sales appointment call
- `CSR_CALL = "csr_call"` - Customer service representative call

**Used In**: Transcription requests, call type classification

---

## API Versioning

**File**: `app/core/versioning.py`  
**Purpose**: Enums for API versioning

### 11. APIVersion

**Enum**: `APIVersion`  
**Type**: `str, Enum`  
**Values**:
- `V1 = "v1"` - Production API version 1
- `MOCK = "mock"` - Mock/test API version

**Used In**: API version detection, request routing

---

## Summary Table

| # | Enum | Service | Values Count | File Location |
|---|------|---------|--------------|---------------|
| 1 | `QualificationStatus` | Lead Qualification | 4 | `app/core/constants/lead_qualification_enums.py` |
| 2 | `BookingStatus` | Lead Qualification | 3 | `app/core/constants/lead_qualification_enums.py` |
| 3 | `AppointmentType` | Lead Qualification | 3 | `app/core/constants/lead_qualification_enums.py` |
| 4 | `CallOutcomeCategory` | Lead Qualification | 3 | `app/core/constants/lead_qualification_enums.py` |
| 5 | `OutcomeDecision` | Performance Evaluation | 3 | `app/core/constants/performance_evaluation_enums.py` |
| 6 | `ActionType` | Pending Actions | 30 | `app/core/constants/pending_action_types.py` |
| 7 | `ContactMethod` | Pending Actions | 5 | `app/core/constants/pending_action_types.py` |
| 8 | `MeetingPhase` | Meeting Segmentation | 2 | `app/core/constants/meeting_segmentation_phases.py` |
| 9 | `MissedOpportunityType` | Opportunity Analysis | 4 | `app/core/constants/missed_opportunity_types.py` |
| 10 | `ObjectionCategory` | Objection Detection | 10 | `app/models/call_analysis.py` (Database Table) |
| 11 | `CallType` | Transcription | 2 | `app/routes/v1/transcription.py` |
| 12 | `APIVersion` | API Versioning | 2 | `app/core/versioning.py` |

**Total**: 12 enums/categories, 71 total values

---

## Enum Usage by Service

### Lead Qualification Service
- **Enums**: 4 (QualificationStatus, BookingStatus, AppointmentType, CallOutcomeCategory)
- **Total Values**: 13
- **Primary Use**: LLM prompts, lead evaluation, appointment booking

### Performance Evaluation Service
- **Enums**: 1 (OutcomeDecision)
- **Total Values**: 3
- **Primary Use**: Rep performance assessment, compliance scoring

### Pending Actions Service
- **Enums**: 2 (ActionType, ContactMethod)
- **Total Values**: 35
- **Primary Use**: Task creation, action item extraction

### Meeting Segmentation Service
- **Enums**: 1 (MeetingPhase)
- **Total Values**: 2
- **Primary Use**: Sales appointment segmentation

### Opportunity Analysis Service
- **Enums**: 1 (MissedOpportunityType)
- **Total Values**: 4
- **Primary Use**: Missed opportunity detection, coaching recommendations

### Objection Detection Service
- **Categories**: 1 (ObjectionCategory - Database Table)
- **Total Values**: 10
- **Primary Use**: Objection classification, objection detection, analytics

### Transcription Service
- **Enums**: 1 (CallType)
- **Total Values**: 2
- **Primary Use**: Call type classification

### API Versioning
- **Enums**: 1 (APIVersion)
- **Total Values**: 2
- **Primary Use**: API version routing

---

## Enum Characteristics

### All Enums Are String Enums
All enums inherit from `str, Enum`, meaning:
- ✅ Serialize to strings in JSON responses
- ✅ Can be used directly in API responses
- ✅ Type-safe in Python code
- ✅ Compatible with Pydantic models

### Metadata Support
Most enums have associated metadata classes providing:
- Labels (human-readable names)
- Descriptions
- Business logic (thresholds, criteria)
- Examples
- Validation rules

### LLM Integration
Most enums include helper functions for:
- Generating LLM prompts
- Validating LLM outputs
- Computing derived values
- Formatting for documentation

### Validation Functions
All enums have validation functions:
- `validate_<enum_name>(value: str) -> bool`
- `get_all_<enum_name>s() -> List[str]`
- Metadata getters

---

## Import Examples

### Lead Qualification
```python
from app.core.constants.lead_qualification_enums import (
    QualificationStatus,
    BookingStatus,
    AppointmentType,
    CallOutcomeCategory,
    generate_qualification_status_prompt,
    compute_call_outcome_category
)
```

### Performance Evaluation
```python
from app.core.constants.performance_evaluation_enums import (
    OutcomeDecision,
    generate_outcome_decision_prompt,
    compute_outcome_decision
)
```

### Pending Actions
```python
from app.core.constants.pending_action_types import (
    ActionType,
    ContactMethod,
    get_action_type_metadata,
    generate_llm_prompt_action_types
)
```

### Meeting Segmentation
```python
from app.core.constants.meeting_segmentation_phases import (
    MeetingPhase,
    generate_meeting_phases_prompt,
    get_phase_metadata
)
```

### Opportunity Analysis
```python
from app.core.constants.missed_opportunity_types import (
    MissedOpportunityType,
    generate_missed_opportunity_types_prompt,
    get_missed_opportunity_type_metadata
)
```

### Objection Detection
```python
from app.models.call_analysis import ObjectionCategory, CallObjection
from app.core.database.connection import db_connection

# Query objection categories from database
with db_connection.session_factory() as db:
    categories = db.query(ObjectionCategory).filter(
        ObjectionCategory.is_active == True
    ).all()
    
    for category in categories:
        print(f"{category.id}: {category.category_text} - {category.description}")
```

### Transcription
```python
from app.routes.v1.transcription import CallType
```

### API Versioning
```python
from app.core.versioning import APIVersion
```

---

## Notes

1. **Computed Enums**: Some enums are computed from other values:
   - `CallOutcomeCategory` - computed from `QualificationStatus` + `BookingStatus`
   - `OutcomeDecision` - computed from `overall_outcome_score` + `has_critical_error`

2. **Metadata Classes**: Most enums have separate metadata classes (not enums) that provide additional information:
   - `QualificationStatusMetadata`
   - `BookingStatusMetadata`
   - `AppointmentTypeMetadata`
   - `CallOutcomeCategoryMetadata`
   - `OutcomeDecisionMetadata`
   - `ActionTypeMetadata` (dataclass)
   - `MeetingPhaseMetadata` (dataclass)
   - `MissedOpportunityTypeMetadata` (dataclass)

3. **LLM Prompt Generation**: Most enums have functions to generate LLM prompt sections:
   - `generate_qualification_status_prompt()`
   - `generate_booking_status_prompt()`
   - `generate_appointment_type_prompt()`
   - `generate_outcome_decision_prompt()`
   - `generate_llm_prompt_action_types()`
   - `generate_meeting_phases_prompt()`
   - `generate_missed_opportunity_types_prompt()`

4. **Validation**: All enums have validation functions to check if a string value is valid for that enum.

5. **API Compatibility**: All enum values serialize to strings in JSON, ensuring backward compatibility with existing API clients.

---

**Document Maintained By**: Shunya Team (ottoai-rag)  
**Last Updated**: 2025-12-08  
**Next Review**: When new enums are added

