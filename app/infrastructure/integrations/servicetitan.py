"""
ServiceTitan API client.

Handles OAuth2 client_credentials authentication and REST API calls.
Supports both production and integration environments.

Uses the Export API endpoints (continueFrom token pagination) for polling,
and standard paginated endpoints for one-off lookups / credential verification.
"""
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_iso_duration(duration_str: str | None) -> int | None:
    """
    Parse an ISO 8601 duration string (e.g. "PT5M30S") into total seconds.

    Returns None if the input is None or unparseable.
    """
    if not duration_str:
        return None
    # Handle plain integer strings (seconds)
    if duration_str.isdigit():
        return int(duration_str)
    m = re.match(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        duration_str,
        re.IGNORECASE,
    )
    if not m:
        return None
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(float(m.group(3) or 0))
    return hours * 3600 + minutes * 60 + seconds


class ServiceTitanClient:
    """OAuth2 client for ServiceTitan REST APIs."""

    PROD_AUTH = "https://auth.servicetitan.io/connect/token"
    PROD_API = "https://api.servicetitan.io"
    INT_AUTH = "https://auth-integration.servicetitan.io/connect/token"
    INT_API = "https://api-integration.servicetitan.io"

    def __init__(
        self,
        tenant_id: str | int,
        client_id: str,
        client_secret: str,
        app_key: str | None = None,
        env: str | None = None,
    ):
        self.tenant_id = str(tenant_id)
        self.client_id = client_id
        self.client_secret = client_secret
        # Fall back to global platform app key/env from settings if not provided per-tenant
        self.app_key = app_key or settings.ST_APP_KEY
        self.env = (env or settings.ST_ENV).lower()

        if self.env == "production":
            self._auth_url = self.PROD_AUTH
            self._api_base = self.PROD_API
        else:
            self._auth_url = self.INT_AUTH
            self._api_base = self.INT_API

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    async def _ensure_token(self, client: httpx.AsyncClient) -> str:
        """Fetch or refresh OAuth2 access token, caching until 60s before expiry."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        logger.info(f"Fetching new ST access token for tenant {self.tenant_id}")
        response = await client.post(
            self._auth_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        self._access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        self._token_expires_at = time.time() + expires_in
        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "ST-App-Key": self.app_key,
            "Content-Type": "application/json",
        }

    # ----------------------------------------------------------------------- #
    #  Low-level helpers                                                       #
    # ----------------------------------------------------------------------- #

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated GET request."""
        async with (httpx.AsyncClient() if client is None else _nullctx(client)) as c:
            token = await self._ensure_token(c)
            url = f"{self._api_base}{path}"
            response = await c.get(
                url,
                headers=self._auth_headers(token),
                params=params or {},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

    async def _get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages of a standard paginated ST endpoint."""
        items: list[dict[str, Any]] = []
        page = 1
        page_size = 50
        base_params = dict(params or {})
        base_params["pageSize"] = page_size

        async with httpx.AsyncClient() as client:
            while True:
                base_params["page"] = page
                token = await self._ensure_token(client)
                url = f"{self._api_base}{path}"
                response = await client.get(
                    url,
                    headers=self._auth_headers(token),
                    params=base_params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                page_items = data.get("data", [])
                items.extend(page_items)
                if not data.get("hasMore", False):
                    break
                page += 1

        return items

    async def _get_export(
        self,
        path: str,
        from_token: str | None = None,
        seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Fetch records from an ST Export endpoint using continueFrom tokens.

        Export endpoints return: { hasMore, continueFrom, data[] }

        Args:
            path: API path
            from_token: continueFrom token from the previous poll cycle
            seed_only: If True, fast-forward to the latest continueFrom token
                       without collecting data. Used on first run to skip
                       historical backfill and start polling from "now".

        Returns:
            (items, final_continueFrom) — items is empty when seed_only=True.
        """
        items: list[dict[str, Any]] = []
        cursor = from_token

        async with httpx.AsyncClient() as client:
            while True:
                token = await self._ensure_token(client)
                url = f"{self._api_base}{path}"
                params: dict[str, Any] = {}
                if cursor:
                    params["from"] = cursor
                response = await client.get(
                    url,
                    headers=self._auth_headers(token),
                    params=params,
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
                cursor = data.get("continueFrom")

                if seed_only:
                    # Keep paging to reach the end, but discard data
                    if not data.get("hasMore", False):
                        break
                    continue

                page_items = data.get("data", [])
                items.extend(page_items)
                if not data.get("hasMore", False):
                    break

        return items, cursor

    # ----------------------------------------------------------------------- #
    #  Export endpoints (for polling worker)                                    #
    # ----------------------------------------------------------------------- #

    async def export_calls(
        self, from_token: str | None = None, seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Export calls via the flat export feed.

        Returns (items, continueFrom). Each item is a Telecom.V2.ExportCallResponse:
          { id, from, to, duration (ISO 8601), direction, status, type (call classification),
            recordingUrl, customer: {id, name}, agent, campaign, lead, ... }
        """
        path = f"/telecom/v2/tenant/{self.tenant_id}/export/calls"
        return await self._get_export(path, from_token, seed_only=seed_only)

    async def export_customers(
        self, from_token: str | None = None, seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Export customers.

        Returns (items, continueFrom). Each item is a Crm.V2.ExportCustomerResponse:
          { id, name, type, address: {street, city, state, zip, country, lat, lng}, ... }
        NOTE: Customer records do NOT include phone/email contacts. Use export_customer_contacts().
        """
        path = f"/crm/v2/tenant/{self.tenant_id}/export/customers"
        return await self._get_export(path, from_token, seed_only=seed_only)

    async def export_customer_contacts(
        self, from_token: str | None = None, seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Export customer contact methods (phone, email, fax).

        Returns (items, continueFrom). Each item is a Crm.V2.ExportCustomerContactResponse:
          { id, type (Phone/Email/Fax/MobilePhone), value, customerId, active, ... }
        """
        path = f"/crm/v2/tenant/{self.tenant_id}/export/customers/contacts"
        return await self._get_export(path, from_token, seed_only=seed_only)

    async def export_leads(
        self, from_token: str | None = None, seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Export leads.

        Returns (items, continueFrom). Each item is a Crm.V2.ExportLeadsResponse:
          { id, status (Open/Dismissed/Converted), customerId, leadPhone, leadEmail,
            leadCustomerName, leadStreet, leadCity, leadState, leadZip, bookingId, callId, ... }
        """
        path = f"/crm/v2/tenant/{self.tenant_id}/export/leads"
        return await self._get_export(path, from_token, seed_only=seed_only)

    async def export_bookings(
        self, from_token: str | None = None, seed_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """
        Export bookings (ServiceTitan's equivalent of appointments).

        Tries the export endpoint first. If the app key lacks export permission
        (403), falls back to the standard paginated endpoint using the token as
        a modifiedOnOrAfter ISO timestamp.

        Returns (items, continueFrom/timestamp_token).
        """
        path = f"/crm/v2/tenant/{self.tenant_id}/export/bookings"
        try:
            return await self._get_export(path, from_token, seed_only=seed_only)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
            logger.warning(
                f"Tenant {self.tenant_id}: bookings export returned 403, "
                f"falling back to paginated endpoint"
            )

        # Fallback: paginated endpoint with modifiedOnOrAfter
        now = datetime.now(timezone.utc).isoformat()
        if seed_only:
            # Just save the current timestamp as the token — no data
            return [], now

        # from_token is an ISO timestamp when using fallback mode
        modified_since = from_token or now
        items = await self._get_paginated(
            f"/crm/v2/tenant/{self.tenant_id}/bookings",
            {"modifiedOnOrAfter": modified_since},
        )
        return items, now

    # ----------------------------------------------------------------------- #
    #  Standard paginated endpoints (for one-off lookups)                      #
    # ----------------------------------------------------------------------- #

    async def get_customers(self, modified_on_or_after: str) -> list[dict[str, Any]]:
        """Fetch customers modified since the given ISO timestamp."""
        path = f"/crm/v2/tenant/{self.tenant_id}/customers"
        return await self._get_paginated(path, {"modifiedOnOrAfter": modified_on_or_after})

    async def get_leads(self, modified_on_or_after: str) -> list[dict[str, Any]]:
        """Fetch leads modified since the given ISO timestamp."""
        path = f"/crm/v2/tenant/{self.tenant_id}/leads"
        return await self._get_paginated(path, {"modifiedOnOrAfter": modified_on_or_after})

    async def get_customer(self, customer_id: str | int) -> dict[str, Any]:
        """Fetch a single customer by ID."""
        path = f"/crm/v2/tenant/{self.tenant_id}/customers/{customer_id}"
        return await self._get(path)

    async def get_bookings(self, modified_on_or_after: str) -> list[dict[str, Any]]:
        """Fetch bookings modified since the given ISO timestamp."""
        path = f"/crm/v2/tenant/{self.tenant_id}/bookings"
        return await self._get_paginated(path, {"modifiedOnOrAfter": modified_on_or_after})

    async def verify_credentials(self) -> dict[str, Any]:
        """
        Validate credentials during onboarding.

        Fetches a token and makes a lightweight customers call (page=1, pageSize=1).
        Returns basic tenant info on success, raises on failure.
        """
        async with httpx.AsyncClient() as client:
            token = await self._ensure_token(client)
            url = f"{self._api_base}/crm/v2/tenant/{self.tenant_id}/customers"
            response = await client.get(
                url,
                headers=self._auth_headers(token),
                params={"pageSize": 1, "page": 1},
                timeout=30,
            )
            response.raise_for_status()
            return {
                "tenant_id": self.tenant_id,
                "env": self.env,
                "status": "valid",
            }


class _nullctx:
    """Async no-op context manager that wraps an existing client."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *_: Any) -> None:
        pass
