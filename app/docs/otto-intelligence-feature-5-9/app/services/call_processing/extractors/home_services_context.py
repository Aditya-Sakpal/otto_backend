"""
Home Services Industry Context

Provides industry-specific context for call processing extractors.
This context helps the LLM understand the domain and extract relevant information.
"""

# Main industry context - used by all extractors
HOME_SERVICES_CONTEXT = """
**INDUSTRY CONTEXT: HOME SERVICES**
This is a call for a HOME SERVICES company (roofing, plumbing, electrical, HVAC, etc.).
Currently focused on ROOFING SERVICES: repairs, inspections, replacements, installations.

**CRITICAL PROPERTY DETAILS TO EXTRACT (when mentioned):**
- Roof type: tile, shingle, flat, metal, foam (from phrases like "tile roof", "flat roof", "shingle roof")
- Property stories: single story, two story (from "single story home", "one-story", "two story")
- HOA status: "in an HOA", "no HOA", "HOA neighborhood", "HOA community"
- Gated community: "gated", "not gated", "gate code needed", "gated community"
- Pets on property: dogs, cats (for technician safety - "pets inside", "indoor cats", "dog in backyard")
- Solar panels: "solar on the roof", "no solar", "has solar panels"
- Roof age: years mentioned (from "14 years old", "original roof", "20-25 years")
- Roof condition mentions: "leaks", "damage", "missing tiles", "cracked"

**INDUSTRY-SPECIFIC URGENCY SIGNALS (Arizona context):**
- Monsoon season: "before monsoon", "monsoon season", "monsoon damage", "before the rains"
- Insurance deadlines: "claim deadline", "insurance requires", "adjuster", "insurance claim"
- Inspection periods: "10-day inspection", "inspection period", "home inspection", "escrow"
- Storm damage: "after the storm", "storm damage", "hail damage", "wind damage"
- Active leaks: "active leak", "water coming in", "ceiling stains", "dripping"
- Emergency situations: "emergency", "urgent", "water pouring in"

**KEY INFORMATION FOR FIELD SALES REP:**
When extracting key_points, ALWAYS include details useful for the field technician/sales rep:
- Access instructions: gate codes, HOA rules, best entrance
- Pet warnings: type and location (so tech can be careful)
- Homeowner vs contact person: who to ask for, relationship
- Property quirks: steep roof, limited access, skylight, chimney
- Special instructions mentioned on call
- Best time to reach customer

**CUSTOMER RELATIONSHIPS:**
Pay attention to who is calling and who makes decisions:
- Homeowner: the actual property owner
- Property manager/agent: managing property for someone else (identify actual owner)
- Tenant/resident: lives there but doesn't own it
- Family member: calling on behalf of owner (identify the owner)

**COMMON SERVICE TYPES:**
- Roof replacement (full reroof) - HIGH ticket
- Roof repair (fix specific issues) - MEDIUM ticket  
- Roof inspection (assessment/estimate) - ENTRY point
- Emergency repair (urgent fixes) - PRIORITY
- Solar removal/reinstall (when doing roof work)
- Gutter services
"""

# Property details extraction prompt section
PROPERTY_DETAILS_EXTRACTION = """
**PROPERTY DETAILS TO EXTRACT (look for these specifically):**

Extract these property details if mentioned in the conversation:

1. **roof_type**: Look for mentions of roof material
   - "tile roof", "shingle", "flat roof", "metal roof", "foam roof"
   
2. **roof_age_years**: How old is the roof?
   - "14 years old", "original roof built in 2010", "about 20 years"
   - Calculate approximate age if build year given
   
3. **stories**: Number of stories
   - "single story", "one story", "two story", "ranch style"
   
4. **hoa_status**: HOA membership
   - "in an HOA", "no HOA", "HOA neighborhood", "deed restricted"
   
5. **gated_community**: Is it gated?
   - "gated", "not gated", "guard gate", "gate code"
   
6. **has_solar**: Solar panels present?
   - "solar panels", "no solar", "solar on roof"
   
7. **pets**: Any pets on property?
   - "indoor cat", "dog in backyard", "pets inside"
   - Include type and location if mentioned
   
8. **property_access_notes**: Special access information
   - Gate codes, best entrance, parking instructions
   - HOA rules about contractors
   
9. **roof_condition**: Current condition mentions
   - "leaking", "damaged", "missing tiles", "good condition"
   
10. **special_features**: Unique property features
    - Skylights, chimney, flat sections, multiple levels
"""

# Decision maker extraction guidance
DECISION_MAKER_CONTEXT = """
**DECISION MAKER IDENTIFICATION:**

Identify who can make the decision to proceed with service:

1. **Primary Decision Maker**: Who can authorize the work?
   - Usually the homeowner
   - Could be a spouse (need both to sign?)
   - Could be a property manager with authority
   
2. **Contact Person**: Who should the sales rep contact?
   - May be different from decision maker
   - E.g., "My mother owns the house but call me" - contact is caller, decision maker is mother
   - Real estate agent acting on behalf of owner
   
3. **Relationship Phrases to Watch:**
   - "My mother/father owns it" - decision maker is parent
   - "My mother-in-law's house" - decision maker is in-law
   - "I'm the property manager for..." - may have authority
   - "I'm calling for my neighbor" - decision maker is neighbor (get their info)
   - "My husband/wife and I" - both may need to be present
   
4. **Output Format:**
   - List ALL relevant people with their role
   - Note relationship to property
   - Indicate who needs to be present for decisions
"""

# Urgency context for extraction
URGENCY_EXTRACTION_CONTEXT = """
**URGENCY SIGNALS TO EXTRACT:**

Look for and extract these urgency indicators with CONTEXT:

1. **Time-Bound Urgency:**
   - "before monsoon season" → "Roof needs fixing before monsoon season (Arizona rainy season)"
   - "before we close on the house" → "Roof inspection needed before home sale closing"
   - "inspection period ends Friday" → "Urgent - real estate inspection deadline this Friday"
   
2. **Weather-Related:**
   - "expecting rain this week" → "Rain expected soon, needs immediate attention"
   - "storm damage" → "Recent storm caused damage, time-sensitive repair"
   
3. **Insurance-Related:**
   - "insurance claim" → "Active insurance claim - may have deadlines"
   - "adjuster coming" → "Insurance adjuster visit scheduled"
   
4. **Condition-Based:**
   - "active leak" → "URGENT: Active leak requiring immediate attention"
   - "water damage spreading" → "URGENT: Water damage getting worse"
   
5. **Life Events:**
   - "hosting family next week" → "Event-driven timeline - family visiting"
   - "putting house on market" → "Real estate timeline - listing soon"

**IMPORTANT**: Always include enough context so someone reading the urgency signal understands:
- WHAT needs to be done
- WHY it's urgent  
- WHEN it needs to happen
"""

# Compliance context for home services
HOME_SERVICES_COMPLIANCE_CONTEXT = """
**HOME SERVICES SALES PROCESS STAGES:**

Typical phone call flow for home services:

1. **GREETING & IDENTIFICATION**
   - Professional greeting with company name
   - Get caller's name
   - Verify contact information
   
2. **NEEDS DISCOVERY**
   - What's the issue? (leak, damage, age, preventive)
   - How long has it been an issue?
   - Has anyone looked at it?
   - Property details (roof type, age, stories)
   
3. **QUALIFYING**
   - Are they the homeowner/decision maker?
   - Timeline for getting work done
   - Have they gotten other quotes?
   - Budget/financing discussion
   
4. **SCHEDULING**
   - Availability for inspection/estimate
   - Property access (gate codes, pets, HOA)
   - Who needs to be present
   - Confirm address and contact
   
5. **SETTING EXPECTATIONS**
   - What happens during the appointment
   - How long it takes
   - What they'll receive (estimate, options)
   - Next steps after appointment
   
6. **CLOSE & CONFIRMATION**
   - Confirm appointment details
   - Send confirmation (text/email)
   - Provide contact info if questions

**NOTE FOR COMPLIANCE:**
- If call is a follow-up/existing customer service, do NOT penalize for missing stages
- If no objections occurred, do NOT mark "failed to handle objections" as an issue
"""


def get_home_services_context() -> str:
    """Get the full home services context for extraction prompts."""
    return HOME_SERVICES_CONTEXT


def get_property_details_context() -> str:
    """Get property details extraction context."""
    return PROPERTY_DETAILS_EXTRACTION


def get_decision_maker_context() -> str:
    """Get decision maker identification context."""
    return DECISION_MAKER_CONTEXT


def get_urgency_context() -> str:
    """Get urgency extraction context."""
    return URGENCY_EXTRACTION_CONTEXT


def get_compliance_context() -> str:
    """Get compliance evaluation context for home services."""
    return HOME_SERVICES_COMPLIANCE_CONTEXT


def build_full_extraction_context(include_property: bool = True, include_urgency: bool = True) -> str:
    """Build complete extraction context."""
    context = HOME_SERVICES_CONTEXT
    
    if include_property:
        context += "\n" + PROPERTY_DETAILS_EXTRACTION
    
    if include_urgency:
        context += "\n" + URGENCY_EXTRACTION_CONTEXT
    
    context += "\n" + DECISION_MAKER_CONTEXT
    
    return context

