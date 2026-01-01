"""
Contact domain model.

Represents a customer/contact in the system.
"""
from typing import Optional
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel


class ContactCard(BaseModel):
    """
    Contact card model.
    
    Canonical representation of a customer/contact.
    Consolidates phone numbers, emails, and addresses.
    """
    company_id: UUID = Field(..., description="Company/tenant ID")
    primary_phone: str = Field(..., description="Primary phone number")
    secondary_phone: Optional[str] = Field(None, description="Secondary phone number")
    email: Optional[str] = Field(None, description="Email address")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    address: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    postal_code: Optional[str] = Field(None, description="Postal code")
    property_snapshot: Optional[dict] = Field(None, description="Property intelligence data")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

