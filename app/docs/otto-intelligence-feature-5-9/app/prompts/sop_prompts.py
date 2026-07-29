"""
SOP and Summary Merge Prompts

Prompts for SOP ingestion, validation, evaluation, and summary merging
"""

from typing import Dict, Any, Optional, List


def get_sop_validation_prompt(
    document_text: str,
    metadata: Dict[str, Any]
) -> str:
    """Prompt for validating SOP document structure and content"""
    
    return f"""Validate this Standard Operating Procedure (SOP) document.

**DOCUMENT METADATA:**
- Name: {metadata.get('sop_name', 'Unknown')}
- Target Role: {metadata.get('target_role', 'Unknown')}
- Company: {metadata.get('company_id', 'Unknown')}

**DOCUMENT TEXT:**
{document_text[:5000]}  # First 5000 chars for validation

**TASK:**
Validate that this is a legitimate SOP document suitable for call evaluation.

**VALIDATION CRITERIA:**
1. Contains clear procedures or guidelines
2. Has identifiable stages or steps
3. Provides measurable standards
4. Relevant to call handling or customer interaction
5. Not just marketing material or generic info

**OUTPUT FORMAT (JSON):**
{{
  "is_valid": true|false,
  "confidence": <0.0-1.0>,
  "sop_type": "call_script|process_guide|general_sop|other",
  "validation_notes": [
    "Note about document structure",
    "Note about content quality"
  ],
  "identified_sections": [
    {{
      "section_name": "Section title",
      "start_page": <page number or null>,
      "content_type": "procedure|guideline|checklist|other"
    }}
  ],
  "recommendations": ["Suggestions for improving the SOP"],
  "issues_found": ["Any problems with the document"]
}}

Output ONLY valid JSON."""


def get_sop_metric_extraction_prompt(
    document_text: str,
    metadata: Dict[str, Any]
) -> str:
    """Prompt for extracting measurable metrics from SOP"""
    
    return f"""Extract measurable performance metrics from this SOP document.

**DOCUMENT METADATA:**
- Name: {metadata.get('sop_name', 'Unknown')}
- Target Role: {metadata.get('target_role', 'Unknown')}

**DOCUMENT TEXT:**
{document_text}

**TASK:**
Extract specific, measurable metrics that can be evaluated in a call recording.

**METRIC TYPES TO LOOK FOR:**
1. **Binary Checks**: Did the rep do X? (yes/no)
   - Example: "Greet with company name"
   
2. **Staged Procedures**: Steps that should be followed in order
   - Example: "1. Greeting, 2. Needs assessment, 3. Solution presentation"
   
3. **Required Behaviors**: Specific actions that must occur
   - Example: "Ask for permission to ask questions"
   
4. **Quality Standards**: Expectations for how something should be done
   - Example: "Use positive, professional language"

**OUTPUT FORMAT (JSON):**
{{
  "extracted_metrics": [
    {{
      "metric_id": "unique_id",
      "metric_name": "Short name",
      "description": "What this metric measures",
      "evaluation_method": "binary|scoring|checklist",
      "category": "greeting|qualification|objection_handling|closing|other",
      "weight": <0.0-1.0>,
      "target_value": <expected value>,
      "evaluation_criteria": {{
        "required_elements": ["Element 1", "Element 2"],
        "optional_elements": ["Optional element"],
        "quality_indicators": ["What makes this excellent"]
      }},
      "example_good": "Example of meeting this metric",
      "example_bad": "Example of failing this metric"
    }}
  ],
  "sop_stages": [
    {{
      "stage_name": "Stage name",
      "stage_order": <sequence number>,
      "description": "What happens in this stage",
      "required": true|false,
      "metrics_in_stage": ["List of metric_ids"]
    }}
  ],
  "overall_structure": "Description of how metrics relate to each other"
}}

**IMPORTANT:**
- Extract only measurable, observable behaviors
- Be specific enough that an AI can evaluate from transcript
- Focus on what can be detected in a call recording

Output ONLY valid JSON."""


def get_sop_evaluation_prompt(
    sop_metrics: List[Dict[str, Any]],
    transcript_chunk: str,
    rep_role: str
) -> str:
    """Prompt for evaluating call against SOP metrics"""
    
    metrics_str = "\n".join([
        f"- {m['metric_name']}: {m['description']}"
        for m in sop_metrics[:15]  # Limit to avoid token overflow
    ])
    
    return f"""Evaluate this call transcript against the provided SOP metrics.

**TARGET ROLE:** {rep_role}

**SOP METRICS:**
{metrics_str}

**TRANSCRIPT:**
{transcript_chunk}

**TASK:**
Evaluate how well the representative followed the SOP.

**OUTPUT FORMAT (JSON):**
{{
  "metrics_evaluation": [
    {{
      "metric_id": "metric_id from SOP",
      "metric_name": "Metric name",
      "score": <0.0-1.0>,
      "met": true|false,
      "evidence": "Quote from transcript showing this",
      "notes": "Additional context"
    }}
  ],
  "overall_compliance_score": <0.0-1.0>,
  "stages_completed": ["Stage names"],
  "stages_missed": ["Stage names"],
  "notable_deviations": [
    {{
      "deviation": "What was missed or done incorrectly",
      "impact": "critical|high|medium|low",
      "recommendation": "How to improve"
    }}
  ]
}}

Output ONLY valid JSON."""


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

Output ONLY valid JSON."""


def get_role_detection_prompt(transcript: str) -> str:
    """Prompt for detecting representative role (CSR vs Sales Rep)"""
    
    return f"""Determine the role of the representative in this call.

**TRANSCRIPT:**
{transcript[:3000]}  # First 3000 chars should be enough

**ROLE DEFINITIONS:**

**customer_rep (CSR - Customer Service Representative):**
- Takes inbound phone calls
- Gathers information and qualifies leads
- Schedules appointments for sales reps
- Answers questions and provides information
- Does NOT do in-person meetings
- Focus: scheduling, information gathering, qualification

**sales_rep (Sales Representative):**
- Conducts in-person consultations/meetings
- Provides quotes and proposals
- Closes deals and takes payments
- Discusses detailed solutions
- May reference previous phone calls
- Focus: selling, closing, detailed product knowledge

**KEY INDICATORS:**

CSR Indicators:
- "I'd like to schedule someone to come out"
- "Let me get some information from you"
- "Our technician will call you"
- Phone-based interaction only
- Scheduling focus

Sales Rep Indicators:
- "I'm here at your property"
- "Let me take some measurements"
- "Here's what I recommend"
- In-person references
- Solution presentation
- Pricing discussion with authority

**TASK:**
Determine which role this representative has.

**OUTPUT FORMAT (JSON):**
{{
  "role": "customer_rep|sales_rep",
  "confidence": <0.0-1.0>,
  "reasoning": "Explanation of classification",
  "key_indicators": ["Phrase 1", "Phrase 2"]
}}

Output ONLY valid JSON."""


__all__ = [
    'get_sop_validation_prompt',
    'get_sop_metric_extraction_prompt',
    'get_sop_evaluation_prompt',
    'get_summary_merge_prompt',
    'get_role_detection_prompt',
]

