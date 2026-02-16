"""
SOP Validation Service

LLM-based validation to ensure uploaded documents are valid SOPs.
"""

import logging
import json
from typing import Dict, Any, Optional

from app.config import settings


logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when document validation fails"""
    pass


class ValidationService:
    """Service for validating SOP documents"""
    
    def __init__(self):
        """Initialize validation service"""
        self.llm_client = None
        self._init_llm_client()
    
    def _init_llm_client(self):
        """Initialize LLM client for validation"""
        try:
            from app.core.llm import get_llm_client
            
            self.llm_client = get_llm_client()
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
    
    async def validate_sop_document(self, document_preview: str, filename: str) -> Dict[str, Any]:
        """
        Validate if document is a valid SOP using LLM.
        
        Args:
            document_preview: First 5000 characters of document
            filename: Original filename
            
        Returns:
            Dict with validation results:
            {
                "is_sop": bool,
                "confidence": float,
                "sop_type": str | None,
                "detected_roles": list,
                "has_metrics": bool,
                "has_procedures": bool,
                "rejection_reason": str | None
            }
            
        Raises:
            ValidationError: If validation fails
        """
        if not self.llm_client:
            logger.warning("LLM client not available, performing basic validation")
            return self._basic_validation(document_preview, filename)
        
        try:
            from app.core.llm import get_active_model, get_max_tokens_param
            
            # Build validation prompt
            prompt = self._build_validation_prompt(document_preview)
            
            # Call LLM
            response = await self.llm_client.chat.completions.create(
                model=get_active_model(),
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing business documents and identifying Standard Operating Procedures (SOPs)."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                **get_max_tokens_param(500)
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            result = self._parse_validation_response(result_text)
            
            return result
            
        except Exception as e:
            logger.error(f"LLM validation error: {str(e)}")
            # Fall back to basic validation
            return self._basic_validation(document_preview, filename)
    
    def _build_validation_prompt(self, document_preview: str) -> str:
        """Build LLM prompt for SOP validation"""
        return f"""Analyze this document and determine if it is a Standard Operating Procedure (SOP) document.

Document Content (first 5000 chars):
{document_preview}

An SOP document typically:
- Contains procedural steps or guidelines
- Has role-specific instructions
- Includes evaluation criteria or performance metrics
- Is structured with sections and headers
- Provides standardized processes for specific tasks or roles

Return your analysis in JSON format:
{{
    "is_sop": true/false,
    "confidence": 0.0-1.0,
    "sop_type": "sales_sop" | "support_sop" | "general_sop" | null,
    "detected_roles": ["role1", "role2", ...],
    "has_metrics": true/false,
    "has_procedures": true/false,
    "rejection_reason": "explanation if not SOP" or null
}}

Respond ONLY with valid JSON."""
    
    def _parse_validation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM validation response"""
        try:
            # Try to extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                result = json.loads(json_str)
                
                # Validate required fields
                required_fields = ["is_sop", "confidence"]
                for field in required_fields:
                    if field not in result:
                        raise ValueError(f"Missing required field: {field}")
                
                return result
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            logger.error(f"Failed to parse validation response: {e}")
            raise ValidationError(f"Invalid validation response: {str(e)}")
    
    def _basic_validation(self, document_preview: str, filename: str) -> Dict[str, Any]:
        """
        Basic validation without LLM (fallback).
        
        Checks for common SOP indicators:
        - Keywords like "procedure", "process", "guidelines", "SOP"
        - Numbered or bulleted lists
        - Section headers
        """
        preview_lower = document_preview.lower()
        
        # SOP indicators
        sop_keywords = [
            "standard operating procedure",
            "sop",
            "procedure",
            "process",
            "guidelines",
            "instructions",
            "protocol",
            "step-by-step"
        ]
        
        # Performance indicators
        performance_keywords = [
            "metric",
            "kpi",
            "performance",
            "evaluation",
            "score",
            "rating",
            "criteria"
        ]
        
        # Count indicators
        sop_score = sum(1 for keyword in sop_keywords if keyword in preview_lower)
        performance_score = sum(1 for keyword in performance_keywords if keyword in preview_lower)
        
        # Check for structure
        has_numbers = any(char.isdigit() for char in document_preview[:500])
        has_bullets = any(bullet in document_preview for bullet in ['•', '-', '*'])
        
        # Make decision
        is_sop = sop_score >= 2 and (has_numbers or has_bullets)
        confidence = min(0.9, (sop_score + performance_score) / 10)
        
        result = {
            "is_sop": is_sop,
            "confidence": confidence,
            "sop_type": "general_sop" if is_sop else None,
            "detected_roles": [],
            "has_metrics": performance_score > 0,
            "has_procedures": sop_score >= 2,
            "rejection_reason": None if is_sop else "Document does not appear to contain standard operating procedures"
        }
        
        return result
    
    async def validate_extracted_metrics(self, metrics: list) -> Dict[str, Any]:
        """
        Validate extracted metrics.
        
        Args:
            metrics: List of extracted metrics
            
        Returns:
            Dict with validation results
        """
        errors = []
        warnings = []
        
        # Check total count
        if len(metrics) == 0:
            errors.append("No metrics extracted")
        elif len(metrics) < 3:
            warnings.append(f"Only {len(metrics)} metrics found - expected at least 3")
        
        # Validate individual metrics
        total_weight = 0
        for i, metric in enumerate(metrics):
            # Check required fields
            required_fields = ["metric_id", "metric_name", "description", "evaluation_method"]
            for field in required_fields:
                if field not in metric or not metric[field]:
                    errors.append(f"Metric {i+1}: Missing required field '{field}'")
            
            # Check weight
            if "weight" in metric:
                weight = metric["weight"]
                if not isinstance(weight, (int, float)) or weight < 0 or weight > 1:
                    errors.append(f"Metric {i+1}: Invalid weight {weight} (must be 0-1)")
                else:
                    total_weight += weight
        
        # Check total weight
        if total_weight > 0:
            if abs(total_weight - 1.0) > 0.1:
                warnings.append(f"Total weight is {total_weight:.2f} (should be close to 1.0)")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "metrics_count": len(metrics),
            "total_weight": total_weight
        }

