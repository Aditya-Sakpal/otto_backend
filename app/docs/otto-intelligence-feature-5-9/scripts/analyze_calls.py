#!/usr/bin/env python3
"""
Script to fetch transcripts and summaries for specific call IDs
for analysis of reported issues.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
import httpx

# Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://admin:fp36rqULVlBjL940@stella-user-details.1vnaurg.mongodb.net/?retryWrites=true&w=majority")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
API_KEY = os.getenv("API_KEY", "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP")
BASE_URL = os.getenv("BASE_URL", "http://localhost:9000")

# Call IDs to analyze
CALL_IDS = [440, 441, 442, 443, 444, 445, 446, 447, 448, 449, 450, 451]


async def get_mongodb_client():
    """Get MongoDB client."""
    client = AsyncIOMotorClient(MONGODB_URL)
    return client


async def fetch_call_data(db, call_id: int) -> Dict[str, Any]:
    """Fetch call document from MongoDB."""
    call_doc = await db.calls.find_one({"call_id": str(call_id)})
    if not call_doc:
        # Try with integer
        call_doc = await db.calls.find_one({"call_id": call_id})
    return call_doc


async def fetch_transcript(db, call_id: int) -> Optional[str]:
    """Fetch transcript for a call."""
    # First check the calls collection
    call_doc = await fetch_call_data(db, call_id)
    if call_doc and call_doc.get("transcript"):
        return call_doc["transcript"]
    
    # Check chunk_summaries for transcript pieces
    chunks = await db.chunk_summaries.find(
        {"call_id": str(call_id)}
    ).sort("chunk_index", 1).to_list(length=None)
    
    if chunks:
        # Combine chunk texts if available
        transcript_parts = []
        for chunk in chunks:
            if chunk.get("text"):
                transcript_parts.append(chunk["text"])
        if transcript_parts:
            return "\n".join(transcript_parts)
    
    return None


async def fetch_summary_from_api(call_id: int) -> Optional[Dict[str, Any]]:
    """Fetch summary from the API endpoint."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/call-processing/summary/{call_id}",
                headers={"X-API-Key": API_KEY}
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"  API returned {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            print(f"  API error: {e}")
            return None


async def fetch_summary_from_db(db, call_id: int) -> Optional[Dict[str, Any]]:
    """Fetch summary directly from MongoDB."""
    summary_doc = await db.call_summaries.find_one({"call_id": str(call_id)})
    if not summary_doc:
        summary_doc = await db.call_summaries.find_one({"call_id": call_id})
    
    if summary_doc:
        # Remove MongoDB _id for cleaner output
        summary_doc.pop("_id", None)
    
    return summary_doc


async def analyze_call(db, call_id: int, output_dir: str) -> Dict[str, Any]:
    """Analyze a single call and save results."""
    print(f"\n{'='*60}")
    print(f"Analyzing Call ID: {call_id}")
    print(f"{'='*60}")
    
    result = {
        "call_id": call_id,
        "timestamp": datetime.utcnow().isoformat(),
        "call_data": None,
        "transcript": None,
        "summary": None,
        "errors": []
    }
    
    # Fetch call data
    print(f"  Fetching call data...")
    call_data = await fetch_call_data(db, call_id)
    if call_data:
        call_data.pop("_id", None)
        result["call_data"] = call_data
        print(f"  ✓ Found call data")
    else:
        result["errors"].append("Call data not found in MongoDB")
        print(f"  ✗ Call data not found")
    
    # Fetch transcript
    print(f"  Fetching transcript...")
    transcript = await fetch_transcript(db, call_id)
    if transcript:
        result["transcript"] = transcript
        print(f"  ✓ Found transcript ({len(transcript)} chars)")
    else:
        result["errors"].append("Transcript not found")
        print(f"  ✗ Transcript not found")
    
    # Fetch summary from API
    print(f"  Fetching summary from API...")
    summary = await fetch_summary_from_api(call_id)
    if summary:
        result["summary"] = summary
        print(f"  ✓ Got summary from API")
    else:
        # Try from DB directly
        print(f"  Trying MongoDB directly...")
        summary = await fetch_summary_from_db(db, call_id)
        if summary:
            result["summary"] = summary
            print(f"  ✓ Got summary from MongoDB")
        else:
            result["errors"].append("Summary not found")
            print(f"  ✗ Summary not found")
    
    # Save individual call analysis
    output_file = os.path.join(output_dir, f"call_{call_id}_analysis.json")
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"  Saved to: {output_file}")
    
    return result


async def main():
    """Main analysis function."""
    print("="*60)
    print("Otto Intelligence - Call Analysis Script")
    print("="*60)
    print(f"Analyzing {len(CALL_IDS)} calls: {CALL_IDS}")
    print(f"MongoDB: {MONGODB_DB_NAME}")
    print(f"API: {BASE_URL}")
    
    # Create output directory
    output_dir = os.path.join(os.path.dirname(__file__), "..", "analysis_results")
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # Connect to MongoDB
    print("\nConnecting to MongoDB...")
    client = await get_mongodb_client()
    db = client[MONGODB_DB_NAME]
    
    # Test connection
    try:
        await client.admin.command('ping')
        print("✓ MongoDB connected")
    except Exception as e:
        print(f"✗ MongoDB connection failed: {e}")
        return
    
    # Analyze each call
    all_results = []
    for call_id in CALL_IDS:
        try:
            result = await analyze_call(db, call_id, output_dir)
            all_results.append(result)
        except Exception as e:
            print(f"  ✗ Error analyzing call {call_id}: {e}")
            all_results.append({
                "call_id": call_id,
                "error": str(e)
            })
    
    # Save combined results
    combined_file = os.path.join(output_dir, "all_calls_analysis.json")
    with open(combined_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n✓ Combined results saved to: {combined_file}")
    
    # Summary
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    
    successful = sum(1 for r in all_results if r.get("summary"))
    failed = len(all_results) - successful
    
    print(f"Total calls analyzed: {len(all_results)}")
    print(f"Successful (with summary): {successful}")
    print(f"Failed (no summary): {failed}")
    
    if failed > 0:
        print("\nCalls without summaries:")
        for r in all_results:
            if not r.get("summary"):
                print(f"  - Call {r['call_id']}: {r.get('errors', ['Unknown error'])}")
    
    # Close connection
    client.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())

