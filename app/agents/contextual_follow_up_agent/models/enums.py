"""
Domain enums for the contextual follow-up agent.
"""
from enum import Enum


class QueueType(str, Enum):
    """Which follow-up queue a lead belongs to."""
    QUALIFIED_UNBOOKED = "qualified_unbooked"
    APPOINTMENT_RAN = "appointment_ran"


class FollowUpStatus(str, Enum):
    """Status of a follow-up log entry."""
    PROPOSED = "proposed"    # In review queue, not yet approved
    PENDING = "pending"      # Approved/scheduled, not yet sent
    SENT = "sent"            # Successfully delivered
    FAILED = "failed"        # Delivery failed
    DORMANT = "dormant"      # Lead exhausted max attempts
    CANCELLED = "cancelled"  # Manually cancelled
    OPTED_OUT = "opted_out"  # Homeowner opted out of messaging
    PAUSED = "paused"        # Sequence paused (rep intervened or homeowner replied)


class ActionType(str, Enum):
    """Type of follow-up action."""
    SMS_TO_LEAD = "sms_to_lead"
    NUDGE_SALES_REP = "nudge_sales_rep"
    MARK_DORMANT = "mark_dormant"


class PausedReason(str, Enum):
    """Reason a follow-up sequence was paused."""
    REP_INTERVENED = "rep_intervened"
    HOMEOWNER_REPLIED = "homeowner_replied"
    OPTED_OUT = "opted_out"


class CommsPath(str, Enum):
    """Communication delivery path."""
    DIRECT_SMS = "direct_sms"
    PENDING_ACTION = "pending_action"
