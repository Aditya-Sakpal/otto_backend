# DETAILED OLD vs NEW Analysis (GPT-5.2)

This report compares the OLD summaries vs NEW GPT-5.2 regenerated summaries.
It checks if the reported issues were fixed.

## Executive Summary

**Calls Analyzed:** 10
**Total Field Improvements:** 65
**Total Field Regressions:** 0

### ✅ Key Improvements

**Call 440:**
  - **customer_name**: Now has value: `Will McCulloch`
  - **address**: Now has value: `3161 East Athena Court in Gilbert`
  - **appointment_date**: Now has value: `2026-01-15T07:30:00`
  - **appointment_time**: Now has value: `any`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `1 items`

**Call 441:**
  - **customer_name**: Now has value: `Robert Kovil`
  - **address**: Now has value: `3553 North Ramada, Mesa, 85215`
  - **appointment_date**: Now has value: `2026-01-23T13:00:00`
  - **appointment_time**: Now has value: `afternoon`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `2 items`

**Call 442:**
  - **customer_name**: Now has value: `Sandy Balak`
  - **address**: Now has value: `22042 North Reis R.E.I.F. drive. 8-5-1-3-8 (Rancho El Dorado, Narcopa)`
  - **appointment_date**: Now has value: `2026-01-19T13:00:00`
  - **appointment_time**: Now has value: `afternoon`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `1 items`
  - **objections**: Now has value: `1 items`

**Call 443:**
  - **customer_name**: Now has value: `Jim`
  - **address**: Now has value: `None None None`
  - **booking_status**: Now has value: `not_booked`
  - **call_outcome**: Now has value: `qualified_but_unbooked`
  - **decision_makers**: Now has value: `1 items`

**Call 445:**
  - **customer_name**: Now has value: `Deshay Ramos`
  - **address**: Now has value: `159 East Pebble Trow, 85122`
  - **appointment_date**: Now has value: `2026-01-19T13:00:00`
  - **appointment_time**: Now has value: `afternoon`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `2 items`

**Call 446:**
  - **customer_name**: Now has value: `Les McCoy`
  - **address**: Now has value: `6933 West Linda Sulane Imperia 8538`
  - **booking_status**: Now has value: `not_booked`
  - **call_outcome**: Now has value: `qualified_but_unbooked`
  - **decision_makers**: Now has value: `1 items`

**Call 447:**
  - **address**: Now has value: `None None None`
  - **booking_status**: Now has value: `not_booked`
  - **call_outcome**: Now has value: `qualified_but_unbooked`
  - **decision_makers**: Now has value: `1 items`
  - **objections**: Now has value: `1 items`

**Call 449:**
  - **customer_name**: Now has value: `Don Etherton`
  - **address**: Now has value: `Wickhamberg`
  - **booking_status**: Now has value: `service_not_offered`
  - **call_outcome**: Now has value: `qualified_service_not_offered`
  - **decision_makers**: Now has value: `1 items`

**Call 450:**
  - **customer_name**: Now has value: `Julie Colkins`
  - **address**: Now has value: `3342 North Brighton, Mesa, Arizona, 85207`
  - **appointment_date**: Now has value: `2026-01-21T16:00:00`
  - **appointment_time**: Now has value: `evening`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `1 items`
  - **objections**: Now has value: `1 items`

**Call 451:**
  - **customer_name**: Now has value: `David`
  - **address**: Now has value: `15227 South 14th Avenue, Phoenix, Arizona 85045`
  - **appointment_date**: Now has value: `2026-01-20T10:00:00`
  - **appointment_time**: Now has value: `morning`
  - **booking_status**: Now has value: `booked`
  - **call_outcome**: Now has value: `qualified_and_booked`
  - **decision_makers**: Now has value: `1 items`
  - **objections**: Now has value: `1 items`

---

## Detailed Call-by-Call Analysis

### Call 440

#### 📋 Original Reported Issues:
- Appointment confirmed but only day identified (Thursday), not time
- Action item was not required

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Will McCulloch`
- **address**: Now has value: `3161 East Athena Court in Gilbert`
- **appointment_date**: Now has value: `2026-01-15T07:30:00`
- **appointment_time**: Now has value: `any`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Will McCulloch |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 3161 East Athena Court in Gilbert |
| appointment_date | ❌ Empty | 2026-01-15T07:30:00 |
| appointment_time | ❌ Empty | any |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 2 items | 2 items |

---

### Call 441

#### 📋 Original Reported Issues:
- Customer's last name transcribed incorrectly (Colkins vs Culkins C-U-L-K-I-N-S)
- Missed: mother-in-law homeowner and her contact info
- Missed: need to get her email ID at sales appointment

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Robert Kovil`
- **address**: Now has value: `3553 North Ramada, Mesa, 85215`
- **appointment_date**: Now has value: `2026-01-23T13:00:00`
- **appointment_time**: Now has value: `afternoon`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `2 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Robert Kovil |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 3553 North Ramada, Mesa, 85215 |
| appointment_date | ❌ Empty | 2026-01-23T13:00:00 |
| appointment_time | ❌ Empty | afternoon |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 2 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 1 items | 2 items |

---

### Call 442

#### 📋 Original Reported Issues:
- Address taken incorrectly (street + spelled version combined)
- Caller's location misidentified (Rancho El Dorado vs Maricopa)
- Missed: roof age (20-25 years)
- Missed: flat roof with a bit in the back
- Sandy's last name misspelled
- Missed: sales rep likes cats (rapport building detail)
- Action item: incorrectly stated to schedule when already scheduled
- Appointment date vague (Monday next week vs specific)
- Positive behaviors too general

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Sandy Balak`
- **address**: Now has value: `22042 North Reis R.E.I.F. drive. 8-5-1-3-8 (Rancho El Dorado, Narcopa)`
- **appointment_date**: Now has value: `2026-01-19T13:00:00`
- **appointment_time**: Now has value: `afternoon`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `1 items`
- **objections**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Sandy Balak |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 22042 North Reis R.E.I.F. drive. 8-5-1-3-8 (Rancho El Dorado, Narcopa) |
| appointment_date | ❌ Empty | 2026-01-19T13:00:00 |
| appointment_time | ❌ Empty | afternoon |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 1 items |
| action_items | 1 items | 2 items |

---

### Call 443

#### 📋 Original Reported Issues:
- Pending action was wrong
- Issue about vacation plans irrelevant for confirmation call
- Call classified as qualified/unbooked when already booked

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Jim`
- **address**: Now has value: `None None None`
- **booking_status**: Now has value: `not_booked`
- **call_outcome**: Now has value: `qualified_but_unbooked`
- **decision_makers**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Jim |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | None None None |
| appointment_date | ❌ Empty | ❌ Empty |
| appointment_time | ❌ Empty | ❌ Empty |
| booking_status | ❌ Empty | not_booked |
| call_outcome | ❌ Empty | qualified_but_unbooked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 1 items | 1 items |

---

### Call 445

#### 📋 Original Reported Issues:
- Should identify: no reported roof issues, just age assumption
- Homeowner misidentified (Deshay as homeowner, not agent; Ted as owner)
- Missed: tile roof, HOA neighborhood, no solar panels
- Deshay Ramos should be main contact, Ted's info needed later
- Deshay's email was shared but not identified
- Positive behaviors too general
- Urgency signal 'sooner the better' missed

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Deshay Ramos`
- **address**: Now has value: `159 East Pebble Trow, 85122`
- **appointment_date**: Now has value: `2026-01-19T13:00:00`
- **appointment_time**: Now has value: `afternoon`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `2 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Deshay Ramos |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 159 East Pebble Trow, 85122 |
| appointment_date | ❌ Empty | 2026-01-19T13:00:00 |
| appointment_time | ❌ Empty | afternoon |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 2 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 1 items | 2 items |

---

### Call 446

#### 📋 Original Reported Issues:
- Postal code wrong (8538 vs 85382)
- Email missed
- Raven's expectations-setting missed as positive behavior
- Objection handling issue when none occurred
- Positive: 'offered alternative installation' incorrect
- 'Lien' misspelled as 'Lain' and later missed
- Action: clearing driveway missed
- Call outcome still unbooked

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Les McCoy`
- **address**: Now has value: `6933 West Linda Sulane Imperia 8538`
- **booking_status**: Now has value: `not_booked`
- **call_outcome**: Now has value: `qualified_but_unbooked`
- **decision_makers**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Les McCoy |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 6933 West Linda Sulane Imperia 8538 |
| appointment_date | ❌ Empty | ❌ Empty |
| appointment_time | ❌ Empty | ❌ Empty |
| booking_status | ❌ Empty | not_booked |
| call_outcome | ❌ Empty | qualified_but_unbooked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 1 items | 2 items |

---

### Call 447

#### 📋 Original Reported Issues:
- Objection initially correct, then missed after feedback
- Issue: 'did not set expectations' when no appointment
- Coaching should be actionable (explain why in-person required)

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **address**: Now has value: `None None None`
- **booking_status**: Now has value: `not_booked`
- **call_outcome**: Now has value: `qualified_but_unbooked`
- **decision_makers**: Now has value: `1 items`
- **objections**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | ❌ Empty |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | None None None |
| appointment_date | ❌ Empty | ❌ Empty |
| appointment_time | ❌ Empty | ❌ Empty |
| booking_status | ❌ Empty | not_booked |
| call_outcome | ❌ Empty | qualified_but_unbooked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 1 items |
| action_items | 1 items | 1 items |

---

### Call 449

#### 📋 Original Reported Issues:
- 'Piled roof' instead of 'tiled roof'
- Should be qualified but deprioritized

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Don Etherton`
- **address**: Now has value: `Wickhamberg`
- **booking_status**: Now has value: `service_not_offered`
- **call_outcome**: Now has value: `qualified_service_not_offered`
- **decision_makers**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Don Etherton |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | Wickhamberg |
| appointment_date | ❌ Empty | ❌ Empty |
| appointment_time | ❌ Empty | ❌ Empty |
| booking_status | ❌ Empty | service_not_offered |
| call_outcome | ❌ Empty | qualified_service_not_offered |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 0 items |
| action_items | 1 items | 1 items |

---

### Call 450

#### 📋 Original Reported Issues:
- Customer spelled last name but still wrong
- Email and phone missed
- Permission for email/text not captured
- Missed: no solar panels
- Gate code partial (#0 vs #0797)

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `Julie Colkins`
- **address**: Now has value: `3342 North Brighton, Mesa, Arizona, 85207`
- **appointment_date**: Now has value: `2026-01-21T16:00:00`
- **appointment_time**: Now has value: `evening`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `1 items`
- **objections**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | Julie Colkins |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 3342 North Brighton, Mesa, Arizona, 85207 |
| appointment_date | ❌ Empty | 2026-01-21T16:00:00 |
| appointment_time | ❌ Empty | evening |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 1 items |
| action_items | 1 items | 2 items |

---

### Call 451

#### 📋 Original Reported Issues:
- Email and phone to reach missed
- Permission for updates missed
- Roof type (shingle) missed

#### 🎯 IMPROVEMENTS (GPT-5.2):
- **customer_name**: Now has value: `David`
- **address**: Now has value: `15227 South 14th Avenue, Phoenix, Arizona 85045`
- **appointment_date**: Now has value: `2026-01-20T10:00:00`
- **appointment_time**: Now has value: `morning`
- **booking_status**: Now has value: `booked`
- **call_outcome**: Now has value: `qualified_and_booked`
- **decision_makers**: Now has value: `1 items`
- **objections**: Now has value: `1 items`

#### Key Fields Comparison:

| Field | OLD | NEW |
|-------|-----|-----|
| customer_name | ❌ Empty | David |
| customer_email | ❌ Empty | ❌ Empty |
| customer_phone | ❌ Empty | ❌ Empty |
| address | ❌ Empty | 15227 South 14th Avenue, Phoenix, Arizona 85045 |
| appointment_date | ❌ Empty | 2026-01-20T10:00:00 |
| appointment_time | ❌ Empty | morning |
| booking_status | ❌ Empty | booked |
| call_outcome | ❌ Empty | qualified_and_booked |
| decision_makers | 0 items | 1 items |
| roof_type | ❌ Empty | ❌ Empty |
| roof_age | ❌ Empty | ❌ Empty |
| objections | 0 items | 1 items |
| action_items | 1 items | 2 items |

---
