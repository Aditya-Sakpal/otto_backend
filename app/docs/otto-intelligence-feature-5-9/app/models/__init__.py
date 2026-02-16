"""
Models package for Otto Intelligence Service

Contains Pydantic models and enums for data validation.
"""

from .enums import (
    ProcessingStatus,
    InsightType,
    TrendDirection,
    QualificationStatus,
    BookingStatus,
    CallOutcomeCategory,
    CallTypeCategory,
    RepRole,
    ServicePriority,
)

from .tenant_config import (
    TenantConfiguration,
    QualificationThresholds,
    QualificationRule,
    ServiceConfig,
    get_default_tenant_config,
)

__all__ = [
    # Enums
    "ProcessingStatus",
    "InsightType", 
    "TrendDirection",
    "QualificationStatus",
    "BookingStatus",
    "CallOutcomeCategory",
    "CallTypeCategory",
    "RepRole",
    "ServicePriority",
    # Tenant Config
    "TenantConfiguration",
    "QualificationThresholds",
    "QualificationRule",
    "ServiceConfig",
    "get_default_tenant_config",
]
