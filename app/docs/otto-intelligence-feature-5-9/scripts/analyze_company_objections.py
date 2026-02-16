"""
In-depth Analysis of Objections for Company ID: 91ecfcb9-fc40-4792-ba47-65b273cec204

This script analyzes all objections in call_summaries for the specified company
and shows what transformations would occur based on the ObjectionCategory enum.

Output: CSV file with before/after comparison
"""

import asyncio
import sys
from pathlib import Path
import csv
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from app.models.enums import ObjectionCategory

load_dotenv()


async def analyze_company_objections():
    """Analyze objections for specific company and generate CSV report"""
    
    # Company ID to analyze
    company_id = "6d40b509-82bc-4d21-9614-de91cc25dc1b"
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("MONGODB_DB_NAME")]
    
    # Get correct category mapping from enum
    correct_categories = ObjectionCategory.get_category_mapping()
    category_descriptions = ObjectionCategory.get_category_descriptions()
    
    print("="*100)
    print(f"IN-DEPTH OBJECTION ANALYSIS FOR COMPANY: {company_id}")
    print("="*100)
    print()
    
    # Get all call summaries for this company
    call_summaries = await db.call_summaries.find(
        {"company_id": company_id}
    ).to_list(length=None)
    
    print(f"Found {len(call_summaries)} call summaries for this company")
    print()
    
    # Prepare data for CSV
    csv_data = []
    
    # Statistics
    total_objections = 0
    objections_needing_correction = 0
    category_corrections = {}
    calls_with_objections = 0
    calls_without_objections = 0
    
    # Process each call
    for call_summary in call_summaries:
        call_id = call_summary.get("call_id", "unknown")
        call_date = call_summary.get("created_at", "unknown")
        objections_data = call_summary.get("objections", {})
        objections = objections_data.get("objections", [])
        
        if not objections:
            calls_without_objections += 1
            # Add row for calls with no objections
            csv_data.append({
                "call_id": call_id,
                "call_date": str(call_date),
                "has_objections": "NO",
                "objection_count": 0,
                "objection_text": "",
                "current_category_id": "",
                "current_category_text": "",
                "expected_category_text": "",
                "needs_correction": "",
                "correction_type": "",
                "confidence_score": "",
                "severity": "",
                "overcome": "",
                "speaker_id": "",
                "category_description": "",
                "category_examples": ""
            })
            continue
        
        calls_with_objections += 1
        total_objections += len(objections)
        
        # Process each objection
        for idx, objection in enumerate(objections, 1):
            cat_id = objection.get("category_id")
            cat_text = objection.get("category_text", "")
            obj_text = objection.get("objection_text", "")
            confidence = objection.get("confidence_score", 0)
            severity = objection.get("severity", "")
            overcome = objection.get("overcome", False)
            speaker = objection.get("speaker_id", "")
            
            # Validate category
            needs_correction = False
            correction_type = ""
            expected_cat_text = ""
            
            # Check 1: Is category_id valid (1-10)?
            if cat_id not in correct_categories:
                needs_correction = True
                correction_type = "INVALID_ID"
                expected_cat_text = "Other"
                objections_needing_correction += 1
            else:
                expected_cat_text = correct_categories[cat_id]
                
                # Check 2: Does category_text match enum?
                if cat_text != expected_cat_text:
                    needs_correction = True
                    correction_type = "NAME_MISMATCH"
                    objections_needing_correction += 1
                    
                    # Track this correction
                    correction_key = f"{cat_text} → {expected_cat_text}"
                    category_corrections[correction_key] = category_corrections.get(correction_key, 0) + 1
            
            # Get category details from enum
            cat_details = category_descriptions.get(cat_id, {})
            cat_description = cat_details.get("description", "")
            cat_examples = " | ".join(cat_details.get("examples", []))
            
            # Add to CSV data
            csv_data.append({
                "call_id": call_id,
                "call_date": str(call_date),
                "has_objections": "YES",
                "objection_count": len(objections),
                "objection_number": f"{idx}/{len(objections)}",
                "objection_text": obj_text[:200] + "..." if len(obj_text) > 200 else obj_text,
                "current_category_id": cat_id,
                "current_category_text": cat_text,
                "expected_category_text": expected_cat_text,
                "needs_correction": "YES" if needs_correction else "NO",
                "correction_type": correction_type,
                "confidence_score": f"{confidence:.2f}",
                "severity": severity,
                "overcome": "YES" if overcome else "NO",
                "speaker_id": speaker,
                "category_description": cat_description,
                "category_examples": cat_examples
            })
    
    # Write to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"objection_analysis_{company_id[:8]}_{timestamp}.csv"
    
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            "call_id", "call_date", "has_objections", "objection_count", "objection_number",
            "objection_text", "current_category_id", "current_category_text", 
            "expected_category_text", "needs_correction", "correction_type",
            "confidence_score", "severity", "overcome", "speaker_id",
            "category_description", "category_examples"
        ]
        
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)
    
    print("="*100)
    print("SUMMARY STATISTICS")
    print("="*100)
    print()
    print(f"📊 Total Calls Analyzed: {len(call_summaries)}")
    print(f"   ├─ Calls WITH objections: {calls_with_objections}")
    print(f"   └─ Calls WITHOUT objections: {calls_without_objections}")
    print()
    print(f"📝 Total Objections Found: {total_objections}")
    print(f"   ├─ Objections CORRECT: {total_objections - objections_needing_correction}")
    print(f"   └─ Objections NEEDING CORRECTION: {objections_needing_correction}")
    print()
    
    if objections_needing_correction > 0:
        print("🔧 CORRECTIONS NEEDED BY TYPE:")
        print()
        for correction, count in sorted(category_corrections.items(), key=lambda x: x[1], reverse=True):
            print(f"   {correction}: {count} objection(s)")
        print()
    
    # Category distribution
    print("="*100)
    print("CATEGORY DISTRIBUTION (CURRENT STATE)")
    print("="*100)
    print()
    
    category_counts = {}
    for row in csv_data:
        if row["has_objections"] == "YES":
            cat_text = row["current_category_text"]
            category_counts[cat_text] = category_counts.get(cat_text, 0) + 1
    
    for cat_text, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_objections * 100) if total_objections > 0 else 0
        print(f"   {cat_text:50s} {count:3d} ({percentage:5.1f}%)")
    
    print()
    print("="*100)
    print("EXPECTED CATEGORY DISTRIBUTION (AFTER CORRECTION)")
    print("="*100)
    print()
    
    expected_category_counts = {}
    for row in csv_data:
        if row["has_objections"] == "YES":
            cat_text = row["expected_category_text"]
            expected_category_counts[cat_text] = expected_category_counts.get(cat_text, 0) + 1
    
    for cat_text, count in sorted(expected_category_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_objections * 100) if total_objections > 0 else 0
        print(f"   {cat_text:50s} {count:3d} ({percentage:5.1f}%)")
    
    print()
    print("="*100)
    print("DETAILED OBJECTION BREAKDOWN")
    print("="*100)
    print()
    
    # Show each call with objections
    for call_summary in call_summaries:
        call_id = call_summary.get("call_id", "unknown")
        objections = call_summary.get("objections", {}).get("objections", [])
        
        if objections:
            print(f"\n📞 Call ID: {call_id}")
            print(f"   Objections: {len(objections)}")
            print()
            
            for idx, obj in enumerate(objections, 1):
                cat_id = obj.get("category_id")
                cat_text = obj.get("category_text", "")
                expected = correct_categories.get(cat_id, "Other")
                needs_fix = "❌" if cat_text != expected else "✅"
                
                print(f"   {needs_fix} Objection {idx}:")
                print(f"      Category: [{cat_id}] {cat_text}")
                if cat_text != expected:
                    print(f"      Should be: [{cat_id}] {expected}")
                print(f"      Text: {obj.get('objection_text', '')[:100]}...")
                print(f"      Confidence: {obj.get('confidence_score', 0):.2f} | Severity: {obj.get('severity', 'unknown')}")
                print()
    
    print()
    print("="*100)
    print(f"✅ ANALYSIS COMPLETE - Results saved to: {csv_filename}")
    print("="*100)
    print()
    print("📋 CSV COLUMNS:")
    print("   - call_id: Unique call identifier")
    print("   - call_date: When the call was processed")
    print("   - has_objections: YES/NO indicator")
    print("   - objection_count: Total objections in this call")
    print("   - objection_text: The actual objection statement")
    print("   - current_category_id: Current category ID (1-10)")
    print("   - current_category_text: Current category name in DB")
    print("   - expected_category_text: What it SHOULD be (from enum)")
    print("   - needs_correction: YES if mismatch detected")
    print("   - correction_type: INVALID_ID or NAME_MISMATCH")
    print("   - confidence_score: LLM confidence (0.0-1.0)")
    print("   - severity: low/medium/high")
    print("   - overcome: Was objection resolved?")
    print("   - speaker_id: Who raised the objection")
    print("   - category_description: Description from enum")
    print("   - category_examples: Example phrases from enum")
    print()
    
    await client.close()
    
    return csv_filename


if __name__ == "__main__":
    csv_file = asyncio.run(analyze_company_objections())
    print(f"\n🎉 Open {csv_file} to view the complete analysis!")
