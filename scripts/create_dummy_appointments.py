#!/usr/bin/env python3
"""
Script to create dummy appointments data linked to calls for testing.

Creates appointments that:
- Link to existing calls via interaction_id
- Have objections stored directly in appointments.objections
- Have assigned_rep_id set to Sales Reps
- Match the structure needed for the sales rep dashboard endpoint

Usage:
    python scripts/create_dummy_appointments.py --company-id <UUID> --count 10
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import UUID
import random

# Add parent directory to path to import app modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# CRITICAL: Load .env file and set DATABASE_URL BEFORE importing any app modules
original_cwd = os.getcwd()
os.chdir(backend_dir)

env_path = backend_dir / ".env"
if env_path.exists():
    print(f"Loading .env from: {env_path}")
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value
                if key == "DATABASE_URL":
                    if "postgres" in value.lower():
                        print(f"✓ DATABASE_URL set to PostgreSQL")
                    else:
                        print(f"⚠ DATABASE_URL is SQLite")
else:
    print(f"Warning: .env file not found at {env_path}")

from dotenv import load_dotenv
load_dotenv(env_path, override=True) if env_path.exists() else None

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Import all models
import app.infrastructure.database.models  # noqa: F401
from app.infrastructure.database.models import (
    AppointmentORM,
    CallORM,
    CallAnalysisORM,
    LeadORM,
    ContactCardORM,
    UserORM,
    CompanyORM,
)
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM  # noqa: F401
from app.infrastructure.database.session import AsyncSessionLocal
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)

# Sample objections for dummy data
SAMPLE_OBJECTIONS = [
    ["price", "Price/Fee Concerns"],
    ["timing", "Scheduling Conflict"],
    ["authority", "Decision Maker Not Available"],
    ["need", "Customer Needs Time to Decide"],
    ["competitor", "Considering Other Options"],
    ["other", "Communication Issues"],
    ["other", "Phone Connection Issues"],
    ["other", "Inefficient Agent Communication"],
]

# Sample summaries
SAMPLE_SUMMARIES = [
    "Customer called to inquire about pricing for roof replacement. Discussed options and scheduled follow-up.",
    "Initial consultation call. Customer expressed interest but needs to discuss with spouse before booking.",
    "Follow-up call regarding previous estimate. Customer has questions about warranty and timeline.",
    "Customer called to reschedule appointment due to scheduling conflict. New time agreed upon.",
    "Sales call discussing service options. Customer requested more information via email.",
]


async def create_dummy_appointments(
    company_id: UUID,
    count: int = 10,
    dry_run: bool = False,
) -> None:
    """
    Create dummy appointments linked to calls with objections.
    
    Args:
        company_id: Company UUID
        count: Number of appointments to create
        dry_run: If True, preview changes without writing to DB
    """
    async with AsyncSessionLocal() as session:
        try:
            logger.info(f"Starting to create {count} dummy appointments for company {company_id}")
            
            # Verify company exists
            company_result = await session.execute(
                select(CompanyORM).where(CompanyORM.id == company_id)
            )
            company = company_result.scalar_one_or_none()
            if not company:
                logger.error(f"Company {company_id} not found")
                return
            logger.info(f"✓ Company found: {company.name if hasattr(company, 'name') else company_id}")
            
            # Get existing calls with analyses that have objections
            # Also include calls without analyses - we'll create appointments with objections anyway
            calls_query = (
                select(CallORM, CallAnalysisORM, LeadORM, ContactCardORM)
                .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
                .outerjoin(LeadORM, CallORM.lead_id == LeadORM.id)
                .outerjoin(ContactCardORM, CallORM.contact_card_id == ContactCardORM.id)
                .where(
                    CallORM.company_id == company_id,
                    CallORM.lead_id.isnot(None),  # Must have a lead
                    CallORM.contact_card_id.isnot(None),  # Must have a contact
                )
                .limit(count * 3)  # Get more calls than needed
            )
            
            calls_result = await session.execute(calls_query)
            calls_data = calls_result.all()
            logger.info(f"Found {len(calls_data)} calls with leads and contacts")
            
            if not calls_data:
                logger.warning("No calls with leads/contacts found. Trying to get any calls...")
                # Get any calls for the company
                any_calls_query = (
                    select(CallORM, LeadORM, ContactCardORM)
                    .outerjoin(LeadORM, CallORM.lead_id == LeadORM.id)
                    .outerjoin(ContactCardORM, CallORM.contact_card_id == ContactCardORM.id)
                    .where(CallORM.company_id == company_id)
                    .limit(count * 2)
                )
                any_calls_result = await session.execute(any_calls_query)
                calls_data = [(call, None, lead, contact) for call, lead, contact in any_calls_result.all()]
                logger.info(f"Found {len(calls_data)} total calls (some may be missing leads/contacts)")
            
            if not calls_data:
                logger.error("No calls found for this company. Cannot create appointments.")
                logger.error("Please ensure there are calls in the database for this company.")
                return
            
            # Get Sales Reps for this company
            sales_reps_query = select(UserORM).where(
                UserORM.company_id == company_id,
                UserORM.role == 'sales_rep',
                UserORM.is_active == True,
            )
            sales_reps_result = await session.execute(sales_reps_query)
            sales_reps = list(sales_reps_result.scalars().all())
            
            if not sales_reps:
                logger.warning("No Sales Reps found. Creating appointments without assigned_rep_id.")
            
            # Check which calls already have appointments
            existing_interaction_ids = set()
            if calls_data:
                call_ids = [call.id for call, _, _, _ in calls_data if call]
                logger.info(f"Checking for existing appointments for {len(call_ids)} calls...")
                existing_appts_query = select(AppointmentORM.interaction_id).where(
                    AppointmentORM.interaction_id.in_(call_ids),
                    AppointmentORM.company_id == company_id,
                )
                existing_result = await session.execute(existing_appts_query)
                existing_interaction_ids = {id for id in existing_result.scalars().all() if id}
                logger.info(f"Found {len(existing_interaction_ids)} calls that already have appointments")
            
            created_count = 0
            skipped_count = 0
            error_count = 0
            
            for call, analysis, lead, contact_card in calls_data:
                if created_count >= count:
                    break
                
                if not call:
                    continue
                
                # Skip if appointment already exists for this call
                if call.id in existing_interaction_ids:
                    skipped_count += 1
                    continue
                
                # Skip if no lead or contact_card
                if not lead or not contact_card:
                    continue
                
                # Get objections from analysis if available, otherwise use sample
                if analysis and analysis.objections and len(analysis.objections) > 0:
                    objections = analysis.objections[:3]  # Take first 3 objections
                else:
                    # Use sample objections - create multiple for variety
                    num_objections = random.randint(1, 3)
                    selected_objections = random.sample(SAMPLE_OBJECTIONS, min(num_objections, len(SAMPLE_OBJECTIONS)))
                    objections = [obj[1] for obj in selected_objections]  # Get objection text
                
                # Random Sales Rep
                assigned_rep_id = None
                if sales_reps:
                    assigned_rep_id = random.choice(sales_reps).id
                
                # Create scheduled time (random time in the past 30 days to match date range)
                scheduled_start = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(0, 30),
                    hours=random.randint(0, 23),
                    minutes=random.choice([0, 15, 30, 45]),
                )
                scheduled_end = scheduled_start + timedelta(hours=1)
                
                # Create appointment with all fields
                appointment = AppointmentORM(
                    company_id=company_id,
                    lead_id=lead.id,
                    contact_card_id=contact_card.id,
                    scheduled_start=scheduled_start,
                    scheduled_end=scheduled_end,
                    location_address=contact_card.address or "123 Main St",
                    assigned_rep_id=assigned_rep_id,
                    interaction_id=call.id,  # Link to call
                    audio_url=call.audio_url,  # Copy audio_url from call
                    transcript=call.transcript,
                    duration_seconds=call.duration_seconds,
                    summary=analysis.summary if analysis else random.choice(SAMPLE_SUMMARIES),
                    objections=objections,  # Store objections directly
                    objection_texts=objections,  # Same as objections for now
                    objections_total_count=len(objections),
                    qualification_status=analysis.qualification_status if analysis else "warm",
                    booking_status=analysis.booking_status if analysis else "not_booked",
                    handled_by_user_id=call.handled_by_user_id,  # Copy from call
                )
                
                if not dry_run:
                    try:
                        session.add(appointment)
                        await session.flush()
                        logger.info(
                            f"✓ Created appointment {appointment.id} linked to call {call.id} "
                            f"with {len(objections)} objections: {objections[:2]}..."
                        )
                        created_count += 1
                    except Exception as e:
                        error_count += 1
                        logger.error(f"✗ Error creating appointment for call {call.id}: {e}")
                        await session.rollback()
                        # Continue with next call
                        continue
                else:
                    logger.info(
                        f"[DRY RUN] Would create appointment linked to call {call.id} "
                        f"with objections: {objections}, assigned_rep: {assigned_rep_id}"
                    )
                    created_count += 1
                
                existing_interaction_ids.add(call.id)  # Track to avoid duplicates
            
            if not dry_run:
                try:
                    await session.commit()
                    logger.info("=" * 60)
                    logger.info(f"✓ SUCCESS: Created {created_count} appointments")
                    logger.info(f"  Skipped: {skipped_count} (already exist)")
                    logger.info(f"  Errors: {error_count}")
                    logger.info("=" * 60)
                    
                    # Verify appointments were created
                    verify_query = select(func.count(AppointmentORM.id)).where(
                        AppointmentORM.company_id == company_id,
                        AppointmentORM.objections.isnot(None),
                        func.coalesce(func.array_length(AppointmentORM.objections, 1), 0) > 0,
                    )
                    verify_result = await session.execute(verify_query)
                    total_with_objections = verify_result.scalar() or 0
                    logger.info(f"✓ Verification: Found {total_with_objections} appointments with objections in database")
                    logger.info("=" * 60)
                except Exception as e:
                    await session.rollback()
                    logger.error(f"✗ Error committing appointments: {e}")
                    raise
            else:
                logger.info(f"[DRY RUN] Would create {created_count} appointments (would skip {skipped_count})")
                
        except Exception as e:
            await session.rollback()
            logger.error("=" * 60)
            logger.error(f"✗ ERROR creating dummy appointments: {e}")
            logger.error("=" * 60)
            import traceback
            traceback.print_exc()
            raise


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create dummy appointments linked to calls")
    parser.add_argument(
        "--company-id",
        type=str,
        required=False,
        default="6d40b509-82bc-4d21-9614-de91cc25dc1b",  # Default company from user's endpoint
        help="Company UUID (default: 6d40b509-82bc-4d21-9614-de91cc25dc1b)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,  # Create more appointments to ensure we have data
        help="Number of appointments to create (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to database",
    )
    
    args = parser.parse_args()
    
    setup_logging()
    
    try:
        company_id = UUID(args.company_id)
    except ValueError:
        logger.error(f"Invalid company_id: {args.company_id}")
        sys.exit(1)
    
    await create_dummy_appointments(
        company_id=company_id,
        count=args.count,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    asyncio.run(main())
