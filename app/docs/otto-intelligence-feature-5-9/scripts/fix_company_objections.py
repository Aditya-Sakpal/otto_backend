"""
Script to fix objection categories for specific company
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

# Import the enum
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app.models.enums import ObjectionCategory

async def fix_specific_company():
    """Fix objection category names for specific company"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("MONGODB_DB_NAME")]
    
    # Get the correct category mapping
    correct_categories = ObjectionCategory.get_category_mapping()
    
    print("\nCorrect category mapping:")
    for cat_id, cat_name in correct_categories.items():
        print(f"  {cat_id}: {cat_name}")
    print()
    
    # Specific company ID
    company_id = "91ecfcb9-fc40-4792-ba47-65b273cec204"
    
    # Get call summaries for this company
    call_summaries = await db.call_summaries.find(
        {"company_id": company_id}
    ).to_list(length=None)
    
    print(f"Found {len(call_summaries)} call summaries for company {company_id}\n")
    
    updated_count = 0
    
    for call_summary in call_summaries:
        call_id = call_summary.get("call_id")
        objections_data = call_summary.get("objections", {})
        objections = objections_data.get("objections", [])
        
        if not objections:
            continue
        
        needs_update = False
        
        print(f"Call {call_id}: {len(objections)} objections")
        
        for objection in objections:
            cat_id = objection.get("category_id")
            cat_text = objection.get("category_text", "")
            
            if cat_id not in correct_categories:
                print(f"  ⚠️  Invalid category_id {cat_id}")
                continue
            
            correct_name = correct_categories[cat_id]
            
            if cat_text != correct_name:
                print(f"  📝 Fixing: '{cat_text}' -> '{correct_name}'")
                objection["category_text"] = correct_name
                needs_update = True
        
        if needs_update:
            result = await db.call_summaries.update_one(
                {"call_id": call_id},
                {"$set": {"objections": objections_data}}
            )
            
            if result.modified_count > 0:
                updated_count += 1
                print(f"  ✅ Updated\n")
            else:
                print(f"  ⚠️  Update failed\n")
    
    print(f"\nUpdated {updated_count} call summaries")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(fix_specific_company())
