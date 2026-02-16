"""
Customer Context Service

Service for retrieving customer context for Ask Otto.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.conversation import CustomerContextResult


class CustomerContextService:
    """Service for customer context lookup"""
    
    async def get_customer_context(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        location: Optional[str] = None
    ) -> Optional[CustomerContextResult]:
        """
        Retrieve customer context using fuzzy matching.
        
        Args:
            db: MongoDB database
            company_id: Company ID
            name: Customer name (fuzzy search)
            phone: Customer phone
            location: Customer location hint
            
        Returns:
            CustomerContextResult if found
        """
        # Build query
        query = {"company_id": company_id}
        
        if phone:
            query["phone"] = phone
        elif name:
            # Text search on name
            query["$text"] = {"$search": name}
            
            # Add location filter if provided
            if location:
                query["$or"] = [
                    {"address": {"$regex": location, "$options": "i"}},
                    {"state": {"$regex": location, "$options": "i"}},
                    {"city": {"$regex": location, "$options": "i"}}
                ]
        else:
            return None  # Need at least name or phone
        
        # Find customer
        customer = await db.customers.find_one(query)
        
        if not customer:
            return None
        
        customer_id = str(customer["_id"])
        
        # Get recent calls
        calls_cursor = db.calls.find({
            "company_id": company_id,
            "phone_number": customer["phone"]
        }).sort("call_date", -1).limit(5)
        
        recent_calls = await calls_cursor.to_list(length=5)
        
        # Get summaries for recent calls
        call_ids = [c["call_id"] for c in recent_calls]
        summaries_cursor = db.call_summaries.find({
            "call_id": {"$in": call_ids}
        })
        summaries = await summaries_cursor.to_list(length=None)
        
        # Format recent calls summary
        recent_calls_summary = []
        for call in recent_calls:
            call_id = call["call_id"]
            
            # Find matching summary
            summary = next((s for s in summaries if s["call_id"] == call_id), None)
            
            call_summary = {
                "call_id": call_id,
                "date": call["call_date"].isoformat() if call.get("call_date") else None,
                "summary": summary.get("summary", {}).get("summary", "") if summary else "",
                "qualification_status": summary.get("qualification", {}).get("qualification_status", "") if summary else ""
            }
            recent_calls_summary.append(call_summary)
        
        # Create result
        result = CustomerContextResult(
            customer_id=customer_id,
            name=customer.get("name"),
            phone=customer["phone"],
            location=customer.get("address") or customer.get("city"),
            qualification_status=customer.get("qualification_status"),
            total_calls=customer.get("total_calls", len(recent_calls)),
            last_call_date=customer.get("last_call_date"),
            recent_calls_summary=recent_calls_summary
        )
        
        return result


# Singleton
_customer_context_service: Optional[CustomerContextService] = None


def get_customer_context_service() -> CustomerContextService:
    """Get singleton instance"""
    global _customer_context_service
    if _customer_context_service is None:
        _customer_context_service = CustomerContextService()
    return _customer_context_service

