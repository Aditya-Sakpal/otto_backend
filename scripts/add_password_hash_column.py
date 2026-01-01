"""
Script to add password_hash column to users table.

This script adds the missing password_hash column to the users table.
Run this once to fix the database schema.

Usage (from backend directory):
    python scripts/add_password_hash_column.py
"""
import asyncio
import sys
from pathlib import Path

# Add current directory to path to import app modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.infrastructure.database.session import engine
from app.core.logging import get_logger

logger = get_logger(__name__)


async def add_password_hash_column():
    """Add password_hash column to users table if it doesn't exist."""
    async with engine.begin() as conn:
        try:
            # Add password_hash column (nullable to support Clerk users)
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR")
            )
            logger.info("Successfully added password_hash column to users table")
        except Exception as e:
            logger.error(f"Error adding password_hash column: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(add_password_hash_column())

