#!/usr/bin/env python3
"""
Script to backfill appointments from booked leads and round-robin assign sales reps.

Booked leads (status = "qualified_booked") can get out of sync with appointments.
This script:
1. Finds all booked leads (all companies)
2. Creates missing appointment rows
3. Round-robin assigns ALL appointments for the target company to sales reps

Usage:
    python scripts/backfill_booked_lead_appointments.py --dry-run
    python scripts/backfill_booked_lead_appointments.py
"""
import asyncio
import argparse
import sys
from pathlib import Path
from uuid import UUID, uuid4

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

# Import all models to ensure relationships are properly initialized
from app.infrastructure.database.models import (
    CompanyORM,
    UserORM,
    ContactCardORM,
    LeadORM,
    CallORM,
    AppointmentORM,
    CallAnalysisORM,
    InvitationORM,
    PendingActionORM,
    CallProcessingJobORM,
    AskOttoConversationORM,
    AskOttoMessageORM,
    InsightJobORM,
)
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM

from app.infrastructure.database.session import AsyncSessionLocal
from app.domain.enums import LeadStatus, AppointmentOutcome, UserRole
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)

TARGET_COMPANY_ID = UUID("6d40b509-82bc-4d21-9614-de91cc25dc1b")


def build_location_address(contact: ContactCardORM) -> str | None:
    """Build a location address string from contact card fields."""
    parts = [
        contact.address,
        contact.city,
        contact.state,
        contact.postal_code,
    ]
    filtered = [p for p in parts if p]
    return ", ".join(filtered) if filtered else None


async def backfill_appointments(dry_run: bool = False) -> None:
    """
    Backfill appointments for booked leads and assign sales reps.

    Args:
        dry_run: If True, preview changes without writing to DB.
    """
    async with AsyncSessionLocal() as session:
        try:
            # ── Step 1: Get all booked leads (all companies) ──
            logger.info("Fetching all booked leads...")
            result = await session.execute(
                select(LeadORM).where(LeadORM.status == LeadStatus.QUALIFIED_BOOKED.value)
            )
            booked_leads = list(result.scalars().all())
            logger.info(f"Found {len(booked_leads)} booked leads")

            if not booked_leads:
                logger.info("No booked leads found. Nothing to do.")
                return

            # ── Step 2 & 3 & 4: Check existing appointments, create missing ──
            created_count = 0
            skipped_count = 0

            for lead in booked_leads:
                # Check if appointment already exists for this lead
                appt_result = await session.execute(
                    select(AppointmentORM).where(AppointmentORM.lead_id == lead.id)
                )
                existing = appt_result.scalars().first()

                if existing:
                    skipped_count += 1
                    logger.info(
                        f"SKIP lead {lead.id} — appointment {existing.id} already exists"
                    )
                    continue

                # Get contact card for address
                contact_result = await session.execute(
                    select(ContactCardORM).where(ContactCardORM.id == lead.contact_card_id)
                )
                contact = contact_result.scalars().first()
                location_address = build_location_address(contact) if contact else None

                if dry_run:
                    logger.info(
                        f"DRY RUN — would create appointment for lead {lead.id} "
                        f"(company: {lead.company_id}, address: {location_address})"
                    )
                else:
                    appointment = AppointmentORM(
                        id=uuid4(),
                        company_id=lead.company_id,
                        lead_id=lead.id,
                        contact_card_id=lead.contact_card_id,
                        scheduled_start=lead.created_at,
                        location_address=location_address,
                        outcome=AppointmentOutcome.PENDING.value,
                        extra_metadata={"source": "backfill_script"},
                    )
                    session.add(appointment)
                    logger.info(
                        f"CREATED appointment {appointment.id} for lead {lead.id} "
                        f"(company: {lead.company_id})"
                    )

                created_count += 1

            # Flush so new appointments are visible in subsequent queries
            if not dry_run:
                await session.flush()

            # ── Step 5: Get sales reps for target company ──
            logger.info(
                f"Fetching sales reps for company {TARGET_COMPANY_ID}..."
            )
            reps_result = await session.execute(
                select(UserORM).where(
                    UserORM.role == UserRole.SALES_REP.value,
                    UserORM.company_id == TARGET_COMPANY_ID,
                )
            )
            sales_reps = list(reps_result.scalars().all())
            logger.info(f"Found {len(sales_reps)} sales reps")

            if not sales_reps:
                logger.warning(
                    "No sales reps found for target company — skipping assignment"
                )
            else:
                # ── Step 6: Round-robin assign ALL appointments for target company ──
                appts_result = await session.execute(
                    select(AppointmentORM)
                    .where(AppointmentORM.company_id == TARGET_COMPANY_ID)
                    .order_by(AppointmentORM.scheduled_start.asc())
                )
                company_appointments = list(appts_result.scalars().all())
                logger.info(
                    f"Found {len(company_appointments)} appointments for target company"
                )

                assigned_count = 0
                for i, appt in enumerate(company_appointments):
                    rep = sales_reps[i % len(sales_reps)]
                    old_rep = appt.assigned_rep_id

                    if dry_run:
                        logger.info(
                            f"DRY RUN — would assign appointment {appt.id} "
                            f"to rep {rep.first_name} {rep.last_name} ({rep.id}) "
                            f"[was: {old_rep}]"
                        )
                    else:
                        appt.assigned_rep_id = rep.id
                        logger.info(
                            f"ASSIGNED appointment {appt.id} "
                            f"to rep {rep.first_name} {rep.last_name} ({rep.id}) "
                            f"[was: {old_rep}]"
                        )
                    assigned_count += 1

            # Commit all changes
            if not dry_run:
                await session.commit()
                logger.info("All changes committed successfully")

            # ── Summary ──
            logger.info("=" * 60)
            logger.info("SUMMARY")
            logger.info(f"  Booked leads found:        {len(booked_leads)}")
            logger.info(f"  Appointments created:       {created_count}")
            logger.info(f"  Appointments skipped:       {skipped_count}")
            if sales_reps:
                logger.info(f"  Sales reps:                 {len(sales_reps)}")
                logger.info(f"  Appointments assigned:      {assigned_count}")
            if dry_run:
                logger.info("  Mode:                       DRY RUN (no changes written)")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during backfill: {e}")
            await session.rollback()
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill appointments from booked leads and assign sales reps"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database",
    )

    args = parser.parse_args()

    setup_logging()

    try:
        asyncio.run(backfill_appointments(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
