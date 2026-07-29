"""
Objection Extraction Prompts

All prompts related to objection detection, classification, and validation
"""

from typing import Dict, Any, Optional, List


def get_initial_objection_detection_prompt(
    chunk_text: str,
    call_context: Dict[str, Any]
) -> str:
    """Prompt for initial objection detection"""
    
    return f"""Identify potential objections from the CUSTOMER in this call chunk.

**WHAT IS AN OBJECTION:**
An objection is a concern, hesitation, or resistance expressed by the CUSTOMER that could prevent them from moving forward.

**WHAT IS NOT AN OBJECTION:**
- Questions asking for information
- The representative explaining something
- Neutral statements or acknowledgments
- Positive responses

**TRANSCRIPT CHUNK:**
{chunk_text}

**TASK:**
Identify potential objections expressed by the customer.

**OUTPUT FORMAT (JSON):**
{{
  "potential_objections": [
    {{
      "id": <sequential number>,
      "objection_text": "Exact quote from transcript",
      "speaker": "Identified speaker (must be customer)",
      "context": "Surrounding context",
      "timestamp": "Approximate timestamp if available",
      "confidence": <0.0-1.0>
    }}
  ]
}}

**IMPORTANT:**
- Only flag statements from the CUSTOMER
- Use exact quotes
- Include context to understand the objection
- Be conservative - when in doubt, flag it for later validation

Output ONLY valid JSON."""


def get_objection_classification_prompt(
    objection_text: str,
    context: str,
    objection_categories: List[Dict[str, Any]]
) -> str:
    """Prompt for classifying objections into categories"""
    
    categories_str = "\n".join([
        f"{cat['category_id']}. {cat['category_name']}: {cat.get('description', '')}"
        for cat in objection_categories
    ])
    
    return f"""Classify this objection into the most appropriate category.

**OBJECTION:**
"{objection_text}"

**CONTEXT:**
{context}

**AVAILABLE CATEGORIES:**
{categories_str}

**TASK:**
1. Determine the best matching category
2. Assess if this is truly an objection or just a question
3. Determine severity (how much resistance it represents)

**OUTPUT FORMAT (JSON):**
{{
  "category_id": <number from list>,
  "category_name": "Category name",
  "is_genuine_objection": true|false,
  "severity": "critical|high|medium|low",
  "reasoning": "Brief explanation of classification",
  "confidence": <0.0-1.0>
}}

**SEVERITY GUIDELINES:**
- **critical**: Strong resistance, deal-breaker ("I can't afford this", "Not interested")
- **high**: Significant concern ("That's too expensive", "I need to think about it")
- **medium**: Moderate concern ("How long will it take?", "What if it rains?")
- **low**: Minor question or clarification ("Do you offer financing?")

Output ONLY valid JSON."""


def get_speaker_validation_prompt(
    objections: List[Dict[str, Any]],
    transcript_chunk: str
) -> str:
    """Prompt for validating speaker attribution"""
    
    objections_str = "\n".join([
        f"ID {obj['id']}: \"{obj['objection_text']}\" (attributed to: {obj.get('speaker_id', 'unknown')})"
        for obj in objections
    ])
    
    return f"""Validate speaker attribution for these objections.

**OBJECTIONS:**
{objections_str}

**TRANSCRIPT:**
{transcript_chunk}

**TASK:**
For each objection, verify:
1. Who actually said it (customer or representative)
2. Is it genuinely an objection or just a statement/question
3. Is the attribution correct

**SPEAKER ROLES:**
- **customer**: The person calling about a service need (homeowner, tenant, property manager)
- **representative**: The company rep taking the call (CSR, sales rep)

**OUTPUT FORMAT (JSON):**
{{
  "validated_objections": [
    {{
      "id": <objection id>,
      "is_from_customer": true|false,
      "actual_speaker": "customer|representative",
      "is_genuine_objection": true|false,
      "correction_note": "Explanation if attribution was wrong",
      "confidence": <0.0-1.0>
    }}
  ]
}}

**COMMON ERRORS TO CATCH:**
- Rep explaining process mistaken for objection ("Let me tell you about...")
- Rep's empathy statement mistaken for objection ("I understand that's expensive")
- Customer's positive statement mistaken for objection ("That sounds good")

Output ONLY valid JSON."""


def get_objection_cross_validation_prompt(
    objections: List[Dict[str, Any]],
    transcript_chunk: str
) -> str:
    """Prompt for cross-validating objections to catch false positives"""
    
    objections_str = "\n".join([
        f"ID {obj['id']}: \"{obj['objection_text']}\" (Category: {obj.get('category_text', 'Unknown')})"
        for obj in objections
    ])
    
    return f"""Cross-validate these objections to identify false positives.

**OBJECTIONS TO VALIDATE:**
{objections_str}

**FULL TRANSCRIPT:**
{transcript_chunk}

**TASK:**
Review each objection in full context and determine:
1. Is this ACTUALLY an objection (resistance/concern from customer)?
2. Or is it a question, clarification, or neutral statement?
3. Was the objection overcome (did customer accept the response)?

**FALSE POSITIVE INDICATORS:**
- Rep speaking, not customer
- Customer asking neutral question
- Customer agreeing or showing interest
- Information gathering without resistance
- Positive or neutral sentiment

**OUTCOME INDICATORS:**
Objection was OVERCOME if:
- Customer accepts explanation
- Customer says "okay", "that makes sense", "I understand"
- Customer moves forward despite concern
- Concern is resolved through explanation

Objection NOT overcome if:
- Customer still expresses concern
- Customer wants to "think about it"
- Issue remains unresolved
- Customer becomes more resistant

**OUTPUT FORMAT (JSON):**
{{
  "final_objections": [
    {{
      "id": <objection id>,
      "is_valid_objection": true|false,
      "overcome": true|false|null,
      "false_positive_reason": "Explanation if not valid objection",
      "overcome_evidence": "Evidence showing it was overcome",
      "final_confidence": <0.0-1.0>
    }}
  ]
}}

Output ONLY valid JSON."""


def get_objection_response_suggestions_prompt(
    objection: Dict[str, Any],
    category: str
) -> str:
    """Prompt for generating objection response suggestions"""
    
    return f"""Generate response suggestions for this objection.

**OBJECTION:**
Category: {category}
Text: "{objection.get('objection_text', '')}"
Severity: {objection.get('severity', 'unknown')}

**TASK:**
Generate 2-3 effective response strategies for handling this objection.

**OUTPUT FORMAT (JSON):**
{{
  "response_suggestions": [
    "Response strategy 1",
    "Response strategy 2",
    "Response strategy 3"
  ]
}}

**GUIDELINES:**
- Responses should be specific to this objection
- Focus on addressing the underlying concern
- Be practical and actionable
- Use home services context

Output ONLY valid JSON."""


__all__ = [
    'get_initial_objection_detection_prompt',
    'get_objection_classification_prompt',
    'get_speaker_validation_prompt',
    'get_objection_cross_validation_prompt',
    'get_objection_response_suggestions_prompt',
]

