# Otto Intelligence - Comprehensive Call Analysis Report

## Executive Summary

This document provides a detailed analysis of 12 call IDs (440-451) comparing the actual transcripts against the generated summaries and expert feedback. The goal is to identify root causes of issues and propose improvements to make Otto the world's best sales rep/coach platform.

---

## Call-by-Call Analysis

### Call ID 440 - Appointment Confirmation Call

**Expert Feedback:**
- Appointment confirmed, but only the day (Thursday) was identified, not the time
- Action item was not required

**Transcript Evidence:**
- Rep offers: "I have a 7.30 to a 9, a 10 a.m. to a 12, 1 p.m. to 3 p.m. or a 4 p.m."
- Customer: "Okay. Sounds good. I'll get you added in here for that."
- Rep confirms: "We will see you this Thursday"

**Summary Output:**
- `appointment_date`: "2026-01-21T07:30:00" (picked first option without confirmation)
- `appointment_time_confidence`: 1.0 (incorrectly high)
- `pending_actions`: Contains "schedule_appointment" when already scheduled

**Root Cause Analysis:**
1. **Time Extraction Logic Flaw**: The system picked the first time slot mentioned (7:30) without verifying customer selection
2. **Action Item Hallucination**: Generated action items for already-completed tasks
3. **Missing Explicit Confirmation Detection**: Customer said "Sounds good" but didn't explicitly select a time slot

**Issue Categories:**
- ❌ Extraction Logic Error (time slot selection)
- ❌ Action Item Hallucination
- ❌ Context Understanding Gap

---

### Call ID 441 - Roof Repair Scheduling

**Expert Feedback:**
- Customer's last name was transcribed incorrectly despite being spelled out
- Key details missed: mother-in-law is the homeowner (and her contact info)
- Need to get her email ID at the sales appointment was missed

**Transcript Evidence:**
- Customer spells: "My last name is Kovil, D-O-L. D is in Victor, I-L-L-E" → Should be "Doville" or similar
- Customer says: "my mother-in-law owns a home" (critical ownership detail)
- Mother-in-law's name: "Marilyn Warwick" with phone "602-818-4957"
- Rep says: "We can get that from you at the appointment" (re: mother-in-law's email)

**Summary Output:**
- `customer_name`: "Robert Kovil" (incorrect transcription)
- `decision_makers`: ["Robert Kovil", "Marilyn Warwick"] (correct identification)
- No mention of needing to get mother-in-law's email at appointment

**Root Cause Analysis:**
1. **Transcription Error**: The ASR system misheard the spelled-out name
2. **Ownership Relationship Captured**: Decision makers correctly identified
3. **Missing Follow-up Action**: The "get email at appointment" task wasn't captured

**Issue Categories:**
- ❌ Transcription/ASR Error (name spelling)
- ✅ Partial Success (decision makers identified)
- ❌ Action Item Extraction Gap (pending info collection)

---

### Call ID 442 - Roof Estimate Request

**Expert Feedback:**
- Address taken incorrectly (street and spelled-out version combined)
- Caller's location misidentified (Rancho El Dorado vs. Maricopa)
- Key details missed: roof age (20-25 years), flat roof with a bit in the back
- Sandy's last name was misspelled
- Playful comment about cats missed as rapport-building detail
- Action item incorrectly stated to schedule when already scheduled
- Sending text updates listed as pending when just a general query
- Appointment date vague ("Monday next week" vs specific Monday)
- Positive behaviors too general

**Transcript Evidence:**
- Address: "22042 North Reis R.E.I.F. drive. 8-5-1-3-8" → Customer confirms "That's in Rancho El Dorado"
- Customer says: "we're out in Narcopa" (Maricopa)
- Customer mentions: "A little bit of flat roof in the back there, too"
- Customer says: "the roof is old" (no specific age given in transcript)
- Last name spelled: "B. as in boy, A. T. T. O. C. K." → Should be "Battock"
- Cat exchange: Rep says "Make sure they like cats. I'm kidding" - Customer laughs
- Appointment: "Monday between 1 to 3" confirmed

**Summary Output:**
- `service_address_raw`: "22042 North Reis R.E.I.F. drive, Rancho El Dorado, Narcopa"
- `service_address_structured.state`: "Narcopa" (incorrect - should be Arizona)
- `customer_name`: "Sandy" (missing last name entirely in main field)
- `property_details.roof_type`: "tile" (missed flat roof in back)
- No mention of cat rapport-building moment
- `pending_actions`: Contains schedule_appointment and send_info (hallucinated)

**Root Cause Analysis:**
1. **Address Parsing Error**: Combined street name with spelled version
2. **Geographic Confusion**: "Narcopa" (Maricopa) misidentified as state
3. **Name Extraction Incomplete**: Last name "Battock" not captured correctly
4. **Property Details Incomplete**: Missed flat roof section
5. **Rapport Details Not Captured**: No mechanism for capturing personal connection moments
6. **Action Item Hallucination**: Generated pending actions for completed tasks

**Issue Categories:**
- ❌ Address Parsing Logic Error
- ❌ Geographic/Context Understanding
- ❌ Name Extraction Error
- ❌ Property Details Incomplete
- ❌ Missing Rapport Capture Feature
- ❌ Action Item Hallucination

---

### Call ID 443 - Installation Confirmation Call

**Expert Feedback:**
- Pending action was wrong
- Issue about not addressing vacation plans was irrelevant for a confirmation call
- Call classified as qualified and unbooked when it was already booked

**Transcript Evidence:**
- This is a follow-up call about an ALREADY BOOKED installation
- Rep: "were there any days within the next couple of weeks that won't work for starting the installation of your roof?"
- Customer mentions vacation but says: "we might just postpone it until after all this is completed"
- Rep: "I'll go ahead and update that for you"

**Summary Output:**
- `booking_status`: "not_booked" (INCORRECT - installation already booked)
- `call_outcome_category`: "qualified_but_unbooked" (INCORRECT)
- `compliance.issues`: ["Failed to schedule inspection/estimate", "Did not set expectations"]
- `summary.summary`: Incorrectly describes call flow

**Root Cause Analysis:**
1. **Call Type Misclassification**: System didn't recognize this as a confirmation/follow-up call
2. **Booking Status Logic Error**: Failed to detect existing booking context
3. **Irrelevant Compliance Issues**: Applied new-call SOP to confirmation call
4. **Context Blindness**: Didn't understand "installation" implies already sold/booked

**Issue Categories:**
- ❌ Call Type Detection Failure
- ❌ Booking Status Logic Error
- ❌ SOP Context Mismatch (wrong evaluation criteria)

---

### Call ID 444 - Analysis Failed

**Expert Feedback:** Analysis failed

**Root Cause:** Call data not found in MongoDB (likely not processed or processing failed)

---

### Call ID 445 - Agent Scheduling Inspection

**Expert Feedback:**
- Summary should identify no reported roof issues but assumption of age-related problems
- Homeowner misidentified (Deshay as homeowner, not agent; Ted as owner)
- Missed details: tile roof, HOA neighborhood, no solar panels
- Deshay Ramos should be identified as main point of contact
- Ted's information should be noted as eventually required
- Deshay's email was shared and should have been identified
- Positive behaviors were general
- Urgency signal "sooner the better" was missed

**Transcript Evidence:**
- Deshay says: "I am the agent for the property"
- Property owner: "His name is Ted"
- Rep asks: "did you want me to make you the main point of contact?" - Deshay: "Sure"
- Email given: "D-E-S-H-A-Y dot H-O-M-E-S A-Z at gmail.com"
- Customer says: "Some of the better. I guess whatever is your source availability" (urgency)
- HOA: "Yes" confirmed
- Solar: "No" confirmed
- Roof type question asked but answer unclear in transcript

**Summary Output:**
- `customer_name`: "Deshay Ramos" (correct but role not clarified)
- `decision_makers`: ["Deshay Ramos"] (missing Ted as actual owner)
- `urgency_signals`: [] (MISSED "sooner the better")
- `property_details.hoa_status`: "yes" (correct)
- `property_details.has_solar`: false (correct)
- Summary incorrectly says "Deshay Ramos, called Arizona Roofers" implying homeowner

**Root Cause Analysis:**
1. **Role Distinction Failure**: Agent vs. Owner not properly distinguished
2. **Decision Maker Logic Gap**: Should capture both agent (POC) and owner (decision maker)
3. **Urgency Signal Missed**: "sooner the better" not captured
4. **Email Extraction**: Email was captured but not highlighted as key detail

**Issue Categories:**
- ❌ Role/Relationship Extraction Error
- ❌ Decision Maker Logic Incomplete
- ❌ Urgency Signal Detection Gap
- ✅ Partial Success (HOA, solar captured)

---

### Call ID 446 - Installation Follow-up Call

**Expert Feedback:**
- Postal code misidentified (8538 vs. 85382)
- Email missed
- Raven's good job setting expectations missed as positive behavior
- Lack of objection handling listed as issue when there were no objections
- Positive behavior "offered alternative installation" was incorrect
- "Lien" was misspelled as "Lain" and later completely missed
- Action item about clearing the driveway was missed
- Call outcome still unbooked

**Transcript Evidence:**
- Address: "6933 West Linda Sulane Imperia 8538" (likely 85382)
- Email confirmed: "L.A." (partial - full email not in transcript)
- Rep (Raven) gives detailed installation expectations
- Rep mentions: "make sure that your driveway is clear prior to their arrival" (ACTION ITEM)
- Rep mentions: "Titan Lain Services" regarding "pre-lean notice" (LIEN)
- Customer: "the sooner, the better" (urgency)
- No objections raised - customer very positive

**Summary Output:**
- `postal_code`: "8538" (missing digit - should be 85382)
- `booking_status`: "not_booked" (INCORRECT - this is post-sale follow-up)
- `compliance.issues`: ["Failed to handle objections properly"] (INCORRECT - no objections)
- `urgency_signals`: ["the sooner, the better"] (correctly captured)
- No mention of driveway clearing action item
- No mention of lien notice explanation

**Root Cause Analysis:**
1. **Postal Code Truncation**: ASR or extraction cut off last digit
2. **Call Type Misclassification**: Post-sale follow-up treated as pre-sale
3. **False Positive Compliance Issues**: Flagged non-existent objection handling failure
4. **Action Item Extraction Gap**: Missed "clear driveway" instruction
5. **Legal/Process Detail Missed**: Lien notice explanation not captured

**Issue Categories:**
- ❌ Data Extraction Error (postal code)
- ❌ Call Type Detection Failure
- ❌ False Positive Compliance Issues
- ❌ Action Item Extraction Gap
- ❌ Process Detail Extraction Gap

---

### Call ID 447 - Quote Request (No Appointment)

**Expert Feedback:**
- Objection initially identified correctly, then missed after feedback implementation
- "Did not set expectations for the appointment" listed as issue even though there was no appointment
- Coaching should be actionable (e.g., explaining why in-person estimates are required)

**Transcript Evidence:**
- Customer wants phone quote for 4,000 sq ft roof coating
- Rep explains: "I can't give you any quotes over the phone. The only way... would be to send a technician out"
- Customer declines: "That's okay. I'm sorry. I wasted your time"
- NO APPOINTMENT SCHEDULED

**Summary Output:**
- `booking_status`: "not_booked" (correct)
- `call_outcome_category`: "qualified_but_unbooked" (correct)
- `compliance.issues`: ["Did not set expectations for the appointment"] (INCORRECT - no appointment)
- `objections`: [] (MISSED the implicit objection about needing in-person visit)

**Root Cause Analysis:**
1. **Irrelevant Compliance Issue**: Applied appointment-related SOP to no-appointment call
2. **Objection Detection Gap**: Customer's reluctance to schedule is an objection
3. **Coaching Quality Gap**: No actionable coaching provided
4. **Context-Aware Evaluation Missing**: SOP evaluation not adapted to call outcome

**Issue Categories:**
- ❌ SOP Context Mismatch
- ❌ Objection Detection Gap
- ❌ Coaching Quality Gap

---

### Call ID 448 - Analysis Failed

**Expert Feedback:** Analysis failed

**Root Cause:** Call data not found in MongoDB

---

### Call ID 449 - Service Not Offered

**Expert Feedback:**
- "Piled roof" instead of "tiled roof"
- Should be identified as qualified but deprioritized

**Transcript Evidence:**
- Customer: "I need to have some piled roof pieces replaced" (ASR error - should be "tile")
- Rep explains job is too small for their company
- Rep recommends: "roofing handyman specialist"
- Rep mentions: "four to eight weeks to get work done" (their timeline)

**Summary Output:**
- `service_not_offered_reason`: "Don't offer that service" (partially correct)
- `qualification_status`: "warm" (should indicate deprioritized)
- `call_outcome_category`: "qualified_but_unbooked" (needs new category)
- Summary says "piled roof pieces" (ASR error propagated)

**Root Cause Analysis:**
1. **ASR Error Propagation**: "piled" instead of "tiled" carried through
2. **Missing Outcome Category**: No "service_not_offered" or "deprioritized" category
3. **Qualification Logic Gap**: Should distinguish between "unbooked by choice" vs "service mismatch"

**Issue Categories:**
- ❌ ASR/Transcription Error
- ❌ Missing Outcome Category
- ❌ Qualification Logic Gap

---

### Call ID 450 - Appointment Booking

**Expert Feedback:**
- Customer spelled out last name, yet it was wrong
- Email and phone number missed
- Permission for email/text updates not captured
- Missed "no solar panels"
- Gate access code was partially captured (#0 instead of #0797)

**Transcript Evidence:**
- Name: "Julie Colkins" - spelled "C-U-L-K-I-N-S" → Should be "Culkins"
- Email: "julie.n.colkins... C-U-L-K-I-N-S at comcast.net"
- Phone: "971-222-8840"
- Permission: Rep asks, customer says "Yes"
- Solar: "No" (confirmed)
- Gate code: "It's pound zero" (transcript shows partial)

**Summary Output:**
- `customer_name`: "Julie Colkins" (should be "Culkins" based on spelling)
- Email not in qualification output (should be captured)
- Phone not in qualification output (should be captured)
- `has_solar`: false (correct)
- `property_access_notes`: "Gate code 0" (incomplete - should be "#0" or full code)

**Root Cause Analysis:**
1. **Name Spelling Ignored**: Customer spelled it out but summary used phonetic version
2. **Contact Info Not Extracted**: Email and phone not in structured output
3. **Permission Not Captured**: Text/email permission not tracked
4. **Gate Code Incomplete**: Partial capture of access information

**Issue Categories:**
- ❌ Name Extraction Error (ignored spelling)
- ❌ Contact Info Extraction Gap
- ❌ Permission Tracking Gap
- ❌ Access Code Extraction Incomplete

---

### Call ID 451 - Balcony Sealant Request

**Expert Feedback:**
- Email and phone number to reach, and permission for updates, were missed
- Roof type (shingle) was missed

**Transcript Evidence:**
- Email: "D.R., the number two at usa dot com" → "dr2@usa.com"
- Phone: "eight four seven five two nine" (partial - missing area code)
- Permission: Rep asks, customer says "Yes"
- Roof type: Customer says "big singles, whatever... those big heavy shingles"
- Rep confirms: "shingle and flat"

**Summary Output:**
- `customer_name`: "David" (missing last name "Rosenberg")
- Email not in structured output
- Phone not in structured output
- `property_details.roof_type`: "shingle" (CORRECT!)

**Root Cause Analysis:**
1. **Contact Info Not Extracted**: Email and phone not captured in structured fields
2. **Permission Not Tracked**: Update permission not recorded
3. **Name Incomplete**: Last name "Rosenberg" (spelled out) not in main customer_name

**Issue Categories:**
- ❌ Contact Info Extraction Gap
- ❌ Permission Tracking Gap
- ✅ Roof Type Correctly Captured

---

## Issue Categorization Summary

### Category 1: Transcription/ASR Errors
- **Frequency**: 4 calls (441, 442, 449, 450)
- **Examples**: "Kovil" vs spelled "Doville", "piled" vs "tiled", "Colkins" vs "Culkins"
- **Impact**: High - cascades through entire analysis

### Category 2: Extraction Logic Errors
- **Frequency**: 8 calls
- **Sub-types**:
  - Name extraction ignoring spelled versions
  - Contact info (email, phone) not captured in structured fields
  - Partial data capture (gate codes, postal codes)
  - Time slot selection without confirmation

### Category 3: Call Type Misclassification
- **Frequency**: 3 calls (443, 446, 447)
- **Impact**: Causes wrong SOP evaluation, wrong booking status
- **Examples**: Confirmation calls treated as new calls, post-sale calls marked "unbooked"

### Category 4: Action Item Hallucination
- **Frequency**: 4 calls (440, 442, 443, 446)
- **Examples**: "Schedule appointment" when already scheduled, "Send info" as pending

### Category 5: Context Understanding Gaps
- **Frequency**: 6 calls
- **Sub-types**:
  - Role distinction (agent vs owner)
  - Geographic context (Maricopa as state)
  - Relationship context (mother-in-law as owner)

### Category 6: Missing Feature Gaps
- **Frequency**: Multiple calls
- **Missing features**:
  - Rapport-building moment capture
  - Permission tracking
  - Contact info structured extraction
  - Urgency signal detection improvements
  - Deprioritized/service-not-offered outcome category

### Category 7: SOP/Compliance Evaluation Errors
- **Frequency**: 4 calls
- **Examples**: 
  - "Failed to handle objections" when no objections existed
  - "Did not set appointment expectations" when no appointment
  - Generic positive behaviors

---

## Root Cause Mapping to Code Components

### 1. Transcription Layer (`app/services/transcription/`)
- ASR errors for spelled-out names
- Phonetic vs. spelled name resolution needed

### 2. Summary Extractor (`app/services/call_processing/extractors/summary_extractor.py`)
- Action item hallucination
- Missing contact info extraction
- Permission tracking not implemented

### 3. Qualification Extractor (`app/services/call_processing/extractors/qualification_extractor.py`)
- Name extraction logic needs spelling priority
- Address parsing errors
- Postal code truncation
- Role distinction (agent vs owner) logic
- Missing outcome categories

### 4. Compliance Extractor (`app/services/call_processing/extractors/compliance_extractor.py`)
- Call type detection needed before evaluation
- SOP criteria should adapt to call type
- False positive issue generation
- Generic positive behaviors

### 5. Home Services Context (`app/services/call_processing/extractors/home_services_context.py`)
- Geographic context improvements needed
- Role relationship definitions
- Urgency signal patterns

### 6. Self-Reflection Check (`summary_service_v2.py`)
- Not catching hallucinated action items
- Not validating booking status against call context

---

## Alignment with Sales Intelligence Bible

Based on the provided documents, the following principles should guide improvements:

### 1. "Every Detail Matters" Principle
- **Current Gap**: Missing contact info, partial gate codes, ignored spellings
- **Required**: Structured extraction for ALL contact details, access codes, permissions

### 2. "Context is King" Principle
- **Current Gap**: Call type misclassification, wrong SOP application
- **Required**: Call type detection layer before analysis

### 3. "Rapport Builds Trust" Principle
- **Current Gap**: Personal moments (cats, jokes) not captured
- **Required**: Rapport moment detection and capture

### 4. "Actionable Coaching" Principle
- **Current Gap**: Generic positive behaviors, irrelevant issues
- **Required**: Context-aware, specific, actionable feedback

### 5. "Accurate Intelligence" Principle
- **Current Gap**: Hallucinated actions, wrong booking status
- **Required**: Verification layer, cross-validation

---

## Recommended Improvements (Priority Order)

### P0 - Critical (Immediate)
1. **Call Type Detection Layer**: Classify calls before analysis (new, confirmation, follow-up, post-sale)
2. **Spelling Priority for Names**: When customer spells name, use that over phonetic
3. **Contact Info Structured Extraction**: Add email, phone, permission fields
4. **Action Item Validation**: Cross-check against call outcome before generating

### P1 - High Priority
5. **Booking Status Cross-Validation**: Verify against call context and keywords
6. **SOP Evaluation Adaptation**: Different criteria for different call types
7. **Role Distinction Logic**: Agent vs. Owner vs. POC classification
8. **Outcome Category Expansion**: Add "deprioritized", "service_not_offered"

### P2 - Medium Priority
9. **Address Parsing Improvements**: Better handling of spelled components
10. **Urgency Signal Enhancement**: Expand pattern matching
11. **Rapport Moment Capture**: New extraction category
12. **Compliance Issue Validation**: Prevent false positives

### P3 - Enhancement
13. **Geographic Context Database**: State/city validation
14. **Positive Behavior Specificity**: Quote actual phrases
15. **Coaching Actionability**: Specific recommendations with examples

---

## Next Steps

1. Review this analysis with stakeholders
2. Prioritize improvements based on business impact
3. Create detailed implementation specs for P0 items
4. Develop test cases from these 12 calls
5. Implement changes incrementally with A/B testing
6. Re-evaluate same calls after improvements

---

*Analysis completed: 2026-01-19*
*Calls analyzed: 10 of 12 (444, 448 failed)*

