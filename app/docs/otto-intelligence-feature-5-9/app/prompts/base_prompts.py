"""
Base Prompts and Context

Shared context strings and base prompts used across multiple modules
"""

# =============================================================================
# HOME SERVICES CONTEXT
# =============================================================================

HOME_SERVICES_CONTEXT = """
**INDUSTRY CONTEXT: HOME SERVICES**
This is a call for a home services company (roofing, plumbing, electrical, HVAC, etc.)

Key terminology to understand:
- "Roof types": tile, shingle, metal, flat, TPO, EPDM
- "Job types": repair, replacement, inspection, maintenance, emergency
- "Urgency signals": leak, storm damage, HOA deadline, monsoon season, before summer/winter
- "Decision makers": homeowner, property manager, HOA board, spouse, parent
- "Property details": stories, square footage, HOA, gated, solar panels, age of system
"""

PROPERTY_DETAILS_EXTRACTION = """
**PROPERTY DETAILS TO CAPTURE:**
Extract these details if mentioned:
- Roof type (tile, shingle, metal, etc.)
- Roof age (years)
- Number of stories
- HOA status (yes/no, HOA name if mentioned)
- Gated community (yes/no)
- Solar panels (yes/no, number if mentioned)
- Pets (type, any special notes like "indoor cat")
- Property access notes (gate code, key location, etc.)
- Property size (square footage, number of bedrooms)
- Current issues or conditions
"""

DECISION_MAKER_CONTEXT = """
**DECISION MAKER IDENTIFICATION:**
The decision maker is the person who can authorize the work, not necessarily the caller.

Look for:
- "I'm the homeowner" → caller is decision maker
- "My mom owns the house" → mom is decision maker
- "I need to check with my wife" → spouse is also decision maker
- "The HOA needs to approve" → HOA board is decision maker
- Property manager mentioned → they may be decision maker

Capture:
- Decision maker name(s)
- Decision maker relationship to caller
- Decision maker contact info if provided
"""

URGENCY_EXTRACTION_CONTEXT = """
**URGENCY SIGNALS:**
Identify urgency indicators that affect timeline:
- Emergency: "leak", "water coming in", "emergency", "ASAP"
- Seasonal: "before monsoon", "before summer", "before winter", "before rainy season"
- Deadline: "HOA deadline", "insurance deadline", "selling house", "moving"
- Problem severity: "getting worse", "spreading", "can't wait"
- Comfort: "can't use room", "no heat", "no AC"

Rate urgency as: critical, high, medium, low
"""

HOME_SERVICES_COMPLIANCE_CONTEXT = """
**HOME SERVICES COMPLIANCE:**
For home services calls, compliance includes:
- Professional greeting with company name
- Asking permission to ask questions
- Gathering property details (address, type of property, issue description)
- Setting clear expectations for next steps
- Confirming contact information
- Explaining the appointment/inspection process
- Professional closing

Note: Objection handling may not apply if customer is simply inquiring or booking.
"""

# =============================================================================
# GENERAL EXTRACTION GUIDELINES
# =============================================================================

EXTRACTION_ACCURACY_GUIDELINES = """
**EXTRACTION ACCURACY REQUIREMENTS:**

1. **Use Exact Quotes**: When extracting text, use the exact words from the transcript
2. **Don't Hallucinate**: Only extract information that is explicitly stated
3. **Handle Spelling**: If something is spelled out letter-by-letter, use that spelling
4. **Capture Context**: Provide surrounding context for extracted information
5. **Confidence Scores**: Be honest about confidence levels
6. **Null vs Empty**: Use null for truly unknown, empty array [] for explicitly none
"""

SPEAKER_IDENTIFICATION_GUIDELINES = """
**SPEAKER IDENTIFICATION:**

- **customer**: Person calling for service (homeowner, tenant, property manager, caller)
- **representative**: Company employee (CSR, sales rep, dispatcher, service tech)
- **other**: Third party (translator, family member helping, etc.)

Pay attention to:
- Who is asking questions vs answering
- Who is providing information vs requesting
- Professional language (likely rep) vs casual (likely customer)
- References to company ("we", "our company") = rep
"""

JSON_OUTPUT_INSTRUCTION = """
**OUTPUT REQUIREMENTS:**
- Output ONLY valid JSON
- No additional text, explanations, or markdown
- No ```json``` code blocks
- Ensure all JSON is properly formatted and parseable
- Use null for missing values, not "null" as a string
"""

# =============================================================================
# COMMON RESPONSE FORMATS
# =============================================================================

CONFIDENCE_SCORE_GUIDANCE = """
**CONFIDENCE SCORE GUIDELINES:**
- 0.9-1.0: Explicitly stated, unambiguous
- 0.7-0.89: Clearly implied, strong evidence
- 0.5-0.69: Inferred from context, moderate evidence
- 0.3-0.49: Weak inference, uncertain
- 0.0-0.29: Guess, very uncertain
"""

__all__ = [
    'HOME_SERVICES_CONTEXT',
    'PROPERTY_DETAILS_EXTRACTION',
    'DECISION_MAKER_CONTEXT',
    'URGENCY_EXTRACTION_CONTEXT',
    'HOME_SERVICES_COMPLIANCE_CONTEXT',
    'EXTRACTION_ACCURACY_GUIDELINES',
    'SPEAKER_IDENTIFICATION_GUIDELINES',
    'JSON_OUTPUT_INSTRUCTION',
    'CONFIDENCE_SCORE_GUIDANCE',
]

