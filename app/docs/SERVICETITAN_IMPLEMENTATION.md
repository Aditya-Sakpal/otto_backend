# ServiceTitan Integration — Implementation Plan

## Context

ServiceTitan is a CRM + field-service platform used by home service companies. Unlike GHL (webhook-push) and CTM (webhook-push), ServiceTitan requires **polling** — a separate worker process fetches new data every 30s and POSTs it to our FastAPI webhook endpoints for processing.

**Auth model:** OAuth2 `client_credentials` grant. Each tenant needs: `tenant_id`, `client_id`, `client_secret`, `app_key`. Tokens expire (~1hr) and must be refreshed.

**Architecture:**
```
[ST APIs] <--polls-- [Worker Process (standalone)]
                            |
                       POST /webhooks/servicetitan/*
                            |
                            v
                      [FastAPI Server]
                            |
              +-------------+-------------+
              |             |             |
        ContactCard       Lead       Call → Shunya
```

---

## Implementation Order

| Phase | What | Files |
|-------|------|-------|
| 1 | SQL migration — add ST columns to `company_integrations` | `migrations/add_servicetitan_columns.sql` |
| 2 | ORM + domain model updates | `models/company_integration.py` (both) |
| 3 | Repository — ST query methods | `repositories/company_integration.py` |
| 4 | ST API client — OAuth2 + REST | `integrations/servicetitan.py` (new) |
| 5 | ST service — data mapping + processing | `services/servicetitan_service.py` (new) |
| 6 | Webhook endpoints | `routes/v1/webhooks.py` |
| 7 | Onboarding — validation + complete | `routes/v1/onboarding.py`, `schemas/onboarding.py` |
| 8 | Config — env vars | `core/config.py` |
| 9 | Worker process | `workers/st_poller.py` (new) |

---

## Phase 1: SQL Migration

**New file:** `app/infrastructure/database/migrations/add_servicetitan_columns.sql`

```sql
-- Migration: Add ServiceTitan credential columns to company_integrations

ALTER TABLE company_integrations
  ADD COLUMN IF NOT EXISTS st_tenant_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_client_id VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_client_secret_encrypted VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_app_key VARCHAR NULL,
  ADD COLUMN IF NOT EXISTS st_env VARCHAR DEFAULT 'production' NULL;

CREATE INDEX IF NOT EXISTS ix_ci_st_tenant_id
  ON company_integrations (st_tenant_id) WHERE st_tenant_id IS NOT NULL;

COMMENT ON COLUMN company_integrations.st_tenant_id IS 'ServiceTitan tenant ID';
COMMENT ON COLUMN company_integrations.st_client_secret_encrypted IS 'Encrypted ST client_secret (AES-256)';
COMMENT ON COLUMN company_integrations.st_env IS 'ST environment: production or integration';
```

Also update `app/infrastructure/database/database_schema.sql` to include these columns in the canonical schema.

---

## Phase 2: ORM + Domain Model

**Modify:** `app/infrastructure/database/models/company_integration.py`

Add after the VoIP fields block (line 29):
```python
# ServiceTitan integration fields (all optional)
st_tenant_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
st_client_id: Mapped[str | None] = mapped_column(String, nullable=True)
st_client_secret_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
st_app_key: Mapped[str | None] = mapped_column(String, nullable=True)
st_env: Mapped[str | None] = mapped_column(String, nullable=True, default="production")
```

**Modify:** `app/domain/models/company_integration.py`

Add fields:
```python
st_tenant_id: Optional[str] = Field(None, description="ServiceTitan tenant ID")
st_client_id: Optional[str] = Field(None, description="ServiceTitan client ID")
st_client_secret_encrypted: Optional[str] = Field(None, description="Encrypted ST client secret")
st_app_key: Optional[str] = Field(None, description="ServiceTitan app key")
st_env: Optional[str] = Field("production", description="ST environment: production or integration")
```

---

## Phase 3: Repository Updates

**Modify:** `app/infrastructure/repositories/company_integration.py`

### New methods to add:

```python
async def get_all_servicetitan_integrations(self) -> list[CompanyIntegrationORM]:
    """Get all integrations with ST credentials configured (used by worker)."""
    result = await self.session.execute(
        select(CompanyIntegrationORM).where(
            CompanyIntegrationORM.st_tenant_id.isnot(None),
            CompanyIntegrationORM.st_tenant_id != "",
        )
    )
    return list(result.scalars().all())

async def get_company_id_by_st_tenant_id(self, st_tenant_id: str) -> UUID | None:
    """Map ST tenant_id → company_id (used by webhook)."""
    result = await self.session.execute(
        select(CompanyIntegrationORM).where(
            CompanyIntegrationORM.st_tenant_id == st_tenant_id
        )
    )
    orm_obj = result.scalar_one_or_none()
    return orm_obj.company_id if orm_obj else None

async def get_decrypted_st_credentials(self, company_id: UUID) -> dict | None:
    """Returns {tenant_id, client_id, client_secret (decrypted), app_key, env}."""
    integration = await self.get_by_company_id(company_id)
    if not integration or not integration.st_tenant_id:
        return None
    client_secret = decrypt_api_key(integration.st_client_secret_encrypted) if integration.st_client_secret_encrypted else None
    return {
        "tenant_id": integration.st_tenant_id,
        "client_id": integration.st_client_id,
        "client_secret": client_secret,
        "app_key": integration.st_app_key,
        "env": integration.st_env or "production",
    }
```

### Existing methods to update:

- `create()` — add params: `st_tenant_id`, `st_client_id`, `st_client_secret` (encrypted on write via `encrypt_api_key()`), `st_app_key`, `st_env`
- `update()` — same new params, encrypt `st_client_secret` if provided
- `upsert_company_integration()` — pass through new params
- `_to_domain()` — include ST fields in mapping

---

## Phase 4: ST API Client

**New file:** `app/infrastructure/integrations/servicetitan.py`

```python
class ServiceTitanClient:
    """OAuth2 client for ServiceTitan REST APIs."""

    PROD_AUTH = "https://auth.servicetitan.io/connect/token"
    PROD_API  = "https://api.servicetitan.io"
    INT_AUTH  = "https://auth-integration.servicetitan.io/connect/token"
    INT_API   = "https://api-integration.servicetitan.io"

    def __init__(self, tenant_id, client_id, client_secret, app_key, env="production"):
        ...
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
```

### Key methods:

| Method | ST Endpoint | Purpose |
|--------|------------|---------|
| `_ensure_token()` | `POST /connect/token` | OAuth2 client_credentials, caches token until 60s before expiry |
| `_get(path, params)` | Generic GET | Authenticated request with `Authorization: Bearer` + `ST-App-Key` headers |
| `_get_paginated(path, params)` | Generic | Auto-pages using `hasMore` + `page` params, `pageSize=50` |
| `get_customers(modified_on_or_after)` | `GET /crm/v2/tenant/{tid}/customers` | Fetch customers modified since timestamp |
| `get_leads(modified_on_or_after)` | `GET /crm/v2/tenant/{tid}/leads` | Fetch leads |
| `get_customer(id)` | `GET /crm/v2/tenant/{tid}/customers/{id}` | Single customer (for hydration) |
| `get_lead(id)` | `GET /crm/v2/tenant/{tid}/leads/{id}` | Single lead (for hydration) |
| `get_calls(created_on_or_after)` | `GET /telecom/v2/tenant/{tid}/calls` | Fetch calls |
| `get_jobs(modified_on_or_after)` | `GET /jpm/v2/tenant/{tid}/jobs` | Fetch jobs/appointments |
| `verify_credentials()` | Token + lightweight call | Validates creds during onboarding |

**Reference:** existing `new_customer.py` in repo root shows the exact auth + API pattern.

---

## Phase 5: ST Service

**New file:** `app/services/servicetitan_service.py`

Follows CTM/GHL service patterns.

```python
class ServiceTitanService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.call_repo = CallRepository(session)
        self.contact_repo = ContactRepository(session)
        self.lead_repo = LeadRepository(session)
        self.appointment_repo = AppointmentRepository(session)
        self.pending_action_repo = PendingActionRepository(session)
```

### Methods:

**`process_calls_webhook(payload, company_id)`** — Batch call processing
- Iterates `payload["calls"]`, calls `_process_single_call()` per item
- Returns `{processed, skipped, errors}`

**`_process_single_call(st_call, company_id)`**
1. Dedup by `extra_metadata.st_call_id`
2. Extract phone from `st_call.customer.phoneNumber` or `from`
3. `find_or_create_by_phone()` → ContactCard
4. Detect missed: `type in ("missed", "abandoned")`
5. Upload recording to S3 if `recordingUrl` present (skip for missed)
6. Create `Call` record with `call_type=MISSED_CALL` or `CSR_CALL`
7. If missed → create `PendingAction(action_type="call_back", source="manual")`
8. If recording → `call_service.trigger_analysis(call.id)`

**`process_crm_webhook(payload, company_id)`** — Batch CRM processing
- Processes `customers[]` → ContactCards
- Processes `leads[]` → Leads
- Processes `jobs[]` → Appointments
- Returns `{contacts_upserted, leads_upserted, appointments_upserted, errors}`

**`_upsert_contact_from_customer(st_customer, company_id)`**
- Extract phone from `contacts[]` array (type=Phone/MobilePhone) or top-level fields
- `find_or_create_by_phone()`, update address fields, store `st_customer_id` in extra_metadata

**`_upsert_lead(st_lead, company_id)`**
- Resolve ContactCard via `st_customer_id` in extra_metadata
- `find_or_create` Lead, map ST lead status → `LeadStatus` enum
- Store `st_lead_id` in extra_metadata

**`_upsert_appointment(st_job, company_id)`**
- Resolve ContactCard + Lead via customer linkage
- Create/update Appointment with `scheduled_start`, `location_address`, etc.
- Map ST job status → `AppointmentOutcome` enum
- Store `st_job_id` in extra_metadata

---

## Data Mapping

### ST Customer → ContactCard

| ST Field | Otto Field |
|----------|-----------|
| `id` | `extra_metadata.st_customer_id` |
| `name` | `first_name` + `last_name` (split on first space) |
| `contacts[type=Phone].value` | `primary_phone` |
| `contacts[type=Email].value` | `email` |
| `address.street` | `address` |
| `address.city` | `city` |
| `address.state` | `state` |
| `address.zip` | `postal_code` |

### ST Lead Status → LeadStatus

| ST Status | Otto LeadStatus |
|-----------|----------------|
| `open` / `new` | `NEW` |
| `pending` | `WARM` |
| `active` | `HOT` |
| `booked` | `QUALIFIED_BOOKED` |
| `won` | `CLOSED_WON` |
| `lost` | `CLOSED_LOST` |
| `dismissed` | `ABANDONED` |
| `expired` | `DORMANT` |

### ST Call → Call

| ST Field | Otto Field |
|----------|-----------|
| `id` | `extra_metadata.st_call_id` (dedup key) |
| `customer.phoneNumber` | `phone_number` |
| `duration` | `duration_seconds` |
| `recordingUrl` | `audio_url` (after S3 upload) |
| `type=missed/abandoned` | `missed_call=True`, `call_type=MISSED_CALL` |
| `type=other` | `call_type=CSR_CALL` |
| `direction` | `extra_metadata.st_direction` |

### ST Job → Appointment

| ST Status | Otto AppointmentOutcome |
|-----------|------------------------|
| `scheduled` / `in_progress` / `hold` | `PENDING` |
| `completed` | `WON` |
| `canceled` | `LOST` |

---

## Phase 6: Webhook Endpoints

**Modify:** `app/routes/v1/webhooks.py`

Two new endpoints, authenticated via `X-Worker-Secret` header:

### `POST /webhooks/servicetitan/calls`

```python
# Payload: { "tenant_id": "...", "calls": [...], "poll_timestamp": "..." }
# Flow:
#   1. _verify_worker_secret(x_worker_secret)
#   2. Lookup company_id via integration_repo.get_company_id_by_st_tenant_id(tenant_id)
#   3. ServiceTitanService(db).process_calls_webhook(payload, company_id)
#   4. Return { "status": "success", "processed": N, ... }
```

### `POST /webhooks/servicetitan/crm`

```python
# Payload: { "tenant_id": "...", "customers": [...], "leads": [...], "jobs": [...], "poll_timestamp": "..." }
# Flow:
#   1. _verify_worker_secret(x_worker_secret)
#   2. Lookup company_id
#   3. ServiceTitanService(db).process_crm_webhook(payload, company_id)
#   4. Return { "status": "success", "contacts_upserted": N, ... }
```

### Worker auth helper:
```python
def _verify_worker_secret(x_worker_secret: str | None):
    expected = settings.ST_WORKER_SECRET
    if expected and x_worker_secret != expected:
        raise HTTPException(401, "Invalid worker secret")
```

---

## Phase 7: Onboarding

**Modify:** `app/domain/schemas/onboarding.py`

Add schemas:
```python
class ValidateServiceTitanRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    app_key: str
    env: str = "production"

class ValidateServiceTitanResponse(BaseModel):
    tenant_id: str
    status: str
```

**Modify:** `app/routes/v1/onboarding.py`

1. Add `POST /onboarding/validate-servicetitan` — Instantiates `ServiceTitanClient`, calls `verify_credentials()`, returns tenant info. Follows exact pattern of `validate_ghl` / `validate_ctm`.

2. Update `complete_onboarding` — Add Form params:
```python
st_tenant_id: str | None = Form(None),
st_client_id: str | None = Form(None),
st_client_secret: str | None = Form(None),
st_app_key: str | None = Form(None),
st_env: str | None = Form(None),
```
Pass to `company_service.create_company_integration()`.

**Modify:** `app/services/company_service.py` — Accept and pass through ST params in `create_company_integration()`.

---

## Phase 8: Config

**Modify:** `app/core/config.py`

```python
# ServiceTitan Worker
ST_WORKER_SECRET: str = Field(
    default=os.getenv("ST_WORKER_SECRET", ""),
    description="Shared secret for ST worker → webhook auth"
)
```

**Env vars for worker process (read directly via `os.getenv`):**
- `ST_POLL_INTERVAL` — seconds between cycles (default: 30)
- `ST_INITIAL_LOOKBACK_HOURS` — on first run, look back N hours (default: 24)
- `API_URL` — FastAPI server base URL
- `ST_WORKER_SECRET` — must match server config

---

## Phase 9: Worker Process

**New file:** `workers/__init__.py` (empty)
**New file:** `workers/st_poller.py`

Run: `python -m workers.st_poller`

### Architecture:
```python
async def main():
    """Infinite loop: poll all tenants, sleep, repeat."""
    while True:
        await run_poll_cycle()
        await asyncio.sleep(POLL_INTERVAL)

async def run_poll_cycle():
    """One cycle: load ST integrations from DB, poll each tenant."""
    async with AsyncSessionLocal() as session:
        repo = CompanyIntegrationRepository(session)
        integrations = await repo.get_all_servicetitan_integrations()
        async with httpx.AsyncClient() as http:
            for integration in integrations:
                await poll_tenant(integration, http)
        await session.commit()  # saves updated last_poll timestamps

async def poll_tenant(integration, http_client):
    """Poll one tenant: fetch calls + CRM data, POST to webhooks."""
    # 1. Decrypt credentials
    client_secret = decrypt_api_key(integration.st_client_secret_encrypted)
    last_poll = (integration.extra_metadata or {}).get("st_last_poll")

    # 2. Create ST client
    st_client = ServiceTitanClient(
        tenant_id=integration.st_tenant_id,
        client_id=integration.st_client_id,
        client_secret=client_secret,
        app_key=integration.st_app_key,
        env=integration.st_env or "production",
    )

    # 3. Determine since timestamp
    since = last_poll or (now - INITIAL_LOOKBACK_HOURS).isoformat()

    # 4. Fetch calls since last_poll
    calls = await st_client.get_calls(created_on_or_after=since)
    if calls:
        await http_client.post(
            f"{API_URL}/api/v1/webhooks/servicetitan/calls",
            json={"tenant_id": integration.st_tenant_id, "calls": calls, "poll_timestamp": now},
            headers={"X-Worker-Secret": WORKER_SECRET},
        )

    # 5. Fetch CRM data (customers, leads, jobs) since last_poll
    customers = await st_client.get_customers(modified_on_or_after=since)
    leads = await st_client.get_leads(modified_on_or_after=since)
    jobs = await st_client.get_jobs(modified_on_or_after=since)
    if customers or leads or jobs:
        await http_client.post(
            f"{API_URL}/api/v1/webhooks/servicetitan/crm",
            json={"tenant_id": integration.st_tenant_id, "customers": customers, "leads": leads, "jobs": jobs},
            headers={"X-Worker-Secret": WORKER_SECRET},
        )

    # 6. Update last_poll in extra_metadata
    integration.extra_metadata = {**(integration.extra_metadata or {}), "st_last_poll": now}
```

### Resilience:
- Each tenant polled independently — one failure doesn't block others
- Worker catches all exceptions per-tenant, logs, continues
- Last-poll stored in `extra_metadata.st_last_poll`; on first run, looks back `ST_INITIAL_LOOKBACK_HOURS`
- Token cached per-client, refreshes 60s before expiry

---

## File Summary

### New files (5):

| File | Description |
|------|-------------|
| `app/infrastructure/database/migrations/add_servicetitan_columns.sql` | SQL migration for ST columns |
| `app/infrastructure/integrations/servicetitan.py` | ST API client (OAuth2 + REST) |
| `app/services/servicetitan_service.py` | Business logic + data mapping |
| `workers/__init__.py` | Package init |
| `workers/st_poller.py` | Standalone polling worker |

### Modified files (8):

| File | Changes |
|------|---------|
| `app/infrastructure/database/models/company_integration.py` | Add 5 ST columns to ORM |
| `app/domain/models/company_integration.py` | Add 5 ST fields to domain model |
| `app/infrastructure/repositories/company_integration.py` | 3 new methods + update create/update/upsert/_to_domain |
| `app/infrastructure/database/database_schema.sql` | Add ST columns to canonical schema |
| `app/routes/v1/webhooks.py` | 2 new endpoints + worker auth helper |
| `app/routes/v1/onboarding.py` | validate-servicetitan endpoint + ST form params in complete |
| `app/domain/schemas/onboarding.py` | ST validation request/response schemas |
| `app/core/config.py` | `ST_WORKER_SECRET` setting |

---

## Verification

1. **Migration**: Run SQL migration, verify columns exist with `\d company_integrations`
2. **Onboarding**: POST `/onboarding/validate-servicetitan` with real ST credentials → should return `status: "valid"`
3. **Worker**: Run `python -m workers.st_poller` with a configured tenant → should poll and POST to webhooks
4. **Calls webhook**: POST sample ST call data to `/webhooks/servicetitan/calls` → verify Call + ContactCard created, analysis triggered if recording present
5. **CRM webhook**: POST sample ST customer/lead/job data to `/webhooks/servicetitan/crm` → verify ContactCard, Lead, Appointment created
6. **Missed calls**: POST ST call with `type: "missed"` → verify `missed_call=True`, `PendingAction` with `action_type="call_back"` created
7. **Dedup**: POST same call twice → second should be skipped
8. **Existing flows**: GHL and CTM webhooks should continue working unchanged
