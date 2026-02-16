"""
Ghost Mode API schemas.

Request/response schemas for ghost mode operations.
"""
from pydantic import Field

from app.domain.models.base import BaseModel


class GhostModeStatusResponse(BaseModel):
    """Response for ghost mode status check."""

    company_ghost_mode_enabled: bool = Field(
        ...,
        description="Whether the company has ghost mode available for users"
    )
    user_ghost_mode_active: bool = Field(
        ...,
        description="Whether the current user has ghost mode active (only meaningful if company enabled)"
    )
    effective_ghost_mode: bool = Field(
        ...,
        description="True if both company and user ghost mode are enabled"
    )


class UpdateGhostModeRequest(BaseModel):
    """Request to toggle user ghost mode."""

    active: bool = Field(
        ...,
        description="Whether to enable (True) or disable (False) ghost mode for the user"
    )


class UpdateCompanyGhostModeRequest(BaseModel):
    """Request to toggle company ghost mode availability."""

    enabled: bool = Field(
        ...,
        description="Whether to enable (True) or disable (False) ghost mode availability for the company"
    )


class GhostModeToggleResponse(BaseModel):
    """Response for ghost mode toggle operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str = Field(..., description="Human-readable status message")
    company_ghost_mode_enabled: bool = Field(
        ...,
        description="Current company ghost mode setting"
    )
    user_ghost_mode_active: bool = Field(
        ...,
        description="Current user ghost mode setting"
    )
    effective_ghost_mode: bool = Field(
        ...,
        description="True if both company and user ghost mode are enabled"
    )
