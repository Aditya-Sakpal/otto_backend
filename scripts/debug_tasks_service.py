import asyncio, traceback, sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app.infrastructure.database.models.company_integration  # ensure model registry includes this model
import app.infrastructure.database.models.action_item  # ensure action_item model is registered
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.pending_action_service import PendingActionService
from uuid import UUID

async def main():
    company_id = UUID("6d40b509-82bc-4d21-9614-de91cc25dc1b")
    async with AsyncSessionLocal() as session:
        service = PendingActionService(session)
        try:
            res = await service.list_tasks_with_summary(company_id=company_id, skip=0, limit=5)
            print("OK", res)
        except Exception as e:
            print("EXCEPTION", e)
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())

