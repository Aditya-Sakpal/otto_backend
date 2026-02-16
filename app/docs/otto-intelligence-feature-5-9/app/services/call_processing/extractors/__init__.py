"""
Specialized extractors for parallel call summarization.

Each extractor focuses on a specific aspect of call analysis.
"""

from .summary_extractor import SummaryExtractor
from .compliance_extractor import ComplianceExtractor
from .objection_extractor import ObjectionExtractor
from .qualification_extractor import QualificationExtractor

__all__ = [
    "SummaryExtractor",
    "ComplianceExtractor",
    "ObjectionExtractor",
    "QualificationExtractor",
]

