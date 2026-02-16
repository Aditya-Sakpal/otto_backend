# Otto Intelligence - Improvement Plan for World-Class Sales Intelligence

## Vision Statement

Transform Otto into the world's best sales rep/coach platform by ensuring **every detail matters**, **context drives intelligence**, and **coaching is actionable**.

---

## Foundational Philosophy (from Sales Intelligence & Coaching Bible)

### The Core Hierarchy: Behavior → Strategy → Tactics → Language → Evaluation

The Bible establishes a non-negotiable hierarchy for elite selling:

1. **Behavioral Layer**: How to act in the moment (talk vs. listen, push vs. pull, pause vs. fill)
2. **Strategic Layer**: Which maneuver to apply (pullback, reframe, authority anchor)
3. **Tactical Layer**: How to execute the chosen maneuver step-by-step
4. **Linguistic Layer**: Exact wording, tone, and style calibrated to buyer persona
5. **Evaluation Layer**: Scoring on Frame Control, Pressure Direction, Trust Delta, Engagement, Context Fit

**Key Insight**: Most sales tools start with words/scripts. Elite sellers start with behavior. Otto must be designed the same way.

### The Three Brains (from Overview.pdf)

Otto should build three distinct intelligence capabilities:

1. **Elite Sales Rep Brain**
   - Knows when to ask questions vs. when to stop talking
   - Knows when to push vs. when to pull back
   - Knows when to do nothing (strategic patience)

2. **Elite Sales Coach Brain**
   - Explains WHY something worked or failed
   - Separates bad outcomes from bad decisions
   - Identifies pressure leaks, authority loss, trust erosion
   - Coaches judgment, not scripts

3. **Elite Sales Ops Brain**
   - Evaluates calls beyond close rate
   - Detects patterns across reps and teams
   - Learns which SOP deviations actually work
   - Improves the system without forcing conformity

### Real Failure Modes (Not Missing Script Lines)

The Bible identifies what actually causes lost deals:
- **Loss of authority** (frame control breakdown)
- **Excess pressure** (buyer feels cornered)
- **Broken trust** (promises not kept, dishonesty detected)
- **Context mismatch** (wrong strategy for the situation)

**Critical**: Otto should evaluate these dimensions, not just "did they follow the script?"

---

## Sales Process Alignment (from Bradley Crohurst Roofing Sales)

### The 10-Stage Home Services Sales Process

Otto's call evaluation should understand these distinct stages:

| Stage | Goal | Key Behaviors |
|-------|------|---------------|
| 1. Warm Entry & Rapport | Build connection | Ask openers, find connection points, accept hospitality |
| 2. Personal Credibility | Humanize yourself | Share "your why" story, demonstrate passion |
| 3. Company Story & Value | Differentiate | Veteran-owned, QC team, warranties |
| 4. Set Expectations | Get micro-yeses | "Does that sound good?" buy-in questions |
| 5. Inspection & Documentation | Create visual evidence | 80-100+ photos, "money shots" |
| 6. Pain Creation | Demonstrate problem | Show worst photos, use samples, empathy |
| 7. Product & Warranty | Present options | Three-tier approach, let them touch samples |
| 8. Financing | Uncover affordability | "Pregnant pause" technique, no pressure |
| 9. Close | Natural transition | Line-by-line scope review, payment options |
| 10. Post-Sale Handoff | Maintain trust | CompanyCam entry, thank you call |

### Psychology Principles to Detect and Score

From the Sales Manager document, elite reps use:
- **Mirroring**: Matching tone and topics of interest
- **Authority**: Sharing technical expertise and "why" story
- **Scarcity & Exclusivity**: Limited warranties/offers
- **Reciprocity**: Building goodwill through small gestures
- **Commitment & Consistency**: Micro-yeses building toward final yes
- **Visual Anchoring**: Photos and samples as tactile proof

---

## Phase 1: Critical Fixes (P0) - Week 1-2

### 1.1 Call Type Detection Layer

**Problem**: System treats all calls the same, causing wrong SOP evaluation and booking status.

**Affected Calls**: 443, 446, 447

**Solution**: Add a call type detection step BEFORE analysis.

**File**: `app/services/call_processing/call_type_detector.py`

**Implementation**:
```python
class CallTypeDetector:
    """
    Detect call type before running extractors.
    
    Types:
    - new_inquiry: First contact, scheduling inspection/estimate
    - confirmation: Confirming existing appointment
    - follow_up: Post-sale, installation scheduling
    - service_call: Existing customer with issue
    - quote_only: Customer just wants phone quote (no appointment)
    """
    
    CALL_TYPE_INDICATORS = {
        "follow_up": [
            "installation of your roof",
            "next steps for your project",
            "already been paid",
            "warranty documents",
            "job completion form"
        ],
        "confirmation": [
            "confirming your appointment",
            "just calling to confirm",
            "reminder about",
            "still on for"
        ],
        "quote_only": [
            "just need a quick quote",
            "how much do you charge",
            "can you give me a price"
        ]
    }
```

**Impact**: Prevents 30% of compliance false positives.

---

### 1.2 Spelling Priority for Names

**Problem**: When customers spell their name, the system ignores it and uses phonetic version.

**Affected Calls**: 441, 442, 450

**Solution**: Add spelling detection and priority in qualification extractor.

**File**: `app/services/call_processing/extractors/qualification_extractor.py`

**Implementation**:
```python
# Add to prompt:
"""
**NAME EXTRACTION - SPELLING PRIORITY:**

When a customer SPELLS their name letter by letter, USE THE SPELLED VERSION:
- "My last name is Culkins, C-U-L-K-I-N-S" → Use "Culkins" (not "Colkins")
- "Battock, B-A-T-T-O-C-K" → Use "Battock" (not "Balak")
- "Rosenberg, R-O-S-E-N-B-E-R-G" → Use "Rosenberg"

INDICATORS of spelling:
- "spelled", "that's", "as in" followed by letters
- Phonetic alphabet: "B as in boy", "D as in David"
- Letter sequences: "D-O-V-I-L-L-E"

ALWAYS prefer the spelled version over what you "hear".
"""
```

**Impact**: Fixes name accuracy from ~60% to ~95%.

---

### 1.3 Contact Info Structured Extraction

**Problem**: Email, phone, and permission not captured in structured fields.

**Affected Calls**: 450, 451, 445

**Solution**: Add dedicated contact info extraction to qualification extractor.

**File**: `app/services/call_processing/extractors/qualification_extractor.py`

**Schema Addition**:
```python
"contact_info": {
    "email": str | None,
    "email_confidence": float,
    "phone": str | None,
    "phone_confidence": float,
    "text_permission": bool | None,
    "email_permission": bool | None,
    "preferred_contact_method": str | None
}
```

**Prompt Addition**:
```
**CONTACT INFORMATION EXTRACTION:**

Extract ALL contact details mentioned:
- Email: Look for "@", "at gmail", "at yahoo", etc.
- Phone: Look for number sequences, "best number to reach you"
- Permission: "Can I send text updates?" → Yes/No response

IMPORTANT: Capture the EXACT email/phone as stated, including:
- Spelled out portions: "julie dot n dot culkins at comcast dot net"
- Number format: "971-222-8840" or "nine seven one two two two..."
```

---

### 1.4 Action Item Validation

**Problem**: System generates action items for already-completed tasks.

**Affected Calls**: 440, 442, 443

**Solution**: Cross-validate action items against call outcome.

**File**: `app/services/call_processing/extractors/summary_extractor.py`

**Implementation**:
```python
def _validate_action_items(self, actions: List[Dict], booking_status: str) -> List[Dict]:
    """Remove hallucinated action items."""
    
    # If appointment is booked, remove "schedule_appointment" actions
    if booking_status == "booked":
        actions = [a for a in actions if a["type"] != "schedule_appointment"]
    
    # If call is follow-up/post-sale, remove new-sale actions
    if self.call_type in ["follow_up", "confirmation"]:
        invalid_types = ["schedule_appointment", "send_quote", "send_estimate"]
        actions = [a for a in actions if a["type"] not in invalid_types]
    
    return actions
```

---

## Phase 2: High Priority (P1) - Week 3-4

### 2.1 Booking Status Cross-Validation

**Problem**: Calls marked "unbooked" when they're actually post-sale follow-ups.

**Affected Calls**: 443, 446

**Solution**: Use call type to inform booking status.

**Implementation**:
```python
def _cross_validate_booking_status(
    self, 
    extracted_status: str, 
    call_type: str,
    transcript_keywords: List[str]
) -> str:
    """Cross-validate booking status against call context."""
    
    # Post-sale calls are inherently "booked" (sale already made)
    if call_type == "follow_up":
        if any(kw in transcript_keywords for kw in [
            "installation", "warranty", "job completion", "project manager"
        ]):
            return "booked"  # Override to booked
    
    # Confirmation calls have existing booking
    if call_type == "confirmation":
        return "booked"
    
    return extracted_status
```

---

### 2.2 SOP Evaluation Adaptation

**Problem**: Same SOP criteria applied to all call types.

**Affected Calls**: 443, 447

**Solution**: Different evaluation criteria per call type.

**File**: `app/services/call_processing/extractors/compliance_extractor.py`

**Implementation**:
```python
SOP_BY_CALL_TYPE = {
    "new_inquiry": {
        "required_stages": [
            "GREETING & IDENTIFICATION",
            "NEEDS DISCOVERY", 
            "QUALIFYING",
            "SCHEDULING",
            "SETTING EXPECTATIONS",
            "CLOSE & CONFIRMATION"
        ],
        "evaluate_objection_handling": True
    },
    "follow_up": {
        "required_stages": [
            "GREETING & IDENTIFICATION",
            "CONFIRM DETAILS",
            "SET EXPECTATIONS",
            "CLOSE"
        ],
        "evaluate_objection_handling": False  # No objections expected
    },
    "confirmation": {
        "required_stages": [
            "GREETING & IDENTIFICATION",
            "CONFIRM APPOINTMENT",
            "CLOSE"
        ],
        "evaluate_objection_handling": False
    },
    "quote_only": {
        "required_stages": [
            "GREETING & IDENTIFICATION",
            "NEEDS DISCOVERY",
            "EXPLAIN PROCESS"  # Why in-person is needed
        ],
        "evaluate_objection_handling": True  # Customer may object to in-person
    }
}
```

---

### 2.3 Role Distinction Logic

**Problem**: Agent vs. Owner vs. POC not properly distinguished.

**Affected Calls**: 445

**Solution**: Enhanced decision maker extraction.

**Schema Update**:
```python
"decision_makers": [
    {
        "name": str,
        "role": "owner" | "agent" | "tenant" | "family_member" | "poc",
        "is_primary_contact": bool,
        "contact_info": {...}
    }
]
```

**Prompt Addition**:
```
**DECISION MAKER ROLES:**

Identify ALL people mentioned and their relationship:

1. **Owner**: The legal property owner
   - "I am the homeowner" → role: "owner"
   - "His name is Ted" (when asked who owns it) → role: "owner"

2. **Agent**: Real estate or property agent
   - "I am the agent for the property" → role: "agent"
   
3. **POC (Point of Contact)**: Primary contact but not owner
   - "Make me the main point of contact" → is_primary_contact: true
   
4. **Tenant**: Lives there but doesn't own
   - "I reside there" + "my mother-in-law owns" → role: "tenant"

IMPORTANT: If owner and POC are different people, capture BOTH.
```

---

### 2.4 Outcome Category Expansion

**Problem**: No category for "service not offered" or "deprioritized".

**Affected Calls**: 449

**Solution**: Add new outcome categories.

**Schema Update**:
```python
CALL_OUTCOME_CATEGORIES = [
    "qualified_and_booked",
    "qualified_but_unbooked",
    "not_qualified",
    "service_not_offered",      # NEW: Company doesn't do this work
    "deprioritized",            # NEW: Job too small, referred elsewhere
    "existing_customer_service", # NEW: Post-sale service call
    "information_only"          # NEW: Just answering questions
]
```

---

## Phase 3: Medium Priority (P2) - Week 5-6

### 3.1 Address Parsing Improvements

**Problem**: Street names combined with spelled versions, wrong geographic context.

**Affected Calls**: 442

**Solution**: Better address parsing logic.

```python
def _parse_address(self, raw_address: str) -> Dict:
    """Parse address with spelled component handling."""
    
    # Detect spelled components: "R.E.I.F." or "R-E-I-F"
    spelled_pattern = r'([A-Z][\.\-])+[A-Z]'
    
    # If spelled version follows street name, merge them
    # "22042 North Reis R.E.I.F. drive" → "22042 North Reif Drive"
    
    # Geographic validation
    ARIZONA_CITIES = ["Phoenix", "Mesa", "Gilbert", "Maricopa", "Casagrand", ...]
    
    # "Narcopa" → "Maricopa" (common mishearing)
    # "Rancho El Dorado" is a neighborhood IN Maricopa, not a city
```

---

### 3.2 Urgency Signal Enhancement

**Problem**: Urgency signals like "sooner the better" not captured.

**Affected Calls**: 445, 446

**Solution**: Expand urgency patterns.

```python
URGENCY_PATTERNS = {
    "high": [
        r"sooner.*better",
        r"as soon as possible",
        r"asap",
        r"urgent",
        r"emergency",
        r"active leak"
    ],
    "medium": [
        r"before monsoon",
        r"before.*close",
        r"inspection period",
        r"insurance deadline"
    ],
    "low": [
        r"when.*available",
        r"no rush",
        r"whenever"
    ]
}
```

---

### 3.3 Rapport Moment Capture

**Problem**: Personal connection moments not captured for field rep.

**Affected Calls**: 442

**Solution**: New extraction category for rapport.

**Schema Addition**:
```python
"rapport_moments": [
    {
        "topic": str,  # "pets", "family", "hobbies", "shared_experience"
        "detail": str,  # "Customer has 3 indoor cats"
        "rep_response": str,  # "Rep joked about sending cat-friendly tech"
        "use_for_followup": bool
    }
]
```

**Prompt Addition**:
```
**RAPPORT BUILDING MOMENTS:**

Capture personal connection moments that field reps can use:
- Pet mentions: "I have three cats" → Great for small talk
- Hobbies/interests mentioned
- Family situations discussed
- Jokes or playful exchanges
- Shared experiences

These help field reps build trust during in-person visits.
```

---

### 3.4 Compliance Issue Validation

**Problem**: "Failed to handle objections" when no objections existed.

**Affected Calls**: 446, 449

**Solution**: Cross-validate compliance issues against objection count.

```python
def _validate_compliance_issues(
    self, 
    issues: List[str], 
    objection_count: int,
    call_type: str
) -> List[str]:
    """Remove invalid compliance issues."""
    
    validated = []
    for issue in issues:
        # Don't flag objection handling if no objections
        if "objection" in issue.lower() and objection_count == 0:
            continue
        
        # Don't flag appointment expectations if no appointment
        if "appointment" in issue.lower() and call_type == "quote_only":
            continue
            
        validated.append(issue)
    
    return validated
```

---

## Phase 4: Enhancements (P3) - Week 7-8

### 4.1 Elite Evaluation Metrics (from Sales Intelligence Bible)

**Problem**: Current evaluation is simplistic (compliance checklist, generic scores).

**Solution**: Implement the Bible's five-dimensional evaluation system.

**Schema Update**:
```python
"evaluation_scores": {
    "frame_control": {
        "score": 1-10,
        "evidence": str,  # "Rep maintained agenda despite buyer tangents"
        "breakdown": {
            "who_asked_questions": float,  # Rep should drive discovery
            "agenda_maintained": bool,
            "challenges_handled_confidently": bool
        }
    },
    "pressure_direction": {
        "score": -5 to +5,  # Negative = rep chasing, Positive = buyer chasing
        "evidence": str,
        "who_initiated_next_step": "rep" | "buyer",
        "closing_attempts_vs_resistance": int
    },
    "trust_delta": {
        "score": -5 to +5,  # Did trust increase or decrease?
        "evidence": str,
        "buyer_disclosure_progression": bool,  # Did they share more over time?
        "sentiment_trajectory": "improving" | "stable" | "declining"
    },
    "engagement_level": {
        "score": 1-10,
        "talk_ratio": float,  # Ideal: 40-60% buyer talk
        "response_quality": "detailed" | "brief" | "monosyllabic",
        "questions_from_buyer": int
    },
    "context_fit": {
        "score": 1-10,
        "strategy_matches_situation": bool,
        "objections_addressed_appropriately": bool,
        "call_type_handled_correctly": bool
    }
}
```

**Implementation Guidance**:
```
Frame Control Score Calculation:
- High (8-10): Rep guided conversation, asked majority of questions, handled challenges confidently
- Medium (5-7): Shared control, some tangents, recovered from challenges
- Low (1-4): Buyer dominated, rep was reactive, lost agenda

Pressure Direction Calculation:
- Positive: Buyer asked "what's next?", expressed eagerness, minimal objections
- Neutral: Rep asked for next step, buyer agreed without resistance
- Negative: Rep pushed repeatedly, buyer hesitant, multiple deferrals

Trust Delta Calculation:
- Positive: Buyer volunteered more info over time, agreed to next step, warm closing
- Neutral: No significant change in buyer openness
- Negative: Buyer became more guarded, repeated concerns, cold closing
```

---

### 4.2 Strategic Maneuvers Library (from Sales Intelligence Bible)

**Problem**: No systematic framework for coaching rep strategy choices.

**Solution**: Implement the Bible's maneuvers library for coaching.

**Core Maneuvers to Detect and Coach**:

```python
STRATEGIC_MANEUVERS = {
    "pullback_disqualify": {
        "intent": "Reduce pressure, flip dynamic so buyer chases value",
        "triggers": [
            "Strong skepticism from buyer",
            "Price fixation early",
            "Disengagement signals"
        ],
        "execution_sequence": ["Validate", "Authority Anchor", "Disqualify", "Silence"],
        "example_lines": [
            "I understand - and honestly, this might not be the right fit for you.",
            "If you're not 100% confident, I'd rather you not move forward.",
        ],
        "risks": "Buyer might agree to walk - accept it if genuine",
        "required_authority": "Moderate - need some credibility first"
    },
    
    "authority_anchor": {
        "intent": "Bolster rep credibility and trust",
        "triggers": [
            "Buyer questions competency",
            "Early in call",
            "After competitor mention"
        ],
        "execution_sequence": ["Lead-in", "Credibility statement", "Insight", "Evidence"],
        "example_lines": [
            "We've installed over 500 systems in homes like yours...",
            "In my 12 years doing this, I've seen...",
        ],
        "risks": "Can seem like bragging if overdone"
    },
    
    "curiosity_loop": {
        "intent": "Engage buyer through self-discovery questions",
        "triggers": [
            "Discovery phase",
            "Passive buyer",
            "Surface-level responses"
        ],
        "execution_sequence": ["Context Q", "Problem Q", "Implication Q", "Solution Q"],
        "example_lines": [
            "What happens if you don't fix this in the next six months?",
            "How does that impact your bottom line?",
        ]
    },
    
    "reframe_to_process": {
        "intent": "Shift difficult conversation to next steps",
        "triggers": [
            "Stuck on single issue",
            "Running out of time",
            "Cannot resolve objection immediately"
        ],
        "execution_sequence": ["Acknowledge", "Propose process", "Outline steps", "Gain agreement"],
        "example_lines": [
            "Let's do this: I'll send you a detailed proposal, and we'll review it Tuesday.",
            "The next step is usually to involve your partner - shall we schedule that?",
        ]
    },
    
    "reframe_to_risk": {
        "intent": "Position status quo as the enemy",
        "triggers": [
            "Buyer complacent",
            "No urgency",
            "Deal stalling"
        ],
        "execution_sequence": ["Identify risk", "Quantify", "Project future", "Present solution"],
        "example_lines": [
            "The risk I have to mention is that these leaks could lead to mold...",
            "Companies that waited experienced X negative outcomes...",
        ],
        "risks": "Must be credible - no FUD (fear, uncertainty, doubt)"
    },
    
    "price_anchoring": {
        "intent": "Manage price perception",
        "triggers": [
            "Early price question",
            "Sticker shock",
            "Budget objection"
        ],
        "execution_sequence": ["Anchor to problem cost", "Offer range with high anchor", "Scope control if needed"],
        "example_lines": [
            "You mentioned losing $5k/month to inefficiencies - that's $60k/year. Our $15k solution pays for itself...",
            "If budget is a concern, we could start with just the core module...",
        ]
    },
    
    "strategic_silence": {
        "intent": "Use silence to encourage buyer elaboration",
        "triggers": [
            "After difficult question",
            "After pullback",
            "During negotiation"
        ],
        "execution_sequence": ["Ask/state", "Wait 3-6 seconds", "Let buyer fill void"],
        "example_lines": ["[silence after: 'So what's holding you back?']"]
    },
    
    "labeling_mirroring": {
        "intent": "Show empathy, encourage elaboration",
        "triggers": [
            "Strong emotion detected",
            "Incomplete explanation",
            "Hidden objection suspected"
        ],
        "execution_sequence": ["Detect emotion/key phrase", "Label or mirror", "Wait"],
        "example_lines": [
            "It sounds like you're concerned about the implementation...",
            "A nightmare? [mirroring their word]",
        ]
    }
}
```

**Coaching Output Integration**:
```python
"maneuver_coaching": {
    "recommended_maneuver": "pullback_disqualify",
    "why": "Buyer showing strong skepticism but hasn't given real objection",
    "example_execution": "You could try: 'I understand. To be honest, this may not be right for you, and that's okay.'",
    "what_rep_did": "Kept pushing benefits despite resistance",
    "impact": "Increased buyer defensiveness, pressure direction worsened"
}
```

---

### 4.3 Signal Detection Enhancement (from Sales Intelligence Bible)

**Problem**: Current system extracts facts but misses behavioral signals.

**Solution**: Add comprehensive signal detection per the Bible's taxonomy.

**Signal Categories to Detect**:

```python
SIGNAL_CATEGORIES = {
    "buyer_intent_urgency": {
        "high": ["need this solved by", "urgent", "ASAP", "emergency"],
        "medium": ["looking to", "planning to", "want to"],
        "low": ["just gathering info", "exploring options", "no rush"]
    },
    
    "emotional_state": {
        "positive": ["excited", "love this", "great", "perfect"],
        "negative": ["frustrated", "concerned", "worried", "hate"],
        "neutral": ["okay", "sure", "fine"]
    },
    
    "trust_skepticism": {
        "high_trust": ["I trust you", "you're right", "makes sense", "volunteering info"],
        "skepticism": ["not sure I believe", "sounds too good", "how do I know"]
    },
    
    "engagement_level": {
        "high": ["asking follow-up questions", "elaborating unprompted"],
        "low": ["monosyllabic answers", "yeah", "uh-huh", "I guess"]
    },
    
    "buying_signals": {
        "positive": ["when can you start", "what's next", "how do we proceed"],
        "negative": ["I need to think", "call me later", "not right now"]
    },
    
    "power_dynamics": {
        "buyer_dominant": ["I only have 5 minutes", "just tell me the price", interrupting],
        "rep_dominant": ["setting agenda", "asking questions", "guiding flow"]
    },
    
    "hidden_objection_indicators": {
        "patterns": ["keeps delaying without reason", "vague 'need to think'", "repeated minor issues"]
    }
}
```

**Signal-to-Maneuver Mapping**:
```python
SIGNAL_MANEUVER_MAP = {
    ("emotional_state", "negative"): ["labeling_mirroring", "de_escalation"],
    ("trust_skepticism", "skepticism"): ["authority_anchor", "social_proof"],
    ("engagement_level", "low"): ["curiosity_loop", "provocative_question"],
    ("buying_signals", "negative"): ["pullback_disqualify", "reframe_to_process"],
    ("power_dynamics", "buyer_dominant"): ["reframe_to_process", "authority_anchor"]
}
```

---

### 4.4 Geographic Context Database

**Solution**: Add Arizona-specific geographic validation.

```python
ARIZONA_GEOGRAPHY = {
    "cities": ["Phoenix", "Mesa", "Gilbert", "Maricopa", "Casa Grande", ...],
    "neighborhoods": {
        "Maricopa": ["Rancho El Dorado", "Province", "Cobblestone Farms"],
        "Gilbert": ["Val Vista Lakes", "Power Ranch"],
        ...
    },
    "zip_codes": {
        "85138": {"city": "Maricopa", "neighborhoods": ["Rancho El Dorado"]},
        "85122": {"city": "Casa Grande"},
        ...
    }
}
```

---

### 4.2 Positive Behavior Specificity

**Problem**: Generic positive behaviors like "Professional greeting".

**Solution**: Quote actual phrases from transcript.

```python
# Instead of:
"positive_behaviors": ["Professional greeting"]

# Generate:
"positive_behaviors": [
    {
        "behavior": "Professional greeting with company name",
        "evidence": "Thank you for calling Arizona Roofers. My name is Eva.",
        "impact": "Sets professional tone and identifies company"
    }
]
```

---

### 4.3 Coaching Actionability

**Problem**: Coaching feedback not actionable.

**Solution**: Add specific recommendations with examples.

```python
"coaching_recommendations": [
    {
        "issue": "Customer declined in-person estimate",
        "recommendation": "Explain WHY in-person is required",
        "example_script": "I understand you'd like a phone quote. The reason we need to see the roof in person is that every roof is different - the pitch, access, existing damage, and materials all affect the price. Our free inspection ensures you get an accurate quote with no surprises.",
        "skill_category": "objection_handling"
    }
]
```

---

## Phase 5: Language Intelligence (P4) - Week 9-10

### 5.1 Language Anti-Patterns Detection (from Sales Intelligence Bible)

**Problem**: No detection of authority-undermining or trust-eroding language.

**Solution**: Implement the Bible's language quality system.

**Anti-Pattern Categories**:
```python
LANGUAGE_ANTI_PATTERNS = {
    "authority_undermining": {
        "patterns": [
            r"\bjust\b",  # "just checking in" sounds weak
            r"\bmaybe\b.*\bwe could\b",  # Excessive hedging
            r"\bhopefully\b",
            r"\bI think\b.*\bmaybe\b",
            r"\bsorry to bother\b",
            r"\bI'm not sure\b",
        ],
        "coaching": "Use confident language. Instead of 'I think maybe we could', say 'We can'."
    },
    
    "trust_eroding": {
        "patterns": [
            r"\btrust me\b",  # Paradoxically reduces trust
            r"\bhonestly\b",  # Implies you're not always honest
            r"\bto be honest\b",
        ],
        "coaching": "Never ask for trust - demonstrate it through actions and evidence."
    },
    
    "salesy_cliches": {
        "patterns": [
            r"\bchange your life\b",
            r"\bno brainer\b",
            r"\bonce in a lifetime\b",
        ],
        "coaching": "Avoid hyperbole. Use specific, credible claims backed by evidence."
    },
    
    "defensive_language": {
        "patterns": [
            r"\bactually,? that's not\b",
            r"\bno,? you're wrong\b",
        ],
        "coaching": "Reframe positively. Instead of 'That's not what I said', try 'Let me clarify what I meant'."
    },
    
    "competitor_bashing": {
        "patterns": [
            r"(competitor|they|them).*(terrible|awful|garbage|sucks)",
        ],
        "coaching": "Never badmouth competitors directly. Focus on your unique value instead."
    }
}
```

**Better Alternative Phrases**:
```python
LANGUAGE_IMPROVEMENTS = {
    "cheap": "cost-effective / affordable",
    "sign the contract": "authorize the agreement",
    "buy": "invest",
    "problem": "challenge / area for improvement",
    "contract": "agreement / paperwork",
    "customer": "client",
    "pitch": "discussion / presentation",
    "just checking in": "following up on [specific topic]",
    "does that make sense?": "how does that sound to you?"
}
```

---

### 5.2 Post-Call Coaching Report Structure (from Sales Intelligence Bible)

**Problem**: Current summaries are fact-focused, not coaching-focused.

**Solution**: Implement the Bible's comprehensive coaching report structure.

**Post-Call Report Schema**:
```python
"coaching_report": {
    "call_id": str,
    "duration_seconds": int,
    "outcome": str,
    
    "evaluation_scores": {
        "frame_control": {"score": int, "evidence": str},
        "pressure_direction": {"score": int, "evidence": str},
        "trust_delta": {"score": int, "evidence": str},
        "engagement_level": {"score": int, "evidence": str},
        "context_fit": {"score": int, "evidence": str}
    },
    
    "key_moments": [
        {
            "timestamp": str,
            "event_type": "opportunity" | "objection" | "buying_signal" | "misstep",
            "description": str,
            "what_rep_did": str,
            "feedback": str,
            "recommended_alternative": str | None
        }
    ],
    
    "strengths": [
        {
            "behavior": str,
            "evidence": str,  # Quote from transcript
            "why_effective": str
        }
    ],
    
    "areas_for_improvement": [
        {
            "behavior": str,
            "evidence": str,
            "recommended_approach": str,
            "example_script": str
        }
    ],
    
    "maneuver_analysis": {
        "maneuvers_used": [str],
        "maneuvers_missed": [str],
        "execution_quality": {
            "maneuver": str,
            "execution_score": int,
            "feedback": str
        }
    },
    
    "outcome_vs_decision_quality": {
        "outcome": "won" | "lost" | "progressed" | "stalled",
        "decision_quality": "excellent" | "good" | "fair" | "poor",
        "note": str  # e.g., "Good decision despite lost outcome - buyer had no budget"
    },
    
    "next_steps_for_rep": [str],
    "overall_summary": str
}
```

**Key Coaching Principle**: 
> A lost deal can still be a high-quality decision. A closed deal can still reveal bad habits. Evaluate decisions, not just outcomes.

---

### 5.3 Objection Handling Intelligence (from Sales Intelligence Bible)

**Problem**: No distinction between absorb vs. deflect objection strategies.

**Solution**: Implement objection classification and coaching.

**Objection Categories**:
```python
OBJECTION_TYPES = {
    "price": {
        "examples": ["too expensive", "over budget", "competitor is cheaper"],
        "recommended_approach": "price_anchoring",
        "absorb_vs_deflect": "Absorb if late stage, deflect if early"
    },
    "timing": {
        "examples": ["not now", "call me later", "need to think"],
        "recommended_approach": "pullback_disqualify or reframe_to_process",
        "absorb_vs_deflect": "Often deflect - may be smokescreen"
    },
    "authority": {
        "examples": ["need to ask spouse", "need boss approval", "committee decides"],
        "recommended_approach": "reframe_to_process (schedule joint meeting)",
        "absorb_vs_deflect": "Absorb - arrange meeting with decision maker"
    },
    "trust": {
        "examples": ["don't trust you", "had bad experience", "too good to be true"],
        "recommended_approach": "authority_anchor + social_proof",
        "absorb_vs_deflect": "Always absorb - critical to address"
    },
    "need": {
        "examples": ["don't need it", "happy with current", "not a priority"],
        "recommended_approach": "reframe_to_risk + curiosity_loop",
        "absorb_vs_deflect": "Absorb if genuine, deflect if brush-off"
    },
    "competitor": {
        "examples": ["using competitor X", "competitor offered more"],
        "recommended_approach": "differentiation + social_proof",
        "absorb_vs_deflect": "Absorb - differentiate without bashing"
    }
}
```

**Objection Coaching Output**:
```python
"objection_coaching": {
    "objection_detected": "I need to talk to my wife",
    "objection_type": "authority",
    "rep_response_strategy": "deflect",
    "rep_response_quality": "poor",
    "feedback": "You said 'okay, call me back' which loses momentum. Better: schedule a joint call.",
    "recommended_script": "Of course - decisions like this should be made together. Would it help if I joined a call with both of you? That way she can ask questions directly."
}
```

---

## Implementation Roadmap (Updated)

| Week | Phase | Focus | Key Deliverables |
|------|-------|-------|------------------|
| 1 | P0 | Call Type Detection | `call_type_detector.py` enhanced |
| 2 | P0 | Name & Contact Extraction | `qualification_extractor.py` updated |
| 3 | P1 | Booking Status & SOP | Cross-validation logic |
| 4 | P1 | Role Distinction | Decision maker schema |
| 5 | P2 | Address & Urgency | Parsing improvements |
| 6 | P2 | Rapport & Compliance | New extraction categories |
| 7 | P3 | Elite Evaluation Metrics | 5-dimensional scoring system |
| 8 | P3 | Strategic Maneuvers | Maneuver detection & coaching |
| 9 | P4 | Signal Detection | Behavioral signal taxonomy |
| 10 | P4 | Language Intelligence | Anti-patterns & coaching reports |
| 11 | P5 | Objection Intelligence | Classification & response coaching |
| 12 | P5 | Integration & Testing | Full system validation |

---

## Success Metrics

### Data Accuracy Metrics (Phase 1-2)
- Name extraction accuracy: 60% → 95%
- Contact info capture rate: 40% → 90%
- Booking status accuracy: 70% → 95%
- Action item accuracy: 60% → 90%

### Evaluation Quality Metrics (Phase 3-4)
- False positive compliance issues: 30% → 5%
- Hallucinated action items: 25% → 2%
- Missing key details: 40% → 10%
- Maneuver detection accuracy: N/A → 85%
- Signal detection accuracy: N/A → 80%

### Coaching Quality Metrics (Phase 5)
- Coaching actionability (rep feedback): N/A → 4.5/5 rating
- Decision vs. outcome separation: N/A → 90% accurate
- Language anti-pattern detection: N/A → 95%

### Business Impact Metrics
- Field rep preparation time: -30%
- Customer callback rate: -20% (better first-call info)
- Coaching effectiveness: +40% (actionable feedback)
- Rep win rate improvement: +15% (better strategy guidance)
- Rep ramp-up time: -25% (faster onboarding with coaching)

---

## Testing Strategy

### Regression Test Suite
Use the 12 analyzed calls (440-451) as golden test cases:
- Each call has documented expected vs. actual output
- Run after every change to ensure no regressions
- Add new test cases as issues are discovered

### Scenario-Based Testing (from Bible Examples)
Test maneuver recommendations against documented scenarios:
1. "I don't trust you" - Status Test vs True Fear
2. Price Shock ("Your price is way higher")
3. Competitor Comparison ("Why not go with X?")
4. "Call me later" Brush-off
5. Spouse/Partner Stall ("Need to ask my wife")
6. Commercial Procurement Skepticism
7. Angry Customer De-escalation
8. Upsell from Existing Job

### A/B Testing
- Deploy changes to 10% of calls initially
- Compare accuracy metrics against baseline
- Measure rep satisfaction with coaching quality
- Roll out to 100% after validation

### Feedback Loop Testing
- Track which suggestions reps follow
- Measure outcomes when suggestions followed vs. ignored
- Use reinforcement learning to improve recommendations

---

## Appendix A: Key Principles from Source Documents

### From Sales Intelligence & Coaching Bible

1. **Behavior First**: "Most sales tools reverse this. They start with words. Elite sellers start with behavior."

2. **Multiple Valid Strategies**: "There is never one 'correct' move—only better or worse fits for the frame, pressure, engagement, and context at hand."

3. **Outcome ≠ Correctness**: "A lost deal can still be a high-quality decision. A closed deal can still reveal bad habits."

4. **Context is King**: "An elite salesperson is defined by behavioral discipline, situational strategy, tactical execution, linguistic finesse, and constant learning."

5. **Top Performer Patterns**: 
   - Talk-to-listen ratio: 46:54 (not 60:40)
   - 54% more conversational switches than average reps
   - High curiosity scores (82% of top sellers)
   - 30% less gregarious than average (willing to challenge)

### From Bradley Crohurst Roofing Sales Process

1. **Permission to Sell**: "You're not selling — you're earning permission to sell later."

2. **Pain Creation**: "You're not telling them they need a new roof — you're helping them realize it themselves."

3. **Make It Their Decision**: "Tactile engagement leads to ownership."

4. **Micro-Yeses Build Final Yes**: "Use 'Does that sound good?' to get multiple small affirmations."

### From Overview Document

1. **Three Brains**: Build Rep Brain + Coach Brain + Ops Brain, not just one.

2. **Real Failure Modes**: Loss of authority, excess pressure, broken trust, context mismatch.

3. **Maneuvers Not Scripts**: "A maneuver is a strategic action triggered by context with known risks and tradeoffs."

---

## Appendix B: Common Scenarios & Recommended Maneuvers

| Scenario | Recommended Maneuver | Key Signal | Risk to Watch |
|----------|---------------------|------------|---------------|
| Buyer skepticism | Authority Anchor + Empathy | "I don't trust you" | Don't get defensive |
| Price shock | Price Anchoring + Scope Control | "That's more than I expected" | Don't discount immediately |
| Competitor comparison | Differentiation + Social Proof | "Competitor X is cheaper" | Don't badmouth competitor |
| Brush-off | Deflection with Hook | "Call me later" | Don't take at face value |
| Partner stall | Reframe to Process | "Need to ask spouse" | Schedule joint call |
| Complacent buyer | Reframe to Risk | "We're doing fine as is" | Don't use FUD |
| Angry customer | De-escalation | Raised voice, frustration | Don't get defensive |
| Hidden objection | Labeling + Pullback | Vague "need to think" | Surface the real issue |

---

## Conclusion

This comprehensive improvement plan transforms Otto from a fact-extraction tool into a **true sales intelligence platform** aligned with the principles of elite sales performance.

### Root Causes Addressed:

1. **Call Type Blindness** → Call type detection layer
2. **Spelling Ignorance** → Spelling priority logic
3. **Missing Contact Info** → Structured extraction
4. **Action Hallucination** → Cross-validation
5. **Wrong SOP Application** → Adaptive evaluation
6. **Role Confusion** → Enhanced decision maker logic
7. **Missing Outcomes** → Expanded categories
8. **Generic Feedback** → Specific, actionable coaching

### Bible-Aligned Enhancements:

9. **Single-Dimensional Scoring** → Five-dimensional elite evaluation (Frame, Pressure, Trust, Engagement, Context)
10. **Script-Based Thinking** → Maneuver-based strategic guidance
11. **Outcome-Only Evaluation** → Decision quality separation
12. **Generic Language** → Anti-pattern detection and improvement suggestions
13. **Signal Blindness** → Comprehensive behavioral signal taxonomy
14. **Reactive Coaching** → Proactive maneuver recommendations

### The Transformation:

By implementing these changes systematically, Otto becomes:

- **An Elite Sales Rep Brain**: Knowing when to push, when to pull back, when to stay silent
- **An Elite Sales Coach Brain**: Explaining why things work, separating decisions from outcomes
- **An Elite Sales Ops Brain**: Learning what actually drives performance, not just SOP compliance

This is how Otto becomes the **world's best sales rep/coach platform**.

---

*Plan created: 2026-01-19*
*Based on analysis of calls 440-451*
*Aligned with Sales Intelligence & Coaching Bible principles*
*Incorporates Bradley Crohurst Roofing Sales Process*
*Guided by GoMotto Overview Philosophy*

