"""Domain models."""

from app.domain.models.base import BaseModel
from app.domain.models.company import Company
from app.domain.models.user import User
from app.domain.models.contact import ContactCard
from app.domain.models.lead import Lead
from app.domain.models.call import Call
from app.domain.models.appointment import Appointment
from app.domain.models.analysis import CallAnalysis

__all__ = [
    "BaseModel",
    "Company",
    "User",
    "ContactCard",
    "Lead",
    "Call",
    "Appointment",
    "CallAnalysis",
]

