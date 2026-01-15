"""
Test script for all Shunya API endpoints.

Tests all Shunya-related endpoints with valid test data.
"""
import asyncio
import httpx
import os
import sys
from uuid import UUID, uuid4
from datetime import datetime, date
import json

# Set encoding for Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"

# Shunya test data (from environment or defaults)
SHUNYA_BASE_URL = os.getenv("UWC_BASE_URL", "https://ottoai.shunyalabs.ai")
SHUNYA_API_KEY = os.getenv("API_KEY") or os.getenv("UWC_API_KEY") or os.getenv("UWC_JWT_SECRET") or "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"

# Set environment variables for the backend to use
os.environ["UWC_BASE_URL"] = SHUNYA_BASE_URL
os.environ["API_KEY"] = SHUNYA_API_KEY

# Test data
TEST_COMPANY_ID = "11111111-1111-1111-1111-111111111111"
TEST_CALL_ID = "11110000-0000-0000-0000-000000000001"
TEST_AUDIO_URL = "https://pub-0d05beffe4df48109a9b7182cfc00427.r2.dev/courtney.mp3"


async def test_endpoint(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    test_name: str,
    json_data: dict = None,
    params: dict = None,
    expected_status: list = [200, 201, 202],
    description: str = "",
):
    """Test an API endpoint."""
    try:
        print(f"\n{'='*80}")
        print(f"Testing: {test_name}")
        if description:
            print(f"Description: {description}")
        print(f"Method: {method} {url}")
        if json_data:
            print(f"Payload: {json.dumps(json_data, indent=2)}")
        if params:
            print(f"Params: {params}")
        print(f"{'='*80}")
        
        response = await client.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            timeout=60.0,
        )
        
        status_code = response.status_code
        print(f"Status Code: {status_code}")
        
        try:
            response_data = response.json()
            print(f"Response: {json.dumps(response_data, indent=2, default=str)}")
        except:
            print(f"Response Text: {response.text[:500]}")
        
        if status_code in expected_status:
            print(f"✅ PASSED: {test_name}")
            return response_data
        else:
            print(f"❌ FAILED: {test_name} - Expected status {expected_status}, got {status_code}")
            return None
            
    except Exception as e:
        print(f"❌ ERROR: {test_name} - {str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def test_all_shunya_apis():
    """Test all Shunya-related API endpoints."""
    print("\n" + "="*80)
    print("SHUNYA API ENDPOINT TESTS")
    print("="*80)
    
    async with httpx.AsyncClient() as client:
        # ====================================================================
        # CALL PROCESSING ENDPOINTS
        # ====================================================================
        print("\n\n" + "🔵 " + "="*78)
        print("🔵 CALL PROCESSING ENDPOINTS")
        print("🔵 " + "="*78)
        
        # 1. Process Call
        process_response = await test_endpoint(
            client,
            "POST",
            f"{BASE_URL}{API_PREFIX}/call-processing/process",
            json_data={
                "call_id": TEST_CALL_ID,
                "company_id": TEST_COMPANY_ID,
                "audio_url": TEST_AUDIO_URL,
                "phone_number": "+1234567890",
                "duration": 120,
                "call_date": datetime.utcnow().isoformat() + "Z",
                "metadata": {
                    "call_type": "csr_call",
                    "source": "twilio"
                },
                "options": {
                    "skip_rag_indexing": False,
                    "skip_summary_generation": False,
                    "priority": "normal"
                }
            },
            test_name="POST /call-processing/process",
            expected_status=[202],
            description="Submit a call for AI processing"
        )
        
        job_id = None
        if process_response and "job_id" in process_response:
            job_id = process_response["job_id"]
            print(f"\n📝 Job ID: {job_id}")
        
        # 2. Get Job Status
        if job_id:
            await test_endpoint(
                client,
                "GET",
                f"{BASE_URL}{API_PREFIX}/call-processing/status/{job_id}",
                test_name=f"GET /call-processing/status/{job_id}",
                expected_status=[200, 404],
                description="Get call processing job status"
            )
        
        # 3. Get Call Summary
        await test_endpoint(
            client,
            "GET",
            f"{BASE_URL}{API_PREFIX}/call-processing/summary/{TEST_CALL_ID}?include_chunks=false",
            test_name=f"GET /call-processing/summary/{TEST_CALL_ID}",
            expected_status=[200, 404, 503],
            description="Get call summary with compliance analysis"
        )
        
        # 4. Get Call Chunks
        await test_endpoint(
            client,
            "GET",
            f"{BASE_URL}{API_PREFIX}/call-processing/chunks/{TEST_CALL_ID}",
            test_name=f"GET /call-processing/chunks/{TEST_CALL_ID}",
            expected_status=[200, 404, 503],
            description="Get call chunks with summaries"
        )
        
        # 5. Retry Failed Job (if we have a job_id)
        if job_id:
            await test_endpoint(
                client,
                "POST",
                f"{BASE_URL}{API_PREFIX}/call-processing/retry/{job_id}",
                test_name=f"POST /call-processing/retry/{job_id}",
                expected_status=[202, 400, 404],
                description="Retry a failed call processing job"
            )
        
        # ====================================================================
        # ASK OTTO ENDPOINTS
        # ====================================================================
        print("\n\n" + "🟢 " + "="*78)
        print("🟢 ASK OTTO ENDPOINTS")
        print("🟢 " + "="*78)
        
        # 1. Create Conversation
        conversation_response = await test_endpoint(
            client,
            "POST",
            f"{BASE_URL}{API_PREFIX}/ask-otto/conversations",
            json_data={
                "company_id": TEST_COMPANY_ID,
                "context": {
                    "user_role": "executive",
                    "focus_area": "sales"
                }
            },
            test_name="POST /ask-otto/conversations",
            expected_status=[201],
            description="Create a new Ask Otto conversation"
        )
        
        conversation_id = None
        if conversation_response and "id" in conversation_response:
            conversation_id = conversation_response["id"]
            print(f"\n📝 Conversation ID: {conversation_id}")
        
        # 2. Send Message
        if conversation_id:
            message_response = await test_endpoint(
                client,
                "POST",
                f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}/messages",
                json_data={
                    "message": "What are the top objections this week?"
                },
                test_name=f"POST /ask-otto/conversations/{conversation_id}/messages",
                expected_status=[200, 201],
                description="Send a message in an Ask Otto conversation"
            )
        
        # 3. Get Messages
        if conversation_id:
            await test_endpoint(
                client,
                "GET",
                f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}/messages",
                test_name=f"GET /ask-otto/conversations/{conversation_id}/messages",
                expected_status=[200, 404],
                description="Get all messages in an Ask Otto conversation"
            )
        
        # 4. Get Conversation
        if conversation_id:
            await test_endpoint(
                client,
                "GET",
                f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}",
                test_name=f"GET /ask-otto/conversations/{conversation_id}",
                expected_status=[200, 404],
                description="Get Ask Otto conversation details"
            )
        
        # 5. Delete Conversation (commented out to keep test data)
        # if conversation_id:
        #     await test_endpoint(
        #         client,
        #         "DELETE",
        #         f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}",
        #         test_name=f"DELETE /ask-otto/conversations/{conversation_id}",
        #         expected_status=[200, 204, 404],
        #         description="Delete an Ask Otto conversation"
        #     )
        
        # ====================================================================
        # INSIGHTS ENDPOINTS
        # ====================================================================
        print("\n\n" + "🟡 " + "="*78)
        print("🟡 INSIGHTS ENDPOINTS")
        print("🟡 " + "="*78)
        
        # Calculate week range (current week)
        today = date.today()
        week_start = today.replace(day=today.day - today.weekday())
        week_end = week_start.replace(day=week_start.day + 6)
        
        # 1. Generate Insights
        insights_response = await test_endpoint(
            client,
            "POST",
            f"{BASE_URL}{API_PREFIX}/insights/generate",
            json_data={
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "company_ids": [TEST_COMPANY_ID],
                "insight_types": ["company", "customer", "objection"],
                "options": {
                    "force_regenerate": False,
                    "include_inactive_customers": False
                }
            },
            test_name="POST /insights/generate",
            expected_status=[202],
            description="Generate insights for specified companies and week range"
        )
        
        insight_job_id = None
        if insights_response and "job_id" in insights_response:
            insight_job_id = insights_response["job_id"]
            print(f"\n📝 Insight Job ID: {insight_job_id}")
        
        # 2. Get Job Status
        if insight_job_id:
            await test_endpoint(
                client,
                "GET",
                f"{BASE_URL}{API_PREFIX}/insights/status/{insight_job_id}",
                test_name=f"GET /insights/status/{insight_job_id}",
                expected_status=[200, 404],
                description="Get insight generation job status"
            )
        
        # 3. Get Current Company Insight
        await test_endpoint(
            client,
            "GET",
            f"{BASE_URL}{API_PREFIX}/insights/company/{TEST_COMPANY_ID}/current",
            test_name=f"GET /insights/company/{TEST_COMPANY_ID}/current",
            expected_status=[200, 404, 503],
            description="Get current company insight"
        )
        
        # 4. Get Customer Insights
        await test_endpoint(
            client,
            "GET",
            f"{BASE_URL}{API_PREFIX}/insights/customers",
            params={
                "company_id": TEST_COMPANY_ID,
                "page": 1,
                "limit": 50
            },
            test_name="GET /insights/customers",
            expected_status=[200, 404, 503],
            description="Get customer insights with pagination"
        )
        
        # 5. Get Objection Insights
        await test_endpoint(
            client,
            "GET",
            f"{BASE_URL}{API_PREFIX}/insights/objections/{TEST_COMPANY_ID}",
            test_name=f"GET /insights/objections/{TEST_COMPANY_ID}",
            expected_status=[200, 404, 503],
            description="Get objection insights for a company"
        )
        
        # ====================================================================
        # SUMMARY
        # ====================================================================
        print("\n\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print("✅ All Shunya API endpoints have been tested")
        print(f"📝 Test Company ID: {TEST_COMPANY_ID}")
        print(f"📝 Test Call ID: {TEST_CALL_ID}")
        if job_id:
            print(f"📝 Call Processing Job ID: {job_id}")
        if conversation_id:
            print(f"📝 Conversation ID: {conversation_id}")
        if insight_job_id:
            print(f"📝 Insight Job ID: {insight_job_id}")
        print("="*80)


if __name__ == "__main__":
    print("\n🚀 Starting Shunya API Tests...")
    print(f"📍 Base URL: {BASE_URL}")
    print(f"🔑 Shunya Base URL: {SHUNYA_BASE_URL}")
    print(f"🔑 Shunya API Key: {SHUNYA_API_KEY[:10]}...")
    
    asyncio.run(test_all_shunya_apis())
    
    print("\n✨ Testing complete!")
