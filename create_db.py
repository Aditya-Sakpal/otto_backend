import asyncio
from app.infrastructure.database.session import engine
from app.infrastructure.database.base_class import Base
import app.infrastructure.database.models

async def create():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("--- DATABASE TABLES CREATED SUCCESSFULLY ---")

if __name__ == "__main__":
    asyncio.run(create())
