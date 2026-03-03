"""
ServiceTitan Polling Worker.

Standalone process that periodically fetches new data from the ServiceTitan
Export APIs for every configured tenant and POSTs it to the FastAPI webhook
endpoints.

Uses the Export API endpoints which provide:
  - Flat response structures (not nested)
  - continueFrom token pagination (ideal for incremental polling)
  - Separate feeds for calls, customers, customer-contacts, leads, bookings

Run:
    python -m workers.st_poller

Environment variables:
    ST_POLL_INTERVAL          Seconds between poll cycles (default: 30)
    API_URL                   FastAPI base URL (default: http://localhost:8001)
    ST_WORKER_SECRET          Shared secret for worker → webhook auth
    DATABASE_URL              Database connection string
"""
import asyncio
import logging
import os

import httpx

from app.core.encryption import decrypt_api_key
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.integrations.servicetitan import ServiceTitanClient
from app.infrastructure.repositories.company_integration import CompanyIntegrationRepository

# --------------------------------------------------------------------------- #
#  Config                                                                      #
# --------------------------------------------------------------------------- #

POLL_INTERVAL = int(os.getenv("ST_POLL_INTERVAL", "30"))
API_URL = os.getenv("API_URL", "http://localhost:8001").rstrip("/")
WORKER_SECRET = os.getenv("ST_WORKER_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("st_poller")


# --------------------------------------------------------------------------- #
#  Entry point                                                                 #
# --------------------------------------------------------------------------- #

async def main() -> None:
    """Infinite loop: poll all tenants, sleep, repeat."""
    logger.info(
        f"ST Poller started — interval={POLL_INTERVAL}s, api={API_URL}"
    )
    while True:
        try:
            await run_poll_cycle()
        except Exception as e:
            logger.error(f"Unhandled error in poll cycle: {e}", exc_info=True)
        await asyncio.sleep(POLL_INTERVAL)


async def run_poll_cycle() -> None:
    """One cycle: load ST integrations from DB, poll each tenant."""
    async with AsyncSessionLocal() as session:
        repo = CompanyIntegrationRepository(session)
        integrations = await repo.get_all_servicetitan_integrations()
        logger.info(f"Found {len(integrations)} ST integration(s)")

        async with httpx.AsyncClient(timeout=60) as http:
            for integration in integrations:
                try:
                    await poll_tenant(integration, http, session)
                except Exception as e:
                    logger.error(
                        f"Error polling tenant {integration.st_tenant_id}: {e}",
                        exc_info=True,
                    )

        await session.commit()


async def _safe_export(export_fn, from_token, feed_name, tenant_id, seed_only=False):
    """Run an export call, returning ([], None) on failure so gather never crashes."""
    try:
        return await export_fn(from_token=from_token, seed_only=seed_only)
    except Exception as e:
        logger.error(f"Tenant {tenant_id}: error exporting {feed_name}: {e}", exc_info=True)
        return [], None


async def _safe_post(http_client, url, payload, headers, label, tenant_id):
    """POST to a webhook endpoint, logging errors instead of raising."""
    try:
        resp = await http_client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        logger.info(f"Tenant {tenant_id}: {label} webhook → {resp.json()}")
    except Exception as e:
        logger.error(f"Tenant {tenant_id}: error posting {label} webhook: {e}", exc_info=True)


async def poll_tenant(integration, http_client: httpx.AsyncClient, session) -> None:
    """Poll one tenant via Export APIs, POST results to webhook endpoints."""
    tenant_id = integration.st_tenant_id
    logger.info(f"Polling ST tenant {tenant_id}")

    # 1. Decrypt credentials
    client_secret = (
        decrypt_api_key(integration.st_client_secret_encrypted)
        if integration.st_client_secret_encrypted
        else None
    )
    if not client_secret:
        logger.warning(f"No client_secret for tenant {tenant_id}, skipping")
        return

    # 2. Load persisted continueFrom tokens from extra_metadata
    meta = dict(integration.extra_metadata or {})
    calls_token = meta.get("st_calls_token")
    customers_token = meta.get("st_customers_token")
    customer_contacts_token = meta.get("st_customer_contacts_token")
    leads_token = meta.get("st_leads_token")
    bookings_token = meta.get("st_bookings_token")

    # 3. Create ST client
    st_client = ServiceTitanClient(
        tenant_id=tenant_id,
        client_id=integration.st_client_id,
        client_secret=client_secret,
    )

    headers = {"X-Worker-Secret": WORKER_SECRET}

    # 4. First-run detection: if ANY token is missing, this feed has never been
    #    polled before. Use seed_only mode to fast-forward to the latest
    #    continueFrom token without ingesting the entire historical backlog.
    is_seeding = not all([calls_token, customers_token, customer_contacts_token,
                          leads_token, bookings_token])
    if is_seeding:
        logger.info(
            f"Tenant {tenant_id}: first run detected — seeding tokens "
            f"(fast-forwarding to current position, no data will be ingested)"
        )

    # 5. Export all 5 feeds in parallel — they are independent API calls
    (
        calls_result,
        customers_result,
        customer_contacts_result,
        leads_result,
        bookings_result,
    ) = await asyncio.gather(
        _safe_export(st_client.export_calls, calls_token, "calls", tenant_id, seed_only=not calls_token),
        _safe_export(st_client.export_customers, customers_token, "customers", tenant_id, seed_only=not customers_token),
        _safe_export(st_client.export_customer_contacts, customer_contacts_token, "customer_contacts", tenant_id, seed_only=not customer_contacts_token),
        _safe_export(st_client.export_leads, leads_token, "leads", tenant_id, seed_only=not leads_token),
        _safe_export(st_client.export_bookings, bookings_token, "bookings", tenant_id, seed_only=not bookings_token),
    )

    calls, new_calls_token = calls_result
    customers, new_customers_token = customers_result
    customer_contacts, new_cc_token = customer_contacts_result
    leads, new_leads_token = leads_result
    bookings, new_bookings_token = bookings_result

    logger.info(
        f"Tenant {tenant_id}: exported {len(calls)} call(s), "
        f"{len(customers)} customer(s), {len(customer_contacts)} contact(s), "
        f"{len(leads)} lead(s), {len(bookings)} booking(s)"
    )

    # 6. POST results to webhook endpoints in parallel (skip if seeding)
    webhook_tasks = []

    if calls:
        webhook_tasks.append(
            _safe_post(
                http_client, f"{API_URL}/api/v1/webhooks/servicetitan/calls",
                {"tenant_id": tenant_id, "calls": calls},
                headers, "calls", tenant_id,
            )
        )

    if customers or customer_contacts or leads or bookings:
        webhook_tasks.append(
            _safe_post(
                http_client, f"{API_URL}/api/v1/webhooks/servicetitan/crm",
                {
                    "tenant_id": tenant_id,
                    "customers": customers,
                    "customer_contacts": customer_contacts,
                    "leads": leads,
                    "bookings": bookings,
                },
                headers, "crm", tenant_id,
            )
        )

    if webhook_tasks:
        await asyncio.gather(*webhook_tasks)

    # 7. Update tokens (only if export succeeded — _safe_export returns [] with old token on failure)
    if new_calls_token:
        calls_token = new_calls_token
    if new_customers_token:
        customers_token = new_customers_token
    if new_cc_token:
        customer_contacts_token = new_cc_token
    if new_leads_token:
        leads_token = new_leads_token
    if new_bookings_token:
        bookings_token = new_bookings_token

    # 8. Persist continueFrom tokens in extra_metadata
    integration.extra_metadata = {
        **meta,
        "st_calls_token": calls_token,
        "st_customers_token": customers_token,
        "st_customer_contacts_token": customer_contacts_token,
        "st_leads_token": leads_token,
        "st_bookings_token": bookings_token,
    }


if __name__ == "__main__":
    asyncio.run(main())
