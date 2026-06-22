"""Shared-secret auth for Retell voice-agent tool endpoints."""
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import settings


def verify_voice_agent_secret(
    x_voice_agent_secret: Annotated[str | None, Header(alias="X-Voice-Agent-Secret")] = None,
) -> None:
    """Validate Retell custom-tool requests."""
    expected = settings.VOICE_AGENT_SECRET
    if not expected:
        if settings.is_dev_mode:
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice agent secret not configured",
        )
    if x_voice_agent_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid voice agent secret",
        )
