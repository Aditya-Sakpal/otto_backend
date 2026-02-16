"""
Diarization Prompts

Prompts for speaker identification and diarization
"""

from typing import Dict, Any, Optional, List
from .base_prompts import SPEAKER_IDENTIFICATION_GUIDELINES, JSON_OUTPUT_INSTRUCTION


def get_diarization_prompt(transcript: str) -> str:
    """Prompt for identifying speakers in a transcript"""
    return f"""Analyze this call transcript and identify distinct speakers.

{SPEAKER_IDENTIFICATION_GUIDELINES}

**TRANSCRIPT:**
{transcript}

**TASK:**
1. Identify how many distinct speakers are in this conversation
2. For each speaker, provide:
   - A consistent speaker ID (SPEAKER_1, SPEAKER_2, etc.)
   - Likely role (customer, representative, other)
   - Key characteristics that help identify them

**OUTPUT FORMAT (JSON):**
{{
  "num_speakers": <number>,
  "speakers": [
    {{
      "speaker_id": "SPEAKER_1",
      "role": "customer|representative|other",
      "characteristics": "Brief description of speech patterns or identifiers"
    }}
  ],
  "confidence": <0.0-1.0>
}}

{JSON_OUTPUT_INSTRUCTION}"""


def get_speaker_labeling_prompt(
    segments: List[str],
    unique_speakers: List[str],
    context: Optional[str] = None
) -> str:
    """Prompt for labeling speaker segments"""
    context_str = f"\n**CONTEXT:**\n{context}\n" if context else ""
    
    return f"""Label each segment with the correct speaker ID.

{SPEAKER_IDENTIFICATION_GUIDELINES}

{context_str}
**SPEAKERS:** {', '.join(unique_speakers)}

**SEGMENTS:**
{chr(10).join(f"{i+1}. {seg}" for i, seg in enumerate(segments))}

**TASK:**
Assign each segment to a speaker ID.

**OUTPUT FORMAT (JSON):**
{{
  "labeled_segments": [
    {{
      "segment_id": 1,
      "speaker_id": "SPEAKER_1",
      "confidence": 0.95
    }}
  ]
}}

{JSON_OUTPUT_INSTRUCTION}"""


def get_diarization_verification_prompt(
    sample_segments: List[Dict[str, Any]],
    full_segments: List[Dict[str, Any]]
) -> str:
    """Prompt for verifying diarization quality"""
    return f"""Verify the quality of speaker diarization.

**SAMPLE SEGMENTS:**
{sample_segments}

**TASK:**
1. Check if speaker labels are consistent
2. Identify any obvious mis-labelings
3. Assess overall diarization quality

**OUTPUT FORMAT (JSON):**
{{
  "quality_score": <0.0-1.0>,
  "issues_found": [
    {{
      "segment_id": <id>,
      "issue": "Description of issue"
    }}
  ],
  "is_acceptable": <true|false>,
  "recommendations": ["List of improvements"]
}}

{JSON_OUTPUT_INSTRUCTION}"""


__all__ = [
    'get_diarization_prompt',
    'get_speaker_labeling_prompt',
    'get_diarization_verification_prompt',
]

