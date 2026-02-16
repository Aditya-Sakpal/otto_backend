"""
Company domain model.

Represents a tenant/organization in the multi-tenant system.
"""
from typing import Optional
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel


class Company(BaseModel):
    """
    Company (tenant) model.

    Each company is a separate tenant with isolated data.
    """
    name: str = Field(..., description="Company name")
    phone_number: Optional[str] = Field(None, description="Company phone number")
    address: Optional[str] = Field(None, description="Company address")
    reference_doc_url: Optional[str] = Field(None, description="S3 URL for reference document")
    csr_sop_doc_url: Optional[str] = Field(None, description="S3 URL for CSR SOP document")
    sales_sop_doc_url: Optional[str] = Field(None, description="S3 URL for Sales SOP document")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

