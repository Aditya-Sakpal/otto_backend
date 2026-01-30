"""
Settings API response schemas.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import Field

from app.domain.models.base import BaseModel


class IntegrationResponse(BaseModel):
    """Integration response model."""
    id: UUID
    company_id: UUID
    provider: str = Field(..., description="Provider name (CRM or VoIP)")
    provider_type: str = Field(..., description="Type: 'crm' or 'voip'")
    status: str = Field(default="connected", description="Connection status: 'connected' or 'disconnected'")
    description: str = Field(..., description="Integration description")
    last_sync: Optional[str] = Field(None, description="Last sync timestamp (ISO format)")
    location_id: Optional[str] = Field(None, description="Location ID (for GHL)")
    company_id_external: Optional[str] = Field(None, description="External company ID")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")


class IntegrationsListResponse(BaseModel):
    """List of integrations."""
    integrations: List[IntegrationResponse]
    total_count: int


class DocumentResponse(BaseModel):
    """Document response model."""
    document_type: str = Field(..., description="Type: 'reference', 'sop', 'csr_sop', 'sales_sop'")
    name: str = Field(..., description="Document name")
    url: Optional[str] = Field(None, description="Document URL")
    type: str = Field(..., description="File type (PDF, DOCX, etc.)")
    size: Optional[str] = Field(None, description="File size (e.g., '2.4 MB')")
    uploaded_at: Optional[str] = Field(None, description="Upload date (ISO format)")
    uploaded_by: Optional[str] = Field(None, description="Uploader name")


class DocumentsListResponse(BaseModel):
    """List of documents."""
    documents: List[DocumentResponse]
    total_count: int


class UpdateIntegrationRequest(BaseModel):
    """Request to update integration."""
    crm_provider: Optional[str] = Field(None, description="CRM provider name")
    crm_api_key: Optional[str] = Field(None, description="CRM API key (will be encrypted)")
    crm_company_id: Optional[str] = Field(None, description="CRM company ID")
    voip_provider: Optional[str] = Field(None, description="VoIP provider name")
    voip_api_key: Optional[str] = Field(None, description="VoIP API key (will be encrypted)")
    voip_company_id: Optional[str] = Field(None, description="VoIP company ID")
    location_id: Optional[str] = Field(None, description="Location ID (for GHL)")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")


class CreateIntegrationRequest(BaseModel):
    """Request to create integration."""
    crm_provider: Optional[str] = Field(None, description="CRM provider name")
    crm_api_key: Optional[str] = Field(None, description="CRM API key (will be encrypted)")
    crm_company_id: Optional[str] = Field(None, description="CRM company ID")
    voip_provider: Optional[str] = Field(None, description="VoIP provider name")
    voip_api_key: Optional[str] = Field(None, description="VoIP API key (will be encrypted)")
    voip_company_id: Optional[str] = Field(None, description="VoIP company ID")
    location_id: Optional[str] = Field(None, description="Location ID (for GHL)")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateDocumentRequest(BaseModel):
    """Request to update document."""
    name: Optional[str] = Field(None, description="Document name")
    document_type: str = Field(..., description="Type: 'reference', 'sop', 'csr_sop', 'sales_sop'")


class SettingsResponse(BaseModel):
    """Complete settings response."""
    integrations: List[IntegrationResponse]
    documents: List[DocumentResponse]
