"""
Centralized Prompt Templates for Otto Intelligence System

This package contains all prompt templates used across the system.
Prompts are organized by functionality for easy maintenance and versioning.

Usage:
    from app.prompts import get_summary_extraction_prompt, HOME_SERVICES_CONTEXT
    
    prompt = get_summary_extraction_prompt(chunk_text, call_context)
"""

# Base context and guidelines
from .base_prompts import (
    HOME_SERVICES_CONTEXT,
    PROPERTY_DETAILS_EXTRACTION,
    DECISION_MAKER_CONTEXT,
    URGENCY_EXTRACTION_CONTEXT,
    HOME_SERVICES_COMPLIANCE_CONTEXT,
    EXTRACTION_ACCURACY_GUIDELINES,
    SPEAKER_IDENTIFICATION_GUIDELINES,
    JSON_OUTPUT_INSTRUCTION,
    CONFIDENCE_SCORE_GUIDANCE,
)

# Diarization prompts
from .diarization_prompts import (
    get_diarization_prompt,
    get_speaker_labeling_prompt,
    get_diarization_verification_prompt,
)

# Call type detection
from .call_type_prompts import (
    get_call_type_detection_prompt,
)

# Summary extraction
from .summary_prompts import (
    get_summary_extraction_prompt,
    get_summary_merge_prompt,
)

# Compliance/SOP
from .compliance_prompts import (
    get_compliance_extraction_prompt,
)

# Qualification
from .qualification_prompts import (
    get_core_qualification_prompt,
    get_appointment_details_prompt,
    get_customer_intelligence_prompt,
    get_property_details_prompt,
)

# Objections
from .objection_prompts import (
    get_initial_objection_detection_prompt,
    get_objection_classification_prompt,
    get_speaker_validation_prompt,
    get_objection_cross_validation_prompt,
    get_objection_response_suggestions_prompt,
)

# SOP ingestion
from .sop_prompts import (
    get_sop_validation_prompt,
    get_sop_metric_extraction_prompt,
    get_sop_evaluation_prompt,
    get_role_detection_prompt,
)

__all__ = [
    # Base context
    'HOME_SERVICES_CONTEXT',
    'PROPERTY_DETAILS_EXTRACTION',
    'DECISION_MAKER_CONTEXT',
    'URGENCY_EXTRACTION_CONTEXT',
    'HOME_SERVICES_COMPLIANCE_CONTEXT',
    'EXTRACTION_ACCURACY_GUIDELINES',
    'SPEAKER_IDENTIFICATION_GUIDELINES',
    'JSON_OUTPUT_INSTRUCTION',
    'CONFIDENCE_SCORE_GUIDANCE',
    
    # Diarization
    'get_diarization_prompt',
    'get_speaker_labeling_prompt',
    'get_diarization_verification_prompt',
    
    # Call type
    'get_call_type_detection_prompt',
    
    # Summary
    'get_summary_extraction_prompt',
    'get_summary_merge_prompt',
    
    # Compliance
    'get_compliance_extraction_prompt',
    
    # Qualification
    'get_core_qualification_prompt',
    'get_appointment_details_prompt',
    'get_customer_intelligence_prompt',
    'get_property_details_prompt',
    
    # Objections
    'get_initial_objection_detection_prompt',
    'get_objection_classification_prompt',
    'get_speaker_validation_prompt',
    'get_objection_cross_validation_prompt',
    'get_objection_response_suggestions_prompt',
    
    # SOP
    'get_sop_validation_prompt',
    'get_sop_metric_extraction_prompt',
    'get_sop_evaluation_prompt',
    'get_role_detection_prompt',
]

# Prompt version for tracking
__version__ = "1.0.0"
