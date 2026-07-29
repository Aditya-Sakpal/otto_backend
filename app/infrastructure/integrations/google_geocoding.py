"""
Google Geocoding API client.

Provides geocoding of contact addresses to latitude/longitude coordinates.
"""
import asyncio
from typing import Optional, Tuple
from uuid import UUID

import httpx
from sqlalchemy import update

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.appointment import AppointmentORM

logger = get_logger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GoogleGeocodingClient:
    """Client for Google Geocoding API."""

    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        if not self.api_key:
            logger.warning("Google Maps API key not configured - geocoding disabled")

    async def geocode(
        self,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode an address to lat/lng coordinates.

        Args:
            address: Street address
            city: City name
            state: State name
            postal_code: Postal/ZIP code

        Returns:
            Tuple of (latitude, longitude) or None on failure
        """
        if not self.api_key:
            return None

        parts = [p for p in [address, city, state, postal_code] if p]
        if not parts:
            return None

        full_address = ", ".join(parts)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    GEOCODE_URL,
                    params={"address": full_address, "key": self.api_key},
                )
                response.raise_for_status()
                data = response.json()

            if data.get("status") != "OK" or not data.get("results"):
                logger.warning(f"Geocoding failed for '{full_address}': status={data.get('status')}")
                return None

            location = data["results"][0]["geometry"]["location"]
            return (location["lat"], location["lng"])

        except Exception as e:
            logger.error(f"Geocoding error for '{full_address}': {e}")
            return None


# Singleton
_client: Optional[GoogleGeocodingClient] = None


def get_google_geocoding_client() -> GoogleGeocodingClient:
    """Get or create the singleton GoogleGeocodingClient."""
    global _client
    if _client is None:
        _client = GoogleGeocodingClient()
    return _client


async def geocode_contact_background(
    contact_card_id: UUID,
    address: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    postal_code: Optional[str] = None,
) -> None:
    """
    Fire-and-forget background task to geocode a contact's address.

    Creates its own DB session to avoid interfering with the caller's transaction.
    """
    async with AsyncSessionLocal() as session:
        try:
            client = get_google_geocoding_client()
            result = await client.geocode(address, city, state, postal_code)
            if result:
                lat, lng = result
                stmt = (
                    update(ContactCardORM)
                    .where(ContactCardORM.id == contact_card_id)
                    .values(latitude=lat, longitude=lng)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Geocoded contact {contact_card_id}: ({lat}, {lng})")
            else:
                logger.debug(f"No geocoding result for contact {contact_card_id}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Background geocoding failed for contact {contact_card_id}: {e}")


async def geocode_appointment_background(
    appointment_id: UUID,
    location_address: str,
) -> None:
    """
    Fire-and-forget background task to geocode an appointment's location_address.

    Creates its own DB session to avoid interfering with the caller's transaction.
    """
    async with AsyncSessionLocal() as session:
        try:
            client = get_google_geocoding_client()
            result = await client.geocode(address=location_address)
            if result:
                lat, lng = result
                stmt = (
                    update(AppointmentORM)
                    .where(AppointmentORM.id == appointment_id)
                    .values(latitude=lat, longitude=lng)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Geocoded appointment {appointment_id}: ({lat}, {lng})")
            else:
                logger.debug(f"No geocoding result for appointment {appointment_id}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Background geocoding failed for appointment {appointment_id}: {e}")
