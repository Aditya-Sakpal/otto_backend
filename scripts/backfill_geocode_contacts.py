"""
Backfill geocoding for existing appointments.

Finds all appointments with a location_address but no latitude/longitude,
geocodes them via Google Maps API, and updates the database.

Usage:
    python scripts/backfill_geocode_contacts.py               # Run backfill
    python scripts/backfill_geocode_contacts.py --dry-run      # Preview only
    python scripts/backfill_geocode_contacts.py --batch-size 50  # Custom batch size
"""
import argparse
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.infrastructure.database.session import AsyncSessionLocal
import app.infrastructure.database.models  # noqa: F401 - register all ORM models
import app.infrastructure.database.models.company_integration  # noqa: F401 - needed for relationship resolution
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.integrations.google_geocoding import get_google_geocoding_client

logger = get_logger(__name__)


async def backfill(dry_run: bool = False, batch_size: int = 100):
    """Geocode all appointments that have location_address but no coordinates."""
    client = get_google_geocoding_client()

    async with AsyncSessionLocal() as session:
        stmt = (
            select(AppointmentORM)
            .where(AppointmentORM.location_address.isnot(None))
            .where(AppointmentORM.latitude.is_(None))
        )
        result = await session.execute(stmt)
        appointments = result.scalars().all()

        total = len(appointments)
        print(f"Found {total} appointments to geocode")

        if dry_run:
            for a in appointments[:10]:
                print(f"  [DRY RUN] Would geocode {a.id}: {a.location_address}")
            if total > 10:
                print(f"  ... and {total - 10} more")
            return

        success = 0
        failed = 0

        for i, appt in enumerate(appointments):
            result = await client.geocode(address=appt.location_address)

            if result:
                lat, lng = result
                stmt = (
                    update(AppointmentORM)
                    .where(AppointmentORM.id == appt.id)
                    .values(latitude=lat, longitude=lng)
                )
                await session.execute(stmt)
                success += 1
            else:
                failed += 1

            # Commit in batches
            if (i + 1) % batch_size == 0:
                await session.commit()
                print(f"  Progress: {i + 1}/{total} (success={success}, failed={failed})")

            # Rate limit: ~50 requests/sec max for Google Geocoding API
            await asyncio.sleep(0.05)

        await session.commit()
        print(f"Done. Total={total}, Success={success}, Failed={failed}")


def main():
    parser = argparse.ArgumentParser(description="Backfill geocoding for appointments")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--batch-size", type=int, default=100, help="Commit batch size")
    args = parser.parse_args()

    asyncio.run(backfill(dry_run=args.dry_run, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
