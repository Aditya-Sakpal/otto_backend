"""
Script to fix objection category names in existing call_summaries

This script updates all objections in the database to use the standardized
category names from the ObjectionCategory enum.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint
import os
from dotenv import load_dotenv

load_dotenv()

# Import the enum
from app.models.enums import ObjectionCategory

async def fix_objection_categories():
    """Fix objection category names in all call_summaries"""
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("MONGODB_DB_NAME")]
    
    # Get the correct category mapping
    correct_categories = ObjectionCategory.get_category_mapping()
    
    print(f"\n{'='*80}")
    print("FIXING OBJECTION CATEGORIES")
    print(f"{'='*80}\n")
    
    print("Correct category mapping:")
    for cat_id, cat_name in correct_categories.items():
        print(f"  {cat_id}: {cat_name}")
    print()
    
    # Known incorrect mappings (from database inspection)
    incorrect_mappings = {
        "Communication Issues": "Inefficient Agent Communication",
        "Scheduling Conflict": "Scheduling Conflicts",
        "Price/Fee Concerns": "Service Fee Concerns",
    }
    
    # Get all call summaries
    call_summaries = await db.call_summaries.find({}).to_list(length=None)
    
    print(f"Found {len(call_summaries)} call summaries to check\n")
    
    updated_count = 0
    objections_fixed = 0
    
    for call_summary in call_summaries:
        call_id = call_summary.get("call_id", "unknown")
        objections_data = call_summary.get("objections", {})
        objections = objections_data.get("objections", [])
        
        if not objections:
            continue
        
        needs_update = False
        
        for objection in objections:
            cat_id = objection.get("category_id")
            cat_text = objection.get("category_text", "")
            
            # Check if category_id is valid (1-10)
            if cat_id not in correct_categories:
                print(f"⚠️  Call {call_id}: Invalid category_id {cat_id}, skipping")
                continue
            
            # Get the correct category name for this ID
            correct_name = correct_categories[cat_id]
            
            # Check if it needs fixing
            if cat_text != correct_name:
                print(f"📝 Call {call_id}: Fixing category {cat_id}")
                print(f"   From: '{cat_text}'")
                print(f"   To:   '{correct_name}'")
                objection["category_text"] = correct_name
                needs_update = True
                objections_fixed += 1
        
        # Update the document if needed
        if needs_update:
            result = await db.call_summaries.update_one(
                {"call_id": call_id},
                {"$set": {"objections": objections_data}}
            )
            
            if result.modified_count > 0:
                updated_count += 1
                print(f"✅ Updated call {call_id}")
            else:
                print(f"⚠️  Failed to update call {call_id}")
            print()
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Call summaries updated: {updated_count}")
    print(f"Objections fixed: {objections_fixed}")
    print()
    
    await client.close()
    
    print("✅ Migration complete!")

if __name__ == "__main__":
    asyncio.run(fix_objection_categories())
