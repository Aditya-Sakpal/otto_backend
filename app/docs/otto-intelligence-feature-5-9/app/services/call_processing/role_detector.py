"""
LLM-Based Role Detector

Detects the representative's role from call content:
- customer_rep (CSR): Phone-based customer service, scheduling, initial qualification
- sales_rep: In-person meetings, proposals, closing

Uses semantic understanding instead of keyword matching for accurate detection.
"""

from typing import Dict, Any, Optional
import json
import logging

from ...config import get_settings
from ...core.llm import get_llm_client, get_active_model

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMRoleDetector:
    """
    LLM-based detection of representative role from call content.
    
    More accurate than keyword matching for distinguishing:
    - CSR (Customer Service Representative): Phone-based, scheduling, initial qualification
    - Sales Rep (Field Sales Representative): In-person, proposals, closing
    """
    
    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.1  # Low for consistency
    
    async def detect_role(
        self, 
        transcript: str,
        provided_role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Detect representative role from transcript content.
        
        Args:
            transcript: Full call transcript
            provided_role: Role provided in request (if any) - used for validation
            
        Returns:
            {
                "detected_role": "customer_rep" | "sales_rep",
                "confidence": 0.0-1.0,
                "key_indicators": [str],
                "call_type": "phone" | "in_person" | "unclear",
                "role_validated": bool (if provided_role matches)
            }
        """
        prompt = f"""Analyze this call transcript to determine the REPRESENTATIVE's role.

**TRANSCRIPT:**
{transcript}

**ROLE DEFINITIONS:**

**CSR (Customer Service Representative) - Use "customer_rep":**
- Takes INCOMING phone calls
- Schedules appointments
- Gathers initial customer information (name, address, phone, email)
- Handles phone-based customer service
- Answers general questions
- Transfers calls to specialists
- Typical phrases:
  - "Thank you for calling [Company]"
  - "How can I help you today?"
  - "Let me schedule an appointment"
  - "Can I get your address?"
  - "What day works for you?"
  - "I'll transfer you to..."
  - "Let me look at our schedule"

**Sales Rep (Field Sales Representative) - Use "sales_rep":**
- Conducts IN-PERSON meetings
- Presents proposals and contracts
- Discusses detailed pricing and options
- Handles objections face-to-face
- Closes deals and gets signatures
- Discusses financing options
- Reviews inspection findings
- Typical phrases:
  - "Looking at this proposal..."
  - "The total cost would be..."
  - "If you sign today..."
  - "Let me show you the inspection photos"
  - "Here are your financing options"
  - "The warranty covers..."
  - "Let's go over the contract"

**INDICATORS:**
- Opening with "Thank you for calling..." = customer_rep (phone call)
- Discussing "proposal", "contract", "financing" = sales_rep (in-person)
- Scheduling future appointments = customer_rep
- Reviewing inspection results with customer = sales_rep
- Taking down customer contact info = customer_rep
- Getting signatures = sales_rep

**OUTPUT FORMAT (JSON only):**
{{
    "detected_role": "customer_rep" | "sales_rep",
    "confidence": 0.0-1.0,
    "key_indicators": ["list of phrases/indicators that determined this role"],
    "call_type": "phone" | "in_person" | "unclear"
}}

Analyze and output JSON only:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You detect representative roles from call transcripts. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Add validation against provided role if any
            if provided_role:
                result["role_validated"] = result.get("detected_role") == provided_role
                if not result["role_validated"]:
                    logger.warning(f"Detected role '{result.get('detected_role')}' differs from provided role '{provided_role}'")
            else:
                result["role_validated"] = None
            
            logger.info(f"Role detected: {result.get('detected_role')} (confidence: {result.get('confidence')})")
            return result
            
        except Exception as e:
            logger.error(f"Role detection failed: {e}")
            # Default to customer_rep on error (most common)
            return {
                "detected_role": provided_role or "customer_rep",
                "confidence": 0.5,
                "key_indicators": ["error_fallback"],
                "call_type": "unclear",
                "role_validated": None
            }


# Singleton instance
_role_detector: Optional[LLMRoleDetector] = None


def get_role_detector() -> LLMRoleDetector:
    """Get singleton role detector instance."""
    global _role_detector
    if _role_detector is None:
        _role_detector = LLMRoleDetector()
    return _role_detector

