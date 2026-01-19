from uuid import UUID
from pydantic import Field
from typing import Optional
from app.domain.models.base import BaseModel

class CompanyIntegration(BaseModel):
    id: UUID = Field(..., description="Company integration ID")
    company_id: UUID = Field(..., description="Company ID")
    location_id: str = Field(..., description="Location ID")
    crm_api_encrypted_key: str = Field(..., description="Encrypted CRM API key")
    crm_provider: str = Field(..., description="CRM provider")
    crm_company_id: Optional[str] = Field(None, description="CRM company ID")
    voip_api_encrypted_key: str = Field(..., description="Encrypted VoIP API key")
    voip_provider: str = Field(..., description="VoIP provider")
    voip_company_id: Optional[str] = Field(None, description="VoIP company ID")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")
