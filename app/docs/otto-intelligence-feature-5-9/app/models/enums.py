"""
Otto Intelligence Service - Enums

All enum definitions used across the service.
Based on ENUMS_INVENTORY_BY_SERVICE.md
"""

from enum import Enum
from typing import Any


# ============================================================================
# LEAD QUALIFICATION ENUMS
# ============================================================================

class QualificationStatus(str, Enum):
    """Lead qualification status"""
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    UNQUALIFIED = "unqualified"


class LeadBand(str, Enum):
    """
    Lead band classification based on BANT score.
    Fixed thresholds (not company-customizable per manager decision).
    """
    HOT = "hot"      # Score 75-100: Ready to buy, high priority
    WARM = "warm"    # Score 50-74: Qualified, needs nurturing
    COLD = "cold"    # Score 0-49: Needs development


class BookingStatus(str, Enum):
    """Appointment booking status"""
    BOOKED = "booked"
    NOT_BOOKED = "not_booked"
    SERVICE_NOT_OFFERED = "service_not_offered"


class AppointmentType(str, Enum):
    """Type of appointment"""
    IN_PERSON = "in-person"
    VIRTUAL = "virtual"
    PHONE = "phone"


class CallOutcomeCategory(str, Enum):
    """Call outcome classification"""
    QUALIFIED_AND_BOOKED = "qualified_and_booked"
    QUALIFIED_SERVICE_NOT_OFFERED = "qualified_service_not_offered"
    QUALIFIED_BUT_UNBOOKED = "qualified_but_unbooked"
    QUALIFIED_BUT_DEPRIORITIZED = "qualified_but_deprioritized"  # Service deferred due to high demand
    FOLLOW_UP_INQUIRY = "follow_up_inquiry"  # Existing customer follow-up on pending matter
    EXISTING_CUSTOMER_SERVICE = "existing_customer_service"  # Already booked/completed job inquiry


class CallTypeCategory(str, Enum):
    """Type of call for existing customers"""
    NEW_INQUIRY = "new_inquiry"  # First-time customer or new opportunity
    CONFIRMATION = "confirmation"  # Confirming existing appointment
    FOLLOW_UP = "follow_up"  # Post-sale follow-up or installation scheduling
    SERVICE_CALL = "service_call"  # Existing customer with service issue
    QUOTE_ONLY = "quote_only"  # Customer wants phone quote without inspection
    # Legacy values (kept for backward compatibility)
    FRESH_SALES = "fresh_sales"  # Alias for NEW_INQUIRY
    EXISTING_SERVICE = "existing_service"  # Alias for SERVICE_CALL


class RepRole(str, Enum):
    """Representative role types"""
    CUSTOMER_REP = "customer_rep"  # CSR - phone-based customer service
    SALES_REP = "sales_rep"  # Field sales representative


class ServicePriority(str, Enum):
    """Service priority levels for tenant configuration"""
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    DEFERRED = "deferred"
    NOT_OFFERED = "not_offered"


# ============================================================================
# CONVERSATION PHASE ENUMS (per Q49-Q60)
# ============================================================================

class ConversationPhase(str, Enum):
    """
    Semantic phases of a sales conversation.
    
    Per manager decisions:
    - Q49: Core phases only (6 phases)
    - Q50: Use LLM for semantic detection
    - Q51: Overlap allowed between phases
    """
    GREETING = "greeting"                    # Opening pleasantries, name exchange
    PROBLEM_DISCOVERY = "problem_discovery"  # Understanding customer need/pain point
    QUALIFICATION = "qualification"          # BANT questions, assessing fit
    OBJECTION_HANDLING = "objection_handling"  # Addressing concerns/pushback
    CLOSING = "closing"                      # Asking for business, booking appointment
    POST_CLOSE = "post_close"                # Wrap-up, next steps after commitment


# ============================================================================
# PERFORMANCE EVALUATION ENUMS
# ============================================================================

class OutcomeDecision(str, Enum):
    """Rep performance evaluation decision"""
    PASS = "pass"
    NEEDS_COACHING = "needs_coaching"
    FAIL = "fail"


# ============================================================================
# PENDING ACTIONS ENUMS
# ============================================================================

class ActionType(str, Enum):
    """Types of pending actions"""
    # Callback / Follow-Up
    CALL_BACK = "call_back"
    FOLLOW_UP_CALL = "follow_up_call"
    CHECK_IN = "check_in"
    
    # Send Information
    SEND_QUOTE = "send_quote"
    SEND_ESTIMATE = "send_estimate"
    SEND_CONTRACT = "send_contract"
    SEND_INFO = "send_info"
    SEND_PHOTOS = "send_photos"
    SEND_DETAILS = "send_details"
    
    # Scheduling
    SCHEDULE_APPOINTMENT = "schedule_appointment"
    SCHEDULE_VISIT = "schedule_visit"
    RESCHEDULE = "reschedule"
    CONFIRM_APPOINTMENT = "confirm_appointment"
    
    # Field Work
    SITE_VISIT = "site_visit"
    INSPECTION = "inspection"
    MEASUREMENT = "measurement"
    
    # Verification
    VERIFY_INSURANCE = "verify_insurance"
    VERIFY_DETAILS = "verify_details"
    CHECK_AVAILABILITY = "check_availability"
    CONFIRM_ADDRESS = "confirm_address"
    
    # Documentation
    PREPARE_CONTRACT = "prepare_contract"
    COLLECT_DOCUMENTS = "collect_documents"
    SEND_INVOICE = "send_invoice"
    
    # Escalation
    ESCALATE = "escalate"
    MANAGER_REVIEW = "manager_review"
    GET_APPROVAL = "get_approval"
    
    # Financial
    SETUP_FINANCING = "setup_financing"
    PROCESS_PAYMENT = "process_payment"
    SEND_PAYMENT_LINK = "send_payment_link"
    
    # Custom
    CUSTOM = "custom"


class ContactMethod(str, Enum):
    """Method of contact for pending actions"""
    PHONE = "phone"
    EMAIL = "email"
    SMS = "sms"
    IN_PERSON = "in_person"
    ANY = "any"


# ============================================================================
# MEETING SEGMENTATION ENUMS
# ============================================================================

class MeetingPhase(str, Enum):
    """Sales meeting segmentation phases"""
    RAPPORT_AGENDA = "rapport_agenda"
    PROPOSAL_CLOSE = "proposal_close"


# ============================================================================
# OPPORTUNITY ANALYSIS ENUMS
# ============================================================================

class MissedOpportunityType(str, Enum):
    """Types of missed opportunities"""
    DISCOVERY = "discovery"
    CROSS_SELL = "cross_sell"
    UPSELL = "upsell"
    QUALIFICATION = "qualification"


# ============================================================================
# OBJECTION DETECTION ENUMS
# ============================================================================

class ObjectionCategory(str, Enum):
    """
    Standardized objection categories for call analysis.
    
    These are the ONLY valid objection categories that should be extracted
    from calls. All objection extraction logic should reference this enum
    to ensure consistency.
    """
    IMMEDIATE_SERVICE_UNAVAILABILITY = "Immediate Service Unavailability"
    PHONE_CONNECTION_ISSUES = "Phone Connection Issues"
    CUSTOMER_NEEDS_TIME_TO_DECIDE = "Customer Needs Time to Decide"
    SCHEDULING_CONFLICTS = "Scheduling Conflicts"
    SERVICE_FEE_CONCERNS = "Service Fee Concerns"
    IN_PERSON_ESTIMATES_ONLY = "In-Person Estimates Only"
    INEFFICIENT_AGENT_COMMUNICATION = "Inefficient Agent Communication"
    CUSTOMER_DATA_PRIVACY_CONCERNS = "Customer Data Privacy Concerns"
    OTHER = "Other"
    SERVICE_NOT_CATERED = "Service Not Catered"
    
    @classmethod
    def get_category_mapping(cls) -> dict[int, str]:
        """
        Get mapping of category IDs (1-10) to category names.
        
        Returns:
            Dict mapping category_id to category_name
        """
        return {
            1: cls.IMMEDIATE_SERVICE_UNAVAILABILITY.value,
            2: cls.PHONE_CONNECTION_ISSUES.value,
            3: cls.CUSTOMER_NEEDS_TIME_TO_DECIDE.value,
            4: cls.SCHEDULING_CONFLICTS.value,
            5: cls.SERVICE_FEE_CONCERNS.value,
            6: cls.IN_PERSON_ESTIMATES_ONLY.value,
            7: cls.INEFFICIENT_AGENT_COMMUNICATION.value,
            8: cls.CUSTOMER_DATA_PRIVACY_CONCERNS.value,
            9: cls.OTHER.value,
            10: cls.SERVICE_NOT_CATERED.value,
        }
    
    @classmethod
    def get_category_id(cls, category_name: str) -> int:
        """
        Get category ID from category name.
        
        Args:
            category_name: The category name
            
        Returns:
            The category ID (1-10)
            
        Raises:
            ValueError: If category name is not found
        """
        mapping = cls.get_category_mapping()
        for cat_id, cat_name in mapping.items():
            if cat_name == category_name:
                return cat_id
        raise ValueError(f"Unknown objection category: {category_name}")
    
    @classmethod
    def get_category_descriptions(cls) -> dict[int, dict[str, Any]]:
        """
        Get detailed descriptions for each category for use in prompts.
        
        Returns:
            Dict mapping category_id to {name, description, examples, warnings}
        """
        return {
            1: {
                "name": cls.IMMEDIATE_SERVICE_UNAVAILABILITY.value,
                "description": "Company can't help now/soon enough",
                "examples": [
                    '"You can\'t come until January? That\'s too far out"',
                    '"I need this done sooner"'
                ],
                "warnings": [
                    "❌ NOT: Complaints about wait time for existing jobs (use 7)"
                ]
            },
            2: {
                "name": cls.PHONE_CONNECTION_ISSUES.value,
                "description": "Call quality problems, disconnects",
                "examples": [],
                "warnings": []
            },
            3: {
                "name": cls.CUSTOMER_NEEDS_TIME_TO_DECIDE.value,
                "description": "Customer delays decision",
                "examples": [
                    '"Let me think about it"',
                    '"I need to discuss with my spouse"'
                ],
                "warnings": [
                    '❌ NOT: Customer saying "we\'ll postpone our vacation" = COOPERATION'
                ]
            },
            4: {
                "name": cls.SCHEDULING_CONFLICTS.value,
                "description": "Customer CAN'T make proposed times",
                "examples": [
                    '"I have something at 1 o\'clock"'
                ],
                "warnings": [
                    '❌ NOT: Customer asking "what times work?" = QUESTION',
                    '❌ NOT: Customer saying "next 4 weeks, right?" = CLARIFYING'
                ]
            },
            5: {
                "name": cls.SERVICE_FEE_CONCERNS.value,
                "description": "ONLY for PRICE/COST issues",
                "examples": [
                    '"That\'s too expensive"',
                    '"Why is there a fee?"',
                    '"Can you waive the cost?"'
                ],
                "warnings": [
                    "⚠️ DO NOT USE FOR: wait times, communication issues, scheduling",
                    '⚠️ DO NOT USE FOR: "been in queue too long" (use 7)',
                    '⚠️ DO NOT USE FOR: "should have called sooner" (use 7)'
                ]
            },
            6: {
                "name": cls.IN_PERSON_ESTIMATES_ONLY.value,
                "description": "Customer wants phone quote instead of in-person estimate",
                "examples": [
                    '"Can\'t you quote over the phone?"'
                ],
                "warnings": []
            },
            7: {
                "name": cls.INEFFICIENT_AGENT_COMMUNICATION.value,
                "description": "Wait times, follow-up, communication frustration",
                "examples": [
                    'Customer frustrated about WAIT TIME: "been waiting 3 months"',
                    'Customer frustrated about COMMUNICATION: "should have gotten a call"',
                    'Customer frustrated about UPDATES: "want an answer today"'
                ],
                "warnings": [
                    "⚠️ USE THIS (not 5) for: timeline complaints, lack of updates, long queues"
                ]
            },
            8: {
                "name": cls.CUSTOMER_DATA_PRIVACY_CONCERNS.value,
                "description": "Worried about sharing personal info",
                "examples": [],
                "warnings": []
            },
            9: {
                "name": cls.OTHER.value,
                "description": "Doesn't fit any category above",
                "examples": [],
                "warnings": []
            },
            10: {
                "name": cls.SERVICE_NOT_CATERED.value,
                "description": "Service not offered by company",
                "examples": [],
                "warnings": []
            },
        }


class ObjectionSeverity(str, Enum):
    """Severity level of objections"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================================
# TRANSCRIPTION ENUMS
# ============================================================================

class CallType(str, Enum):
    """Type of call"""
    SALES_CALL = "sales_call"
    CSR_CALL = "csr_call"


class SpeakerRole(str, Enum):
    """Speaker roles in conversations"""
    CUSTOMER_REP = "customer_rep"
    HOME_OWNER = "home_owner"
    SALES_REP = "sales_rep"
    MANAGER = "manager"
    UNKNOWN = "unknown"


# ============================================================================
# PROCESSING STATUS ENUMS
# ============================================================================

class ProcessingStatus(str, Enum):
    """Status of async processing jobs"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InsightType(str, Enum):
    """Type of weekly insight"""
    COMPANY = "company"
    CUSTOMER = "customer"
    OBJECTION = "objection"


# ============================================================================
# CORPUS TYPE FOR RAG
# ============================================================================

class CorpusType(str, Enum):
    """Type of document in RAG system"""
    CALL_SUMMARY = "call_summary"
    CHUNK_SUMMARY = "chunk_summary"
    FAQ = "faq"
    DOCUMENT = "document"
    SOP_DOCUMENT = "sop_document"
    SOP_METRIC = "sop_metric"
    SOP_CRITERIA = "sop_criteria"


# ============================================================================
# SENTIMENT ENUMS
# ============================================================================

class SentimentTrend(str, Enum):
    """Trend direction for sentiment analysis"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class PriorityLevel(str, Enum):
    """Priority level for tasks/customers"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TrendDirection(str, Enum):
    """General trend direction"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


# ============================================================================
# SOP DOCUMENT INGESTION ENUMS
# ============================================================================

class SOPType(str, Enum):
    """Type of SOP document"""
    SALES_SOP = "sales_sop"
    SUPPORT_SOP = "support_sop"
    GENERAL_SOP = "general_sop"


class SOPStatus(str, Enum):
    """Status of SOP document"""
    PROCESSING = "processing"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"


class ChunkType(str, Enum):
    """Type of document chunk"""
    PROCEDURE = "procedure"
    METRIC = "metric"
    CRITERIA = "criteria"
    GENERAL = "general"


class EvaluationMode(str, Enum):
    """Compliance evaluation mode"""
    SOP_ONLY = "sop_only"
    LEGACY = "legacy"
    HYBRID = "hybrid"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def compute_call_outcome_category(
    qualification_status: QualificationStatus,
    booking_status: BookingStatus,
    call_type: str = "fresh_sales",
    previous_booking_status: str = None,
    is_deprioritized: bool = False
) -> CallOutcomeCategory:
    """
    Compute call outcome category from qualification, booking status, and call type.
    
    Args:
        qualification_status: Lead qualification status
        booking_status: Appointment booking status
        call_type: Type of call ('fresh_sales', 'follow_up', 'existing_service')
        previous_booking_status: Previous booking status for existing customers
        is_deprioritized: Whether service is deprioritized due to tenant config
        
    Returns:
        CallOutcomeCategory based on the combination
    """
    # Handle existing customer scenarios first
    if call_type == "existing_service" and previous_booking_status == "booked":
        return CallOutcomeCategory.EXISTING_CUSTOMER_SERVICE
    
    if call_type == "follow_up":
        return CallOutcomeCategory.FOLLOW_UP_INQUIRY
    
    # Handle deprioritized services (from tenant config)
    if is_deprioritized and qualification_status != QualificationStatus.UNQUALIFIED:
        return CallOutcomeCategory.QUALIFIED_BUT_DEPRIORITIZED
    
    # Standard fresh sales logic
    if qualification_status == QualificationStatus.UNQUALIFIED:
        return CallOutcomeCategory.QUALIFIED_BUT_UNBOOKED
    
    if booking_status == BookingStatus.BOOKED:
        return CallOutcomeCategory.QUALIFIED_AND_BOOKED
    elif booking_status == BookingStatus.SERVICE_NOT_OFFERED:
        return CallOutcomeCategory.QUALIFIED_SERVICE_NOT_OFFERED
    else:
        return CallOutcomeCategory.QUALIFIED_BUT_UNBOOKED


def compute_outcome_decision(
    overall_score: float,
    has_critical_error: bool = False
) -> OutcomeDecision:
    """
    Compute outcome decision from score and critical error status.
    
    Args:
        overall_score: Overall compliance/performance score (0-1)
        has_critical_error: Whether a critical error was detected
        
    Returns:
        OutcomeDecision based on score and error status
    """
    # Critical error overrides score
    if has_critical_error:
        return OutcomeDecision.FAIL
    
    # Score-based decision
    score_percent = overall_score * 100
    if score_percent >= 80:
        return OutcomeDecision.PASS
    elif score_percent >= 60:
        return OutcomeDecision.NEEDS_COACHING
    else:
        return OutcomeDecision.FAIL

