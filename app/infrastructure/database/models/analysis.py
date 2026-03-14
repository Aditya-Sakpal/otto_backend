"""
Call analysis ORM model.
"""
from sqlalchemy import String, Text, Float, ARRAY, ForeignKey, JSON, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from uuid import uuid4, UUID

from app.infrastructure.database.base import Base


class CallAnalysisORM(Base):
    """Call analysis ORM model."""

    __tablename__ = "call_analyses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    call_id: Mapped[UUID] = mapped_column(ForeignKey("calls.id"), nullable=False, unique=True, index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)

    # Qualification
    qualification_status: Mapped[str | None] = mapped_column(String, nullable=True)
    booking_status: Mapped[str | None] = mapped_column(String, nullable=True)

    # Objections
    objections: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    objection_texts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    objections_total_count: Mapped[int] = mapped_column(Integer, default=0)

    # SOP Compliance
    sop_stages_completed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sop_stages_missed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sop_stages_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sop_compliance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sop_compliance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sop_compliance_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sop_compliance_issues: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    sop_compliance_positive_behaviors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    compliance_target_role: Mapped[str | None] = mapped_column(String(50), nullable=True)  # The role this call was evaluated against

    # Sentiment
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    action_items: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    next_steps: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    pending_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Array of action objects
    summary_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # BANT Scores
    bant_need_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bant_budget_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bant_timeline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bant_authority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualification_overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qualification_confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    call_outcome_category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Appointment
    appointment_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    appointment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    appointment_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    appointment_timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    appointment_time_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_time_window: Mapped[str | None] = mapped_column(String(100), nullable=True)
    appointment_intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_appointment_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_requested_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Service
    service_requested: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_not_offered_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_address_structured: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    address_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Customer
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_name_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_makers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    urgency_signals: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    budget_indicators: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Follow-up
    follow_up_required: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional qualification fields (from Shunya Summary API)
    detected_call_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # fresh_sales, follow_up_inquiry, existing_customer_service
    is_existing_customer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_deprioritized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    service_wait_time_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_rules: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # Tenant-specific rules applied
    property_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Home services property info
    customer_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Customer details with address

    # Scope
    scope: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    # Raw analysis
    raw_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.current_timestamp(),
    )

    # Relationships
    call = relationship("CallORM", back_populates="analysis")

