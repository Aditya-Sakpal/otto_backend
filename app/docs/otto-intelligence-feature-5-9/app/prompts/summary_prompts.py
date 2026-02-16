"""
Summary Extraction Prompts

Prompts for extracting and merging call summaries
"""

from typing import Dict, Any, Optional, List
from .base_prompts import (
    HOME_SERVICES_CONTEXT,
    PROPERTY_DETAILS_EXTRACTION,
    EXTRACTION_ACCURACY_GUIDELINES,
    JSON_OUTPUT_INSTRUCTION
)


def get_summary_extraction_prompt(
    chunk_text: str,
    call_context: Dict[str, Any],
    previous_summary: Optional[Dict[str, Any]] = None
) -> str:
    """Prompt for extracting summary from chunk"""
    
    context_str = f"""
**CALL CONTEXT:**
- Call ID: {call_context.get('call_id')}
- Company: {call_context.get('company_id')}
- Rep Role: {call_context.get('rep_role', 'customer_rep')}
- Call Type: {call_context.get('call_type_detection', {}).get('call_type', 'unknown')}
"""
    
    previous_str = ""
    if previous_summary:
        previous_str = f"""
**PREVIOUS SUMMARY (for context):**
{previous_summary.get('call_summary', 'No previous summary')}
"""
    
    return f"""Analyze this call transcript chunk and extract a summary.

{HOME_SERVICES_CONTEXT}
{PROPERTY_DETAILS_EXTRACTION}
{EXTRACTION_ACCURACY_GUIDELINES}

{context_str}
{previous_str}

**TRANSCRIPT CHUNK:**
{chunk_text}

**TASK:**
Extract a summary section with:
1. Brief narrative summary (2-3 sentences)
2. Key points discussed
3. Action items or next steps mentioned
4. Pending actions (things promised to be done)

**OUTPUT FORMAT (JSON):**
{{
  "call_summary": "Brief narrative of what happened in this chunk",
  "key_points": ["Point 1", "Point 2"],
  "action_items": [
    {{
      "action": "Description",
      "owner": "Who is responsible",
      "timeline": "When if mentioned",
      "confidence": 0.9
    }}
  ],
  "pending_actions": [
    {{
      "type": "send_proposal|schedule_appointment|follow_up|other",
      "owner": "Sales Rep|Customer|Other",
      "due_at": "Date/time if mentioned",
      "raw_text": "Exact quote from transcript",
      "confidence": 0.9,
      "contact_method": "email|phone|in_person|not_specified"
    }}
  ],
  "sentiment_score": <-1.0 to 1.0>,
  "topics_discussed": ["topic1", "topic2"]
}}

**IMPORTANT:**
- Be accurate - only extract what is actually said
- Use exact quotes for raw_text fields
- Don't hallucinate information
- If information isn't mentioned, use null or empty values

{JSON_OUTPUT_INSTRUCTION}"""


def get_summary_merge_prompt(
    chunk_summaries: List[Dict[str, Any]],
    call_metadata: Dict[str, Any]
) -> str:
    """Prompt for merging chunk summaries into final summary"""
    
    chunks_str = "\n\n".join([
        f"**CHUNK {i+1}:**\n{chunk.get('call_summary', '')}"
        for i, chunk in enumerate(chunk_summaries)
    ])
    
    key_points_str = "\n".join([
        f"- {point}"
        for chunk in chunk_summaries
        for point in chunk.get('key_points', [])
    ])
    
    return f"""Merge these chunk summaries into a cohesive final summary.

**CALL METADATA:**
- Call ID: {call_metadata.get('call_id')}
- Duration: {call_metadata.get('duration')} seconds
- Call Type: {call_metadata.get('call_type', 'unknown')}

**CHUNK SUMMARIES:**
{chunks_str}

**KEY POINTS FROM ALL CHUNKS:**
{key_points_str}

**TASK:**
Create a unified, coherent summary that:
1. Tells the story of the call from start to finish
2. Highlights the most important information
3. Removes redundancy
4. Maintains chronological flow
5. Captures the outcome

**OUTPUT FORMAT (JSON):**
{{
  "final_summary": "2-4 sentence narrative of the entire call",
  "key_highlights": [
    "Most important point 1",
    "Most important point 2",
    "Most important point 3"
  ],
  "call_flow": [
    {{
      "phase": "opening|discovery|presentation|handling|closing",
      "summary": "What happened in this phase"
    }}
  ],
  "outcome": "Clear statement of call result",
  "next_steps": "What happens next"
}}

**GUIDELINES:**
- Remove duplicate information
- Keep the most specific/detailed version of facts
- Maintain accuracy - don't add information not in chunks
- Create a coherent narrative, not just a list

{JSON_OUTPUT_INSTRUCTION}"""


__all__ = [
    'get_summary_extraction_prompt',
    'get_summary_merge_prompt',
]

