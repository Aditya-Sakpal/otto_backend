#!/usr/bin/env python3
"""
Script to retroactively trigger analysis for existing calls in the database.

This script finds calls that have audio URLs but no analysis yet, and triggers
the analysis process for them.

Usage:
    python scripts/retroactive_call_analysis.py
    python scripts/retroactive_call_analysis.py --company-id <uuid>
    python scripts/retroactive_call_analysis.py --limit 100
    python scripts/retroactive_call_analysis.py --dry-run
"""
import asyncio
import argparse
import sys
from pathlib import Path
from uuid import UUID
from typing import Optional

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

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
# Import CompanyIntegrationORM separately since it's not in __init__.py
from app.infrastructure.database.models.company_integration import CompanyIntegrationORM

from app.infrastructure.database.session import AsyncSessionLocal
from app.services.call_service import CallService
from app.core.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def get_calls_needing_analysis(
    session: AsyncSession,
    company_id: Optional[UUID] = None,
    limit: Optional[int] = None,
    skip_processed: bool = True,
) -> list[CallORM]:
    """
    Get calls that need analysis.
    
    Args:
        session: Database session
        company_id: Optional company ID to filter by
        limit: Optional limit on number of calls to return
        skip_processed: If True, skip calls that already have analysis
        
    Returns:
        List of CallORM objects that need analysis
    """
    query = select(CallORM)
    
    # Filter by company if provided
    if company_id:
        query = query.where(CallORM.company_id == company_id)
    
    # Only get calls with audio URLs
    query = query.where(CallORM.audio_url.isnot(None))
    query = query.where(CallORM.audio_url != "")
    
    # Skip missed calls (they typically don't need analysis)
    query = query.where(CallORM.missed_call == False)
    
    # Skip calls that already have analysis if requested
    if skip_processed:
        # Use LEFT JOIN to find calls without analysis
        query = query.outerjoin(
            CallAnalysisORM, CallORM.id == CallAnalysisORM.call_id
        ).where(CallAnalysisORM.id.is_(None))
    
    # Order by created_at (oldest first)
    query = query.order_by(CallORM.created_at.asc())
    
    # Apply limit if provided
    if limit:
        query = query.limit(limit)
    
    result = await session.execute(query)
    calls = result.scalars().all()
    
    return list(calls)


async def process_calls(
    company_id: Optional[UUID] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    skip_processed: bool = True,
    batch_size: int = 10,
) -> None:
    """
    Process calls and trigger analysis.
    
    Args:
        company_id: Optional company ID to filter by
        limit: Optional limit on number of calls to process
        dry_run: If True, only show what would be processed without actually triggering
        skip_processed: If True, skip calls that already have analysis
        batch_size: Number of calls to process concurrently
    """
    async with AsyncSessionLocal() as session:
        try:
            # Get calls that need analysis
            logger.info("Fetching calls that need analysis...")
            calls = await get_calls_needing_analysis(
                session=session,
                company_id=company_id,
                limit=limit,
                skip_processed=skip_processed,
            )
            
            total_calls = len(calls)
            logger.info(f"Found {total_calls} calls that need analysis")
            
            if total_calls == 0:
                logger.info("No calls found that need analysis")
                return
            
            if dry_run:
                logger.info("DRY RUN MODE - No analysis will be triggered")
                for i, call in enumerate(calls, 1):
                    logger.info(
                        f"[{i}/{total_calls}] Would process call {call.id} "
                        f"(company: {call.company_id}, created: {call.created_at})"
                    )
                return
            
            # Process calls in batches
            call_service = CallService(session)
            success_count = 0
            error_count = 0
            
            for i in range(0, total_calls, batch_size):
                batch = calls[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_calls + batch_size - 1) // batch_size
                
                logger.info(
                    f"Processing batch {batch_num}/{total_batches} "
                    f"({len(batch)} calls)"
                )
                
                # Process batch concurrently
                tasks = []
                for idx, call in enumerate(batch):
                    call_num = i + idx + 1
                    task = process_single_call(call_service, call, call_num, total_calls)
                    tasks.append(task)
                
                # Wait for batch to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count successes and errors
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"Error in batch processing: {result}")
                    elif result:
                        success_count += 1
                    else:
                        error_count += 1
                
                # Commit after each batch
                try:
                    await session.commit()
                    logger.info(f"Batch {batch_num} committed successfully")
                except Exception as e:
                    logger.error(f"Error committing batch {batch_num}: {e}")
                    await session.rollback()
            
            logger.info(
                f"Processing complete: {success_count} succeeded, "
                f"{error_count} failed out of {total_calls} total"
            )
            
        except Exception as e:
            logger.error(f"Error processing calls: {e}")
            await session.rollback()
            raise


async def process_single_call(
    call_service: CallService,
    call: CallORM,
    call_num: int,
    total_calls: int,
) -> bool:
    """
    Process a single call and trigger analysis.
    
    Args:
        call_service: CallService instance
        call: CallORM object to process
        call_num: Current call number (for logging)
        total_calls: Total number of calls (for logging)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(
            f"[{call_num}/{total_calls}] Processing call {call.id} "
            f"(company: {call.company_id}, created: {call.created_at})"
        )
        
        await call_service.trigger_analysis(call.id)
        
        logger.info(f"[{call_num}/{total_calls}] Successfully triggered analysis for call {call.id}")
        return True
        
    except Exception as e:
        logger.error(
            f"[{call_num}/{total_calls}] Failed to trigger analysis for call {call.id}: {e}"
        )
        return False


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Retroactively trigger analysis for existing calls"
    )
    parser.add_argument(
        "--company-id",
        type=str,
        help="Optional company ID to filter calls by",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit on number of calls to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without actually triggering analysis",
    )
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Include calls that already have analysis (re-process them)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of calls to process concurrently (default: 10)",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    # Parse company_id if provided
    company_id = None
    if args.company_id:
        try:
            company_id = UUID(args.company_id)
        except ValueError:
            logger.error(f"Invalid company ID format: {args.company_id}")
            sys.exit(1)
    
    # Run the async function
    try:
        asyncio.run(
            process_calls(
                company_id=company_id,
                limit=args.limit,
                dry_run=args.dry_run,
                skip_processed=not args.include_processed,
                batch_size=args.batch_size,
            )
        )
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

