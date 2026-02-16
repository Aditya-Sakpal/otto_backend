#!/usr/bin/env python3
"""
Re-process calls with the upgraded GPT model to measure improvement.
"""

import asyncio
import httpx
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_KEY = os.getenv("API_KEY")
BASE_API_URL = os.getenv("BASE_API_URL", "http://localhost:8000")
INPUT_FILE = "./analysis_results/all_calls_analysis.json"
OUTPUT_DIR = "./analysis_results/reprocessed_with_new_model"

async def extract_audio_urls(input_file):
    """Extract audio URLs and call IDs from the analysis file."""
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    calls = []
    for call in data:
        if call.get("call_data") and call["call_data"].get("audio_url"):
            calls.append({
                "call_id": call["call_id"],
                "audio_url": call["call_data"]["audio_url"]
            })
    
    return calls

async def process_call(call_id, audio_url):
    """Submit a call for processing and wait for completion."""
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    
    print(f"\n{'='*60}")
    print(f"Processing Call ID: {call_id}")
    print(f"{'='*60}")
    
    # Submit for processing
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Submit call
            print(f"  → Submitting call for processing...")
            submit_response = await client.post(
                f"{BASE_API_URL}/api/v1/call-processing/process",
                headers=headers,
                json={
                    "audio_url": audio_url,
                    "call_id": str(call_id),
                    "phone_number": "reprocess_test",
                    "company_id": "reprocess_test"
                }
            )
            
            if submit_response.status_code not in [200, 202]:
                error_msg = f"Failed to submit: {submit_response.status_code} - {submit_response.text}"
                print(f"  ✗ {error_msg}")
                return {
                    "call_id": call_id,
                    "status": "failed",
                    "error": error_msg,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            submit_data = submit_response.json()
            job_id = submit_data.get("job_id")
            print(f"  ✓ Submitted with job_id: {job_id}")
            
            # Poll for completion
            max_attempts = 60  # 5 minutes max
            attempt = 0
            
            while attempt < max_attempts:
                await asyncio.sleep(5)
                attempt += 1
                
                status_response = await client.get(
                    f"{BASE_API_URL}/api/v1/call-processing/status/{job_id}",
                    headers=headers
                )
                
                if status_response.status_code != 200:
                    continue
                
                status_data = status_response.json()
                status = status_data.get("status")
                
                print(f"  → Status check {attempt}: {status}")
                
                if status == "completed":
                    print(f"  ✓ Processing completed!")
                    
                    # Fetch summary
                    summary_response = await client.get(
                        f"{BASE_API_URL}/api/v1/call-processing/summary/{call_id}",
                        headers=headers
                    )
                    
                    if summary_response.status_code == 200:
                        summary_data = summary_response.json()
                        print(f"  ✓ Summary retrieved")
                        return {
                            "call_id": call_id,
                            "status": "completed",
                            "job_id": job_id,
                            "summary": summary_data,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    else:
                        error_msg = f"Failed to fetch summary: {summary_response.status_code}"
                        print(f"  ✗ {error_msg}")
                        return {
                            "call_id": call_id,
                            "status": "completed_no_summary",
                            "error": error_msg,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                
                elif status == "failed":
                    error = status_data.get("error", "Unknown error")
                    print(f"  ✗ Processing failed: {error}")
                    return {
                        "call_id": call_id,
                        "status": "failed",
                        "error": error,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            
            # Timeout
            print(f"  ✗ Timeout after {max_attempts} attempts")
            return {
                "call_id": call_id,
                "status": "timeout",
                "error": f"Timed out after {max_attempts * 5} seconds",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"  ✗ {error_msg}")
            return {
                "call_id": call_id,
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.utcnow().isoformat()
            }

async def main():
    print("="*60)
    print("Otto Intelligence - Reprocess Calls with New Model")
    print("="*60)
    
    # Extract audio URLs
    print("\n→ Extracting audio URLs from analysis file...")
    calls = await extract_audio_urls(INPUT_FILE)
    print(f"✓ Found {len(calls)} calls to reprocess\n")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Process each call
    results = []
    for i, call in enumerate(calls, 1):
        print(f"\n[{i}/{len(calls)}] Processing Call ID {call['call_id']}...")
        result = await process_call(call["call_id"], call["audio_url"])
        results.append(result)
        
        # Save individual result
        output_file = os.path.join(OUTPUT_DIR, f"call_{call['call_id']}_new.json")
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  💾 Saved to: {output_file}")
        
        # Small delay between calls
        if i < len(calls):
            await asyncio.sleep(2)
    
    # Save combined results
    combined_file = os.path.join(OUTPUT_DIR, "all_calls_reprocessed.json")
    with open(combined_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ Combined results saved to: {combined_file}")
    
    # Summary statistics
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] in ["failed", "error", "timeout"])
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total calls: {len(calls)}")
    print(f"Successfully processed: {completed}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print("\nFailed calls:")
        for r in results:
            if r["status"] in ["failed", "error", "timeout"]:
                print(f"  - Call {r['call_id']}: {r.get('error', 'Unknown')}")
    
    print("\n✓ Done!\n")

if __name__ == "__main__":
    asyncio.run(main())

