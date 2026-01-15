"""
Comprehensive API Testing Script

Tests all API endpoints to ensure they work correctly with the database schema.
Fetches real data from the database and uses it for testing.
"""
import asyncio
import httpx
import os
import sys
from uuid import UUID, uuid4
from datetime import datetime, date
import json

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import database session and models
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models.company import CompanyORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.lead import LeadORM
from app.infrastructure.database.models.contact import ContactCardORM
from sqlalchemy import select

# Base URL for the API
BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"

# Test results
test_results = {
    "passed": [],
    "failed": [],
    "skipped": []
}

def log_test(name: str, passed: bool, message: str = "", skipped: bool = False):
    """Log test result."""
    if skipped:
        test_results["skipped"].append(f"{name}: {message}")
        print(f"[SKIP] {name} - {message}")
    elif passed:
        test_results["passed"].append(name)
        print(f"[PASS] {name}")
        if message:
            print(f"   {message}")
    else:
        test_results["failed"].append(f"{name}: {message}")
        print(f"[FAIL] {name} - {message}")

async def test_endpoint(client: httpx.AsyncClient, method: str, url: str, 
                       json_data: dict = None, params: dict = None, 
                       expected_status = 200, test_name: str = ""):
    """Test an API endpoint."""
    try:
        if method.upper() == "GET":
            response = await client.get(url, params=params, timeout=30.0)
        elif method.upper() == "POST":
            response = await client.post(url, json=json_data, params=params, timeout=30.0)
        elif method.upper() == "PUT":
            response = await client.put(url, json=json_data, params=params, timeout=30.0)
        elif method.upper() == "DELETE":
            response = await client.delete(url, params=params, timeout=30.0)
        else:
            log_test(test_name or url, False, f"Unsupported method: {method}")
            return None
        
        # Handle expected_status as int or list
        if isinstance(expected_status, list):
            status_ok = response.status_code in expected_status
        else:
            status_ok = response.status_code == expected_status
        
        if status_ok:
            log_test(test_name or url, True, f"Status: {response.status_code}")
            try:
                return response.json()
            except:
                return {"status": "success", "text": response.text[:100]}
        else:
            error_msg = f"Expected {expected_status}, got {response.status_code}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                error_msg += f" - {response.text[:200]}"
            log_test(test_name or url, False, error_msg)
            return None
    except Exception as e:
        log_test(test_name or url, False, f"Exception: {str(e)}")
        return None

async def get_test_data_from_db():
    """Get test data directly from database."""
    print("\nFetching test data directly from database...")
    
    test_company_id = None
    test_user_id = None
    test_call_id = None
    test_lead_id = None
    test_contact_card_id = None
    
    try:
        async with AsyncSessionLocal() as session:
            # Get first company
            result = await session.execute(select(CompanyORM).limit(1))
            company = result.scalar_one_or_none()
            if company:
                test_company_id = str(company.id)
                print(f"   Found company: {company.name} (ID: {test_company_id})")
            
            # Get first user (preferably from the company) - skip role conversion issues
            # Just get the ID without converting to domain model
            if test_company_id:
                try:
                    result = await session.execute(
                        select(UserORM.id, UserORM.email).where(UserORM.company_id == UUID(test_company_id)).limit(1)
                    )
                    user_row = result.first()
                    if user_row:
                        test_user_id = str(user_row[0])
                        print(f"   Found user: {user_row[1]} (ID: {test_user_id})")
                except Exception as e:
                    print(f"   Warning: Could not fetch user from company: {e}")
            
            # If no user from company, get any user
            if not test_user_id:
                try:
                    result = await session.execute(select(UserORM.id, UserORM.email, UserORM.company_id).limit(1))
                    user_row = result.first()
                    if user_row:
                        test_user_id = str(user_row[0])
                        if user_row[2]:
                            test_company_id = str(user_row[2])
                        print(f"   Found user: {user_row[1]} (ID: {test_user_id})")
                except Exception as e:
                    print(f"   Warning: Could not fetch any user: {e}")
            
            # Get first call (preferably from the company)
            if test_company_id:
                result = await session.execute(
                    select(CallORM).where(CallORM.company_id == UUID(test_company_id)).limit(1)
                )
                call = result.scalar_one_or_none()
                if call:
                    test_call_id = str(call.id)
                    print(f"   Found call: {test_call_id}")
            
            # Get first lead (preferably from the company)
            if test_company_id:
                result = await session.execute(
                    select(LeadORM).where(LeadORM.company_id == UUID(test_company_id)).limit(1)
                )
                lead = result.scalar_one_or_none()
                if lead:
                    test_lead_id = str(lead.id)
                    test_contact_card_id = str(lead.contact_card_id) if lead.contact_card_id else None
                    print(f"   Found lead: {test_lead_id}")
            
            # Get contact card if we have a lead
            if not test_contact_card_id and test_company_id:
                result = await session.execute(
                    select(ContactCardORM).where(ContactCardORM.company_id == UUID(test_company_id)).limit(1)
                )
                contact = result.scalar_one_or_none()
                if contact:
                    test_contact_card_id = str(contact.id)
                    print(f"   Found contact card: {test_contact_card_id}")
            
    except Exception as e:
        print(f"   ERROR fetching from database: {e}")
        print("   Will use API-based fallback")
        return None
    
    # Fallback to test UUIDs if no data found
    if not test_company_id:
        test_company_id = "11111111-1111-1111-1111-111111111111"
        print(f"   WARNING: No companies found in database, using test UUID: {test_company_id}")
    
    return {
        "company_id": test_company_id,
        "user_id": test_user_id,
        "call_id": test_call_id,
        "lead_id": test_lead_id,
        "contact_card_id": test_contact_card_id
    }

async def get_test_data(client: httpx.AsyncClient):
    """Get test data - try database first, then API fallback."""
    # Try database first
    db_data = await get_test_data_from_db()
    if db_data and db_data.get("company_id") != "11111111-1111-1111-1111-111111111111":
        return db_data
    
    # Fallback to API
    print("\nFalling back to API for test data...")
    
    # Try to get companies via API
    companies_resp = await test_endpoint(
        client, "GET", f"{BASE_URL}{API_PREFIX}/users/companies",
        test_name="Get Companies (for test data)",
        expected_status=[200, 404, 500]
    )
    
    test_company_id = None
    test_user_id = None
    test_call_id = None
    test_lead_id = None
    
    if companies_resp and isinstance(companies_resp, list) and len(companies_resp) > 0:
        test_company_id = companies_resp[0].get("id") or companies_resp[0].get("company_id")
        print(f"   Using company_id from API: {test_company_id}")
    
    # Try to get users
    if test_company_id:
        users_resp = await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/users",
            params={"company_id": test_company_id},
            test_name="Get Users (for test data)",
            expected_status=[200, 404, 500]
        )
        if users_resp and isinstance(users_resp, list) and len(users_resp) > 0:
            test_user_id = users_resp[0].get("id")
            print(f"   Using user_id from API: {test_user_id}")
    
    # Try to get calls
    if test_company_id:
        calls_resp = await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/calls",
            params={"company_id": test_company_id, "limit": 1},
            test_name="Get Calls (for test data)",
            expected_status=[200, 404, 500]
        )
        if calls_resp and isinstance(calls_resp, list) and len(calls_resp) > 0:
            test_call_id = calls_resp[0].get("id")
            print(f"   Using call_id from API: {test_call_id}")
    
    # Try to get leads
    if test_company_id:
        leads_resp = await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/leads",
            params={"company_id": test_company_id, "limit": 1},
            test_name="Get Leads (for test data)",
            expected_status=[200, 404, 500]
        )
        if leads_resp and isinstance(leads_resp, list) and len(leads_resp) > 0:
            test_lead_id = leads_resp[0].get("id")
            print(f"   Using lead_id from API: {test_lead_id}")
    
    # Fallback to test UUIDs if no data found
    if not test_company_id:
        test_company_id = "11111111-1111-1111-1111-111111111111"
        print(f"   WARNING: No companies found, using test UUID: {test_company_id}")
    
    return {
        "company_id": test_company_id,
        "user_id": test_user_id,
        "call_id": test_call_id,
        "lead_id": test_lead_id,
        "contact_card_id": None
    }

async def test_all_apis():
    """Test all API endpoints."""
    print("=" * 80)
    print("COMPREHENSIVE API TESTING")
    print("=" * 80)
    
    async with httpx.AsyncClient() as client:
        # Get test data
        test_data = await get_test_data(client)
        company_id = test_data["company_id"]
        user_id = test_data["user_id"]
        call_id = test_data["call_id"]
        lead_id = test_data["lead_id"]
        
        print(f"\nTest Configuration:")
        print(f"   Base URL: {BASE_URL}")
        print(f"   Company ID: {company_id}")
        print(f"   User ID: {user_id}")
        print(f"   Call ID: {call_id}")
        print(f"   Lead ID: {lead_id}")
        
        print("\n" + "=" * 80)
        print("AUTHENTICATION APIs")
        print("=" * 80)
        
        # Auth endpoints
        await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/auth/signup",
            json_data={
                "email": f"test_{uuid4().hex[:8]}@test.com",
                "password": "TestPassword123!",
                "first_name": "Test",
                "last_name": "User",
                "role": "sales_rep"
            },
            expected_status=201,
            test_name="POST /auth/signup"
        )
        
        await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/auth/login",
            json_data={
                "email": "test@example.com",
                "password": "test123"
            },
            expected_status=200,
            test_name="POST /auth/login"
        )
        
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/auth/me",
            test_name="GET /auth/me"
        )
        
        print("\n" + "=" * 80)
        print("CALL APIs")
        print("=" * 80)
        
        # Calls endpoints
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/calls",
            params={"company_id": company_id, "skip": 0, "limit": 10},
            test_name="GET /calls"
        )
        
        if call_id:
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/calls/{call_id}",
                test_name="GET /calls/{call_id}"
            )
        
        print("\n" + "=" * 80)
        print("USER APIs")
        print("=" * 80)
        
        # Users endpoints
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/users",
            params={"company_id": company_id},
            test_name="GET /users"
        )
        
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/users/companies",
            test_name="GET /users/companies"
        )
        
        if user_id:
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/users/{user_id}",
                test_name="GET /users/{user_id}"
            )
        
        print("\n" + "=" * 80)
        print("LEAD APIs")
        print("=" * 80)
        
        # Leads endpoints
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/leads",
            params={"company_id": company_id, "skip": 0, "limit": 10},
            test_name="GET /leads"
        )
        
        if lead_id:
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/leads/{lead_id}",
                test_name="GET /leads/{lead_id}"
            )
        
        print("\n" + "=" * 80)
        print("ANALYTICS APIs")
        print("=" * 80)
        
        # Analytics endpoints
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/analytics/top-objections",
            params={"company_id": company_id},
            test_name="GET /analytics/top-objections"
        )
        
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/analytics/objection-calls",
            params={"objection": "price", "company_id": company_id},
            test_name="GET /analytics/objection-calls"
        )
        
        print("\n" + "=" * 80)
        print("METRICS APIs")
        print("=" * 80)
        
        # Metrics endpoints
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/metrics/exec/company-overview",
            params={"company_id": company_id},
            test_name="GET /metrics/exec/company-overview"
        )
        
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/metrics/company/performance",
            params={"company_id": company_id},
            test_name="GET /metrics/company/performance"
        )
        
        print("\n" + "=" * 80)
        print("CALL PROCESSING APIs (Shunya)")
        print("=" * 80)
        
        # Call Processing endpoints
        if call_id:
            # Test call summary
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/call-processing/summary/{call_id}",
                test_name="GET /call-processing/summary/{call_id}",
                expected_status=[200, 404, 503]
            )
            
            # Test call chunks
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/call-processing/chunks/{call_id}",
                test_name="GET /call-processing/chunks/{call_id}",
                expected_status=[200, 404, 503]
            )
        
        # Test process call (submit a new call for processing)
        process_call_resp = await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/call-processing/process",
            json_data={
                "call_id": str(uuid4()),
                "company_id": company_id,
                "audio_url": "https://example.com/test-audio.mp3",
                "phone_number": "+1234567890",
                "duration": 120,
                "call_date": datetime.utcnow().isoformat(),
                "metadata": {},
                "options": {}
            },
            test_name="POST /call-processing/process",
            expected_status=[202, 400, 503]
        )
        
        # If we got a job_id, test status endpoint
        job_id = None
        if process_call_resp and isinstance(process_call_resp, dict):
            job_id = process_call_resp.get("job_id")
        
        if job_id:
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/call-processing/status/{job_id}",
                test_name="GET /call-processing/status/{job_id}",
                expected_status=[200, 404, 503]
            )
        
        print("\n" + "=" * 80)
        print("ASK OTTO APIs (Shunya)")
        print("=" * 80)
        
        # Create a new conversation
        conversation_resp = await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/ask-otto/conversations",
            json_data={
                "company_id": company_id,
                "context": {}
            },
            test_name="POST /ask-otto/conversations",
            expected_status=[201, 200, 400, 503]
        )
        
        conversation_id = None
        if conversation_resp and isinstance(conversation_resp, dict):
            conversation_id = conversation_resp.get("id") or conversation_resp.get("conversation_id")
            # Convert to UUID string if needed
            if conversation_id and not isinstance(conversation_id, str):
                conversation_id = str(conversation_id)
        
        if conversation_id:
            # Send a message
            await test_endpoint(
                client, "POST", f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}/messages",
                json_data={
                    "message": "What are the top objections this week?"
                },
                test_name="POST /ask-otto/conversations/{id}/messages",
                expected_status=[200, 201, 400, 404, 503]
            )
            
            # Get conversation details
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}",
                test_name="GET /ask-otto/conversations/{id}",
                expected_status=[200, 404]
            )
            
            # Get messages
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}/messages",
                test_name="GET /ask-otto/conversations/{id}/messages",
                expected_status=[200, 404]
            )
            
            # Delete conversation (cleanup)
            await test_endpoint(
                client, "DELETE", f"{BASE_URL}{API_PREFIX}/ask-otto/conversations/{conversation_id}",
                test_name="DELETE /ask-otto/conversations/{id}",
                expected_status=[200, 204, 404]
            )
        
        print("\n" + "=" * 80)
        print("INSIGHTS APIs (Shunya)")
        print("=" * 80)
        
        # Generate insights (async job)
        from datetime import timedelta
        week_end = date.today()
        week_start = week_end - timedelta(days=7)
        
        generate_insights_resp = await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/insights/generate",
            json_data={
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "company_ids": [company_id],
                "insight_types": ["company", "customer", "objection"],
                "options": {}
            },
            test_name="POST /insights/generate",
            expected_status=[202, 400, 503]
        )
        
        # Get job status if we got a job_id
        insight_job_id = None
        if generate_insights_resp and isinstance(generate_insights_resp, dict):
            insight_job_id = generate_insights_resp.get("job_id")
        
        if insight_job_id:
            await test_endpoint(
                client, "GET", f"{BASE_URL}{API_PREFIX}/insights/status/{insight_job_id}",
                test_name="GET /insights/status/{job_id}",
                expected_status=[200, 404, 503]
            )
        
        # Get current company insight
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/insights/company/{company_id}/current",
            test_name="GET /insights/company/{id}/current",
            expected_status=[200, 404, 503]
        )
        
        # Get customer insights
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/insights/customers",
            params={"company_id": company_id, "page": 1, "limit": 10},
            test_name="GET /insights/customers",
            expected_status=[200, 404, 503]
        )
        
        # Get objection insights
        await test_endpoint(
            client, "GET", f"{BASE_URL}{API_PREFIX}/insights/objections/{company_id}",
            test_name="GET /insights/objections/{id}",
            expected_status=[200, 404, 503]
        )
        
        print("\n" + "=" * 80)
        print("RAG APIs")
        print("=" * 80)
        
        # RAG endpoints
        await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/rag/ask-otto",
            json_data={
                "query": "What are the top objections?",
                "context": {}
            },
            test_name="POST /rag/ask-otto",
            expected_status=[200, 503]
        )
        
        print("\n" + "=" * 80)
        print("WEBHOOK APIs")
        print("=" * 80)
        
        # Webhook endpoints (test with minimal data)
        await test_endpoint(
            client, "POST", f"{BASE_URL}{API_PREFIX}/webhooks/telephony/call-complete",
            json_data={
                "company_id": company_id,
                "phone_number": "+1234567890",
                "audio_url": "https://example.com/audio.mp3",
                "call_type": "csr_call",
                "missed_call": False,
                "duration_seconds": 60
            },
            test_name="POST /webhooks/telephony/call-complete",
            expected_status=[200, 201, 400]  # 400 if validation fails
        )
        
        # Print summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Passed: {len(test_results['passed'])}")
        print(f"Failed: {len(test_results['failed'])}")
        print(f"Skipped: {len(test_results['skipped'])}")
        print(f"Total: {len(test_results['passed']) + len(test_results['failed']) + len(test_results['skipped'])}")
        
        if test_results['failed']:
            print("\nFailed Tests:")
            for failure in test_results['failed']:
                print(f"   - {failure}")
        
        if test_results['skipped']:
            print("\nSkipped Tests:")
            for skip in test_results['skipped']:
                print(f"   - {skip}")
        
        print("\n" + "=" * 80)
        
        return len(test_results['failed']) == 0

if __name__ == "__main__":
    success = asyncio.run(test_all_apis())
    exit(0 if success else 1)
