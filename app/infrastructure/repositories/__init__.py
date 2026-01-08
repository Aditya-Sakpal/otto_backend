"""Repository layer for data access."""

from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository
from app.infrastructure.repositories.lead import LeadRepository
from app.infrastructure.repositories.appointment import AppointmentRepository

__all__ = [
    "CallRepository",
    "CallAnalysisRepository",
    "LeadRepository",
    "AppointmentRepository",
]

