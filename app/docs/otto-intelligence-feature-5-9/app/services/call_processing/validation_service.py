"""
Validation Service

Service for validating generated summaries against schema.
"""

from typing import Dict, Any, List, Tuple, Optional
from ...models.enums import (
    QualificationStatus,
    BookingStatus,
    AppointmentType,
    ActionType,
    ObjectionSeverity
)


class ValidationService:
    """Service for summary validation"""
    
    def validate_summary(self, summary: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate summary JSON against expected schema.
        
        Args:
            summary: Summary dictionary to validate
            
        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []
        
        # Required top-level fields
        required_fields = ["call_id", "company_id", "summary", "compliance", "objections", "qualification"]
        for field in required_fields:
            if field not in summary:
                errors.append(f"Missing required field: {field}")
        
        # Validate summary section
        if "summary" in summary:
            errors.extend(self._validate_summary_section(summary["summary"]))
        
        # Validate compliance section
        if "compliance" in summary:
            errors.extend(self._validate_compliance_section(summary["compliance"]))
        
        # Validate objections section
        if "objections" in summary:
            errors.extend(self._validate_objections_section(summary["objections"]))
        
        # Validate qualification section
        if "qualification" in summary:
            errors.extend(self._validate_qualification_section(summary["qualification"]))
        
        return len(errors) == 0, errors
    
    def _validate_summary_section(self, summary: Dict[str, Any]) -> List[str]:
        """Validate summary section"""
        errors = []
        
        required_fields = ["summary", "key_points", "action_items", "sentiment_score"]
        for field in required_fields:
            if field not in summary:
                errors.append(f"Missing summary.{field}")
        
        # Validate sentiment score range
        if "sentiment_score" in summary:
            score = summary["sentiment_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                errors.append(f"Invalid sentiment_score: must be between 0 and 1")
        
        # Validate pending actions
        if "pending_actions" in summary:
            for i, action in enumerate(summary["pending_actions"]):
                if "type" in action:
                    try:
                        ActionType(action["type"])
                    except ValueError:
                        errors.append(f"Invalid action type at index {i}: {action['type']}")
        
        return errors
    
    def _validate_compliance_section(self, compliance: Dict[str, Any]) -> List[str]:
        """Validate compliance section"""
        errors = []
        
        if "sop_compliance" not in compliance:
            errors.append("Missing compliance.sop_compliance")
            return errors
        
        sop = compliance["sop_compliance"]
        
        required_fields = ["score", "compliance_rate", "confidence"]
        for field in required_fields:
            if field not in sop:
                errors.append(f"Missing compliance.sop_compliance.{field}")
            elif field in sop:
                score = sop[field]
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    errors.append(f"Invalid {field}: must be between 0 and 1")
        
        return errors
    
    def _validate_objections_section(self, objections: Dict[str, Any]) -> List[str]:
        """Validate objections section"""
        errors = []
        
        if "objections" not in objections:
            errors.append("Missing objections.objections list")
            return errors
        
        for i, obj in enumerate(objections["objections"]):
            # Validate category_id (1-10)
            if "category_id" in obj:
                cat_id = obj["category_id"]
                if not isinstance(cat_id, int) or cat_id < 1 or cat_id > 10:
                    errors.append(f"Invalid objection category_id at index {i}: must be 1-10")
            
            # Validate severity
            if "severity" in obj:
                try:
                    ObjectionSeverity(obj["severity"])
                except ValueError:
                    errors.append(f"Invalid objection severity at index {i}: {obj['severity']}")
            
            # Validate confidence_score
            if "confidence_score" in obj:
                score = obj["confidence_score"]
                if not isinstance(score, (int, float)) or score < 0 or score > 1:
                    errors.append(f"Invalid objection confidence_score at index {i}")
        
        return errors
    
    def _validate_qualification_section(self, qualification: Dict[str, Any]) -> List[str]:
        """Validate qualification section"""
        errors = []
        
        # Validate qualification_status
        if "qualification_status" in qualification:
            try:
                QualificationStatus(qualification["qualification_status"])
            except ValueError:
                errors.append(f"Invalid qualification_status: {qualification['qualification_status']}")
        else:
            errors.append("Missing qualification.qualification_status")
        
        # Validate booking_status
        if "booking_status" in qualification:
            try:
                BookingStatus(qualification["booking_status"])
            except ValueError:
                errors.append(f"Invalid booking_status: {qualification['booking_status']}")
        else:
            errors.append("Missing qualification.booking_status")
        
        # Validate appointment_type (if present)
        if "appointment_type" in qualification and qualification["appointment_type"]:
            try:
                AppointmentType(qualification["appointment_type"])
            except ValueError:
                errors.append(f"Invalid appointment_type: {qualification['appointment_type']}")
        
        # Validate BANT scores
        if "bant_scores" in qualification:
            bant = qualification["bant_scores"]
            required_scores = ["need", "budget", "timeline", "authority"]
            for score_name in required_scores:
                if score_name not in bant:
                    errors.append(f"Missing BANT score: {score_name}")
                else:
                    score = bant[score_name]
                    if not isinstance(score, (int, float)) or score < 0 or score > 1:
                        errors.append(f"Invalid BANT {score_name} score: must be 0-1")
        else:
            errors.append("Missing qualification.bant_scores")
        
        # Validate overall_score
        if "overall_score" in qualification:
            score = qualification["overall_score"]
            if not isinstance(score, (int, float)) or score < 0 or score > 1:
                errors.append("Invalid overall_score: must be between 0 and 1")
        
        return errors


# Singleton instance
_validation_service: Optional[ValidationService] = None


def get_validation_service() -> ValidationService:
    """Get singleton validation service instance"""
    global _validation_service
    if _validation_service is None:
        _validation_service = ValidationService()
    return _validation_service

