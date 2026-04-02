"""
Settings API response schemas.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import Field, ConfigDict

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
    """Request to create integration. Provide CRM and/or VoIP details."""
    crm_provider: Optional[str] = Field(None, description="CRM provider name (e.g. 'gohighlevel', 'servicetitan')")
    crm_api_key: Optional[str] = Field(None, description="CRM API key (will be encrypted at rest)")
    crm_company_id: Optional[str] = Field(None, description="CRM company/account ID")
    voip_provider: Optional[str] = Field(None, description="VoIP/telephony provider name (e.g. 'calltrackingmetrics')")
    voip_api_key: Optional[str] = Field(None, description="VoIP API key (will be encrypted at rest)")
    voip_company_id: Optional[str] = Field(None, description="VoIP company/account ID")
    location_id: Optional[str] = Field(None, description="Location ID (for GHL multi-location)")
    extra_metadata: Optional[dict] = Field(None, description="Additional metadata")

    model_config = {
        "json_schema_extra": {
            "example": {
                "crm_provider": "gohighlevel",
                "crm_api_key": "ghl-api-key-xxxxx",
                "crm_company_id": "ghl-company-123",
                "voip_provider": "calltrackingmetrics",
                "voip_api_key": "ctm-api-key-xxxxx",
                "voip_company_id": "12345",
                "location_id": "loc_abc123",
            }
        }
    }


class UpdateDocumentRequest(BaseModel):
    """Request to update document."""
    name: Optional[str] = Field(None, description="Document name")
    document_type: str = Field(..., description="Type: 'reference', 'sop', 'csr_sop', 'sales_sop'")


class SettingsResponse(BaseModel):
    """Complete settings response."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "00000000-0000-4000-8000-000000000001",
                    "created_at": "2026-03-27T12:00:00",
                    "updated_at": None,
                    "integrations": [],
                    "documents": [],
                    "follow_up_manual_review_enabled": False,
                }
            ]
        },
    )

    integrations: List[IntegrationResponse]
    documents: List[DocumentResponse]
    follow_up_manual_review_enabled: bool = Field(
        default=False,
        description="If true, contextual follow-up agent saves drafts (proposed) until manual send",
    )


class FollowUpManualReviewPatch(BaseModel):
    """Toggle manual review before automated follow-up sends."""

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        use_enum_values=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "00000000-0000-4000-8000-000000000002",
                    "created_at": "2026-03-27T12:00:00",
                    "updated_at": None,
                    "follow_up_manual_review_enabled": True,
                }
            ]
        },
    )

    follow_up_manual_review_enabled: bool
