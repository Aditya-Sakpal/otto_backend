#!/usr/bin/env python3
"""
Script to backfill appointment audio_url from associated calls.

Finds all appointments with an interaction_id (linked to a call) but no audio_url,
and updates them with the audio_url from their associated call.

Usage:
    python scripts/backfill_appointment_audio_url.py --dry-run    # Preview changes
    python scripts/backfill_appointment_audio_url.py             # Run backfill
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path to import app modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# CRITICAL: Load .env file and set DATABASE_URL BEFORE importing any app modules
# The database engine in session.py is created at import time, so env vars must be set first
import os

# Change to backend directory to ensure .env is found
original_cwd = os.getcwd()
os.chdir(backend_dir)

# Read .env file directly and set DATABASE_URL before any imports
env_path = backend_dir / ".env"
if env_path.exists():
    print(f"Loading .env from: {env_path}")
    # Read .env file line by line
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Set environment variable
                os.environ[key] = value
                if key == "DATABASE_URL":
                    if "postgres" in value.lower():
                        print(f"✓ DATABASE_URL set to PostgreSQL")
                    else:
                        print(f"⚠ DATABASE_URL is SQLite")
else:
    print(f"Warning: .env file not found at {env_path}")
    print("Using environment variables or defaults")

# Now load dotenv as well (for any other env vars)
from dotenv import load_dotenv
load_dotenv(env_path, override=True) if env_path.exists() else None

from sqlalchemy import select

# Import all models to ensure relationships are properly initialized
import app.infrastructure.database.models  # noqa: F401 - register all ORM models
from app.infrastructure.database.models import (
    AppointmentORM,
    CallORM,
)
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM  # noqa: F401 - needed for relationship resolution
from app.infrastructure.database.session import AsyncSessionLocal
from app.core.config import settings
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def backfill_appointment_audio_url(dry_run: bool = False) -> None:
    """
    Backfill appointment audio_url from associated calls.

    Args:
        dry_run: If True, preview changes without writing to DB.
    """
    async with AsyncSessionLocal() as session:
        try:
            # First, get statistics
            total_appts = await session.execute(select(AppointmentORM))
            total_count = len(list(total_appts.scalars().all()))
            
            appts_with_interaction = await session.execute(
                select(AppointmentORM).where(AppointmentORM.interaction_id.isnot(None))
            )
            with_interaction_count = len(list(appts_with_interaction.scalars().all()))
            
            appts_with_audio = await session.execute(
                select(AppointmentORM).where(AppointmentORM.audio_url.isnot(None))
            )
            with_audio_count = len(list(appts_with_audio.scalars().all()))
            
            logger.info("=" * 60)
            logger.info("APPOINTMENT STATISTICS")
            logger.info(f"  Total appointments:           {total_count}")
            logger.info(f"  With interaction_id:          {with_interaction_count}")
            logger.info(f"  With audio_url:               {with_audio_count}")
            logger.info(f"  Missing audio_url:             {total_count - with_audio_count}")
            logger.info("=" * 60)
            
            # Find all appointments with interaction_id but no audio_url
            logger.info("Fetching appointments with interaction_id but no audio_url...")
            result = await session.execute(
                select(AppointmentORM)
                .where(AppointmentORM.interaction_id.isnot(None))
                .where(AppointmentORM.audio_url.is_(None))
            )
            appointments = list(result.scalars().all())
            logger.info(f"Found {len(appointments)} appointments to update (with interaction_id but no audio_url)")
            
            # Also find appointments without interaction_id - we'll try to find calls by lead_id
            logger.info("Checking for appointments without interaction_id...")
            appts_no_interaction = await session.execute(
                select(AppointmentORM)
                .where(AppointmentORM.interaction_id.is_(None))
                .where(AppointmentORM.audio_url.is_(None))
            )
            appointments_no_interaction = list(appts_no_interaction.scalars().all())
            logger.info(f"Found {len(appointments_no_interaction)} appointments without interaction_id (will try to match by lead_id)")

            if not appointments:
                logger.info("No appointments need updating. Nothing to do.")
                return

            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Process appointments with interaction_id
            for appointment in appointments:
                try:
                    # Get the associated call
                    call_result = await session.execute(
                        select(CallORM).where(CallORM.id == appointment.interaction_id)
                    )
                    call = call_result.scalar_one_or_none()

                    if not call:
                        logger.warning(
                            f"Appointment {appointment.id} has interaction_id {appointment.interaction_id} "
                            f"but call not found. Skipping."
                        )
                        skipped_count += 1
                        continue

                    if not call.audio_url:
                        logger.debug(
                            f"Appointment {appointment.id} linked to call {call.id} "
                            f"but call has no audio_url. Skipping."
                        )
                        skipped_count += 1
                        continue

                    # Update appointment with call's audio_url
                    if dry_run:
                        logger.info(
                            f"DRY RUN — would update appointment {appointment.id} "
                            f"with audio_url: {call.audio_url} "
                            f"(from call {call.id})"
                        )
                    else:
                        appointment.audio_url = call.audio_url
                        # updated_at will be set automatically by SQLAlchemy's onupdate
                        logger.info(
                            f"Updated appointment {appointment.id} "
                            f"with audio_url: {call.audio_url} "
                            f"(from call {call.id})"
                        )
                    updated_count += 1

                except Exception as e:
                    logger.error(
                        f"Error processing appointment {appointment.id}: {e}",
                        exc_info=True
                    )
                    error_count += 1
            
            # Process appointments without interaction_id - try to find calls by lead_id
            for appointment in appointments_no_interaction:
                try:
                    # Try to find a call for this appointment's lead_id that has audio_url
                    call_result = await session.execute(
                        select(CallORM)
                        .where(CallORM.lead_id == appointment.lead_id)
                        .where(CallORM.audio_url.isnot(None))
                        .order_by(CallORM.created_at.desc())
                        .limit(1)
                    )
                    call = call_result.scalar_one_or_none()
                    
                    if call:
                        # Found a call with audio_url for this lead
                        if dry_run:
                            logger.info(
                                f"DRY RUN — would update appointment {appointment.id} "
                                f"with audio_url: {call.audio_url} "
                                f"(from call {call.id} via lead_id {appointment.lead_id})"
                            )
                        else:
                            appointment.audio_url = call.audio_url
                            appointment.interaction_id = call.id  # Also set interaction_id
                            logger.info(
                                f"Updated appointment {appointment.id} "
                                f"with audio_url: {call.audio_url} "
                                f"(from call {call.id} via lead_id {appointment.lead_id})"
                            )
                        updated_count += 1
                    else:
                        logger.debug(
                            f"Appointment {appointment.id} (lead_id: {appointment.lead_id}) "
                            f"has no associated call with audio_url. Skipping."
                        )
                        skipped_count += 1
                        
                except Exception as e:
                    logger.error(
                        f"Error processing appointment {appointment.id}: {e}",
                        exc_info=True
                    )
                    error_count += 1

            # Commit all changes
            if not dry_run:
                await session.commit()
                logger.info("All changes committed successfully")

            # Summary
            logger.info("=" * 60)
            logger.info("SUMMARY")
            logger.info(f"  Appointments found:          {len(appointments)}")
            logger.info(f"  Appointments updated:        {updated_count}")
            logger.info(f"  Appointments skipped:        {skipped_count}")
            logger.info(f"  Errors:                      {error_count}")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during backfill: {e}", exc_info=True)
            await session.rollback()
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill appointment audio_url from associated calls"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    args = parser.parse_args()

    setup_logging()
    logger.info("Starting appointment audio_url backfill...")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    
    # Log database URL (masked for security)
    db_url = settings.DATABASE_URL
    if db_url:
        # Mask password in URL for logging
        if "@" in db_url:
            parts = db_url.split("@")
            if "://" in parts[0]:
                protocol_user = parts[0].split("://")
                if len(protocol_user) == 2:
                    protocol = protocol_user[0]
                    user_pass = protocol_user[1]
                    if ":" in user_pass:
                        user = user_pass.split(":")[0]
                        masked_url = f"{protocol}://{user}:***@{parts[1]}"
                    else:
                        masked_url = db_url
                else:
                    masked_url = db_url
            else:
                masked_url = db_url
        else:
            masked_url = db_url
        logger.info(f"Database URL: {masked_url}")
    else:
        logger.warning("DATABASE_URL not set! Using default SQLite.")

    try:
        asyncio.run(backfill_appointment_audio_url(dry_run=args.dry_run))
        logger.info("Backfill completed successfully!")
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
