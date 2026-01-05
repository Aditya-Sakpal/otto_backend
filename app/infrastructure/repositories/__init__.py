"""Repository layer for data access."""

from app.infrastructure.repositories.call import CallRepository
from app.infrastructure.repositories.analysis import CallAnalysisRepository

__all__ = [
    "CallRepository",
    "CallAnalysisRepository",
]

