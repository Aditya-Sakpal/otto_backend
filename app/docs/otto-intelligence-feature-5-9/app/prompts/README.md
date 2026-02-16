# Centralized Prompts Package

**Version:** 1.0.0  
**Last Updated:** January 16, 2026

## Overview

This package contains all LLM prompt templates used in the Otto Intelligence system. Centralizing prompts provides:

- ✅ **Single Source of Truth**: All prompts in one location
- ✅ **Easy Versioning**: Track prompt changes over time
- ✅ **A/B Testing**: Compare prompt variations easily
- ✅ **Consistency**: Ensure uniform prompt quality
- ✅ **Maintainability**: Update prompts without touching service code

---

## Structure

```
app/prompts/
├── __init__.py                  # Main exports
├── base_prompts.py              # Shared context and guidelines
├── diarization_prompts.py       # Speaker identification
├── call_type_prompts.py         # Call type detection
├── summary_prompts.py           # Summary extraction and merging
├── compliance_prompts.py        # SOP compliance evaluation
├── qualification_prompts.py     # BANT, appointments, customer info
├── objection_prompts.py         # Objection detection and validation
├── sop_prompts.py               # SOP ingestion and evaluation
└── README.md                    # This file
```

---

## LLM Calls Per API Request

### Call Processing API (`/api/v1/call-processing/process`)

**Total: ~33 LLM calls** (for 4-chunk call, varies with audio length)

| Service | LLM Calls | Notes |
|---------|-----------|-------|
| Diarization | 3 | identify_speakers, label_speakers, verify_diarization |
| Call Type Detection | 1 | detect_call_type |
| Summary Extraction | 4 | 1 per chunk |
| Compliance Extraction | 4 | 1 per chunk |
| Objection Detection | 4 | initial_detection, classification, speaker_validation, cross_validation |
| Qualification Extraction | 16 | 4 methods × 4 chunks (core, appointment, intelligence, property) |
| Summary Merge | 1 | merge_chunk_summaries |

**Chunk Count by Call Duration:**
- 5 min call ≈ 3 chunks ≈ 26 LLM calls
- 10 min call ≈ 4 chunks ≈ 33 LLM calls
- 15 min call ≈ 5 chunks ≈ 40 LLM calls

### SOP Upload API (`/api/v1/sop/documents/upload`)

**Total: 2 LLM calls**

| Service | LLM Calls | Notes |
|---------|-----------|-------|
| SOP Validation | 1 | validate_sop |
| Metric Extraction | 1 | extract_metrics |

---

## Usage

### Import Prompts

```python
from app.prompts import (
    get_summary_extraction_prompt,
    get_compliance_extraction_prompt,
    HOME_SERVICES_CONTEXT,
    PROPERTY_DETAILS_EXTRACTION
)
```

### Use in Service

```python
# Example: Summary extraction
prompt = get_summary_extraction_prompt(
    chunk_text=transcript_chunk,
    call_context={
        'call_id': 'call_123',
        'company_id': 'az_roofers',
        'rep_role': 'customer_rep',
        'call_type_detection': {'call_type': 'fresh_sales'}
    },
    previous_summary=None
)

response = await llm_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": "You are a call analysis expert."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.1
)
```

---

## Prompt Categories

### 1. Base Prompts (`base_prompts.py`)

**Shared Context Strings:**
- `HOME_SERVICES_CONTEXT` - Industry terminology and concepts
- `PROPERTY_DETAILS_EXTRACTION` - Property detail requirements
- `DECISION_MAKER_CONTEXT` - Decision maker identification guide
- `URGENCY_EXTRACTION_CONTEXT` - Urgency signal identification
- `HOME_SERVICES_COMPLIANCE_CONTEXT` - Compliance expectations
- `EXTRACTION_ACCURACY_GUIDELINES` - Accuracy requirements
- `SPEAKER_IDENTIFICATION_GUIDELINES` - Speaker role definitions
- `JSON_OUTPUT_INSTRUCTION` - JSON formatting requirements
- `CONFIDENCE_SCORE_GUIDANCE` - Confidence score guidelines

### 2. Diarization Prompts (`diarization_prompts.py`)

**Functions:**
- `get_diarization_prompt()` - Identify speakers
- `get_speaker_labeling_prompt()` - Label segments
- `get_diarization_verification_prompt()` - Verify quality

**LLM Calls:** 3 per call

### 3. Call Type Prompts (`call_type_prompts.py`)

**Functions:**
- `get_call_type_detection_prompt()` - Detect call type

**LLM Calls:** 1 per call

**Call Types:**
- `fresh_sales` - New inquiry
- `follow_up_inquiry` - Following up on pending job
- `existing_customer_service` - Service issue

### 4. Summary Prompts (`summary_prompts.py`)

**Functions:**
- `get_summary_extraction_prompt()` - Extract chunk summary
- `get_summary_merge_prompt()` - Merge chunks into final summary

**LLM Calls:** N (chunks) + 1 (merge)

### 5. Compliance Prompts (`compliance_prompts.py`)

**Functions:**
- `get_compliance_extraction_prompt()` - Evaluate SOP compliance

**LLM Calls:** N (chunks)

### 6. Qualification Prompts (`qualification_prompts.py`)

**Functions:**
- `get_core_qualification_prompt()` - BANT scores
- `get_appointment_details_prompt()` - Booking info
- `get_customer_intelligence_prompt()` - Customer details
- `get_property_details_prompt()` - Property specifics

**LLM Calls:** 4 × N (chunks)

### 7. Objection Prompts (`objection_prompts.py`)

**Functions:**
- `get_initial_objection_detection_prompt()` - Find potential objections
- `get_objection_classification_prompt()` - Categorize objections
- `get_speaker_validation_prompt()` - Validate speaker attribution
- `get_objection_cross_validation_prompt()` - Catch false positives
- `get_objection_response_suggestions_prompt()` - Generate responses

**LLM Calls:** 4 per call (detection, classification, speaker validation, cross-validation)

### 8. SOP Prompts (`sop_prompts.py`)

**Functions:**
- `get_sop_validation_prompt()` - Validate SOP document
- `get_sop_metric_extraction_prompt()` - Extract metrics
- `get_sop_evaluation_prompt()` - Evaluate against SOP
- `get_role_detection_prompt()` - Detect rep role (unused in pipeline)

**LLM Calls:** 2 per SOP upload (validation + extraction)

---

## Prompt Design Principles

### 1. Clear Instructions
- Start with task description
- Provide context
- Define expected output format

### 2. Home Services Context
- All prompts include industry-specific context
- Terminology guides
- Domain knowledge

### 3. Structured Output
- All prompts request JSON output
- Schemas defined in prompts
- Consistent field naming

### 4. Accuracy Focus
- Extract only explicit information
- Use exact quotes
- Handle spelled-out information
- Provide confidence scores

### 5. Context Awareness
- Include call context (call type, role, history)
- Reference previous extractions
- Provide relevant examples

---

## Updating Prompts

### Best Practices

1. **Test Changes**: Always test prompt changes with sample data
2. **Version Control**: Track changes in git with clear commit messages
3. **A/B Testing**: Keep old version for comparison
4. **Document**: Add comments explaining complex logic
5. **Review**: Have another developer review prompt changes

### Example: Adding a New Prompt

```python
# In appropriate prompts file (e.g., qualification_prompts.py)

def get_new_extraction_prompt(
    chunk_text: str,
    call_context: Dict[str, Any]
) -> str:
    """
    Prompt for extracting new information
    
    Args:
        chunk_text: Transcript chunk
        call_context: Call metadata
        
    Returns:
        Formatted prompt string
    """
    return f"""Analyze this transcript and extract X.

{HOME_SERVICES_CONTEXT}  # Always include relevant context

**TRANSCRIPT:**
{chunk_text}

**TASK:**
Extract X information...

**OUTPUT FORMAT (JSON):**
{{
  "field1": "value",
  "field2": <number>
}}

{JSON_OUTPUT_INSTRUCTION}"""
```

Then add to `__init__.py`:

```python
from .qualification_prompts import (
    # ... existing
    get_new_extraction_prompt,  # Add new one
)

__all__ = [
    # ... existing
    'get_new_extraction_prompt',  # Export it
]
```

---

## Prompt Versioning

Track major prompt changes:

```python
# In __init__.py
__version__ = "1.0.0"

# Version History:
# 1.0.0 - Initial centralized prompts (Jan 16, 2026)
#       - Moved all prompts from services to central location
#       - Added home services context
#       - Standardized JSON output formats
```

---

## Testing Prompts

### Unit Testing

```python
import pytest
from app.prompts import get_summary_extraction_prompt

def test_summary_extraction_prompt():
    """Test that prompt includes required components"""
    prompt = get_summary_extraction_prompt(
        chunk_text="Test transcript",
        call_context={'call_id': 'test'}
    )
    
    assert "HOME SERVICES" in prompt
    assert "TRANSCRIPT CHUNK:" in prompt
    assert "OUTPUT FORMAT (JSON):" in prompt
```

### Integration Testing

Test prompts with actual LLM to ensure they work:

```python
async def test_prompt_with_llm():
    """Test prompt produces valid JSON from LLM"""
    prompt = get_summary_extraction_prompt(
        chunk_text="Customer called about roof repair...",
        call_context={'call_id': 'test', 'rep_role': 'customer_rep'}
    )
    
    response = await llm_client.chat.completions.create(...)
    result = json.loads(response.choices[0].message.content)
    
    assert 'call_summary' in result
    assert 'key_points' in result
```

---

## Common Issues

### Issue: LLM Doesn't Return Valid JSON

**Solution:**
- Ensure `{JSON_OUTPUT_INSTRUCTION}` is included
- Check for conflicting instructions
- Use temperature=0.1 for more deterministic output

### Issue: Extracted Information Is Inaccurate

**Solution:**
- Add more specific instructions
- Include more examples
- Add validation criteria
- Use `{EXTRACTION_ACCURACY_GUIDELINES}`

### Issue: Context Overflow (Too Many Tokens)

**Solution:**
- Truncate less important context
- Summarize previous extractions
- Split into multiple smaller prompts

---

## Future Improvements

- [ ] Add prompt performance metrics tracking
- [ ] Implement A/B testing framework
- [ ] Create prompt templates for easy customization
- [ ] Add multi-language support
- [ ] Build prompt optimization pipeline

---

## Support

For questions or issues with prompts:
1. Check this README
2. Review prompt docstrings
3. Test with sample data
4. Contact development team

---

**Maintained by:** Otto Intelligence Team  
**Last Review:** January 16, 2026

