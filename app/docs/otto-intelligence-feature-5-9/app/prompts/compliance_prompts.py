"""
Compliance Extraction Prompts

Prompts for extracting SOP compliance and rep performance
"""

from typing import Dict, Any, Optional, List
from .base_prompts import HOME_SERVICES_COMPLIANCE_CONTEXT, JSON_OUTPUT_INSTRUCTION


def get_compliance_extraction_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    sop_metrics: Optional[List[Dict[str, Any]]] = None
) -> str:
    """Prompt for extracting compliance/SOP adherence"""
    
    target_role = call_context.get("rep_role", "customer_rep")
    
    sop_context = ""
    if sop_metrics:
        sop_context = f"""
**SOP METRICS TO EVALUATE:**
{chr(10).join(f"- {m.get('metric_name')}: {m.get('description')}" for m in sop_metrics[:10])}
"""
    else:
        sop_context = """
**GENERIC SOP STAGES (No custom SOP provided):**
- Greeting & Introduction
- Needs Assessment
- Information Gathering
- Solution Presentation
- Objection Handling (if applicable)
- Next Steps / Closing
"""
    
    return f"""Analyze this call chunk for SOP compliance and rep performance.

{HOME_SERVICES_COMPLIANCE_CONTEXT}

**CALL CONTEXT:**
- Target Role: {target_role}
- Call Type: {call_context.get('call_type_detection', {}).get('call_type', 'unknown')}

{sop_context}

**TRANSCRIPT CHUNK:**
{chunk_text}

**TASK:**
Evaluate the representative's performance against the SOP.

**OUTPUT FORMAT (JSON):**
{{
  "sop_compliance": {{
    "score": <0.0-1.0>,
    "stages_followed": ["Stage names that were executed well"],
    "stages_missed": ["Stage names that were skipped or done poorly"],
    "issues": [
      {{
        "stage": "Stage name",
        "issue": "Description of what went wrong",
        "severity": "critical|high|medium|low",
        "timestamp": "Approximate timestamp if identifiable"
      }}
    ],
    "positive_behaviors": [
      {{
        "behavior": "Specific action taken",
        "why_good": "Why this was effective",
        "example": "Quote from transcript"
      }}
    ]
  }},
  "professionalism_score": <0.0-1.0>,
  "notes": "Additional observations"
}}

**IMPORTANT:**
- Be specific - reference actual behaviors from the transcript
- Don't penalize for things not applicable (e.g., objection handling when there are no objections)
- Consider the call type (follow-up calls don't need full qualification)

{JSON_OUTPUT_INSTRUCTION}"""


__all__ = [
    'get_compliance_extraction_prompt',
]

