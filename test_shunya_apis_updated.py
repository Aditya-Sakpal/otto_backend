"""
Test script for updated Shunya APIs.

Tests all the new and updated endpoints according to the new API documentation.
"""
import asyncio
import httpx
import json
from typing import Dict, Any

# Shunya API configuration
BASE_URL = "https://ottoai.shunyalabs.ai"
API_KEY = "5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"

# Test data
COMPANY_ID = "company_xyz789"
CALL_ID = "call_abc123"
JOB_ID = "job_a1b2c3d4e5f6"
CONVERSATION_ID = "conv_x1y2z3a4b5c6"


def get_headers(company_id: str = None) -> Dict[str, str]:
    """Get headers for Shunya API requests."""
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    if company_id:
        headers["X-Company-Id"] = company_id
    return headers


async def test_health_check():
    """Test GET /health"""
    print("\n" + "="*60)
    print("TEST 1: GET /health")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("Response:", json.dumps(response.json(), indent=2))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_root_info():
    """Test GET /"""
    print("\n" + "="*60)
    print("TEST 2: GET /")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/")
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("Response:", json.dumps(response.json(), indent=2))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_api_status():
    """Test GET /api/v1/status"""
    print("\n" + "="*60)
    print("TEST 3: GET /api/v1/status")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/status",
                headers=get_headers(),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("Response:", json.dumps(response.json(), indent=2))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_scheduler_status():
    """Test GET /api/v1/scheduler/status"""
    print("\n" + "="*60)
    print("TEST 4: GET /api/v1/scheduler/status")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/scheduler/status",
                headers=get_headers(),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print("Response:", json.dumps(response.json(), indent=2))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_call_processing_status():
    """Test GET /api/v1/call-processing/status/{job_id}"""
    print("\n" + "="*60)
    print("TEST 5: GET /api/v1/call-processing/status/{job_id}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/call-processing/status/{JOB_ID}",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Job ID: {data.get('job_id')}")
                print(f"Status: {data.get('status')}")
                print(f"Progress: {data.get('progress', {}).get('percent')}%")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_call_summary():
    """Test GET /api/v1/call-processing/summary/{call_id}"""
    print("\n" + "="*60)
    print("TEST 6: GET /api/v1/call-processing/summary/{call_id}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/call-processing/summary/{CALL_ID}",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Call ID: {data.get('call_id')}")
                print(f"Status: {data.get('status')}")
                print("Summary available:", "summary" in data)
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_call_chunks():
    """Test GET /api/v1/call-processing/chunks/{call_id}"""
    print("\n" + "="*60)
    print("TEST 7: GET /api/v1/call-processing/chunks/{call_id}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/call-processing/chunks/{CALL_ID}",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Call ID: {data.get('call_id')}")
                print(f"Total Chunks: {data.get('total_chunks')}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_insights_company():
    """Test GET /api/v1/insights/company/{company_id}/current"""
    print("\n" + "="*60)
    print("TEST 8: GET /api/v1/insights/company/{company_id}/current")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/insights/company/{COMPANY_ID}/current",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Company ID: {data.get('company_id')}")
                print(f"Week: {data.get('week_start')} to {data.get('week_end')}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_insights_customers():
    """Test GET /api/v1/insights/customers"""
    print("\n" + "="*60)
    print("TEST 9: GET /api/v1/insights/customers")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/insights/customers",
                params={"company_id": COMPANY_ID, "limit": 10},
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Total Customers: {data.get('total_customers')}")
                print(f"Customers Returned: {len(data.get('customers', []))}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_insights_objections():
    """Test GET /api/v1/insights/objections/{company_id}"""
    print("\n" + "="*60)
    print("TEST 10: GET /api/v1/insights/objections/{company_id}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/insights/objections/{COMPANY_ID}",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Company ID: {data.get('company_id')}")
                print(f"Total Categories: {data.get('total_categories')}")
                print(f"Objections: {len(data.get('objections', []))}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_ask_otto_conversation():
    """Test POST /api/v1/ask-otto/conversations"""
    print("\n" + "="*60)
    print("TEST 11: POST /api/v1/ask-otto/conversations")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            payload = {
                "company_id": COMPANY_ID,
                "user_id": "user_abc123",
                "metadata": {
                    "source": "test_script",
                    "user_role": "sales_manager"
                }
            }
            response = await client.post(
                f"{BASE_URL}/api/v1/ask-otto/conversations",
                json=payload,
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 201:
                data = response.json()
                print(f"Conversation ID: {data.get('conversation_id')}")
                print(f"Company ID: {data.get('company_id')}")
                return True, data.get('conversation_id')
            else:
                print(f"Error: {response.text}")
                return False, None
        except Exception as e:
            print(f"Error: {e}")
            return False, None


async def test_list_sop_documents():
    """Test GET /api/v1/sop/documents"""
    print("\n" + "="*60)
    print("TEST 12: GET /api/v1/sop/documents")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/sop/documents",
                params={"company_id": COMPANY_ID, "limit": 10},
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Total: {data.get('total')}")
                print(f"Documents: {len(data.get('documents', []))}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_sop_metrics():
    """Test GET /api/v1/sop/metrics/{company_id}"""
    print("\n" + "="*60)
    print("TEST 13: GET /api/v1/sop/metrics/{company_id}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BASE_URL}/api/v1/sop/metrics/{COMPANY_ID}",
                headers=get_headers(COMPANY_ID),
            )
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Company ID: {data.get('company_id')}")
                print(f"Active SOPs: {len(data.get('active_sops', []))}")
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("TESTING UPDATED SHUNYA APIs")
    print("="*60)
    print(f"\nBase URL: {BASE_URL}")
    print(f"API Key: {API_KEY[:10]}...")
    print(f"Company ID: {COMPANY_ID}")
    
    results = []
    
    # Health & Status APIs
    results.append(await test_health_check())
    results.append(await test_root_info())
    results.append(await test_api_status())
    results.append(await test_scheduler_status())
    
    # Call Processing APIs
    results.append(await test_call_processing_status())
    results.append(await test_call_summary())
    results.append(await test_call_chunks())
    
    # Insights APIs
    results.append(await test_insights_company())
    results.append(await test_insights_customers())
    results.append(await test_insights_objections())
    
    # Ask Otto APIs
    success, conv_id = await test_ask_otto_conversation()
    results.append(success)
    
    # SOP APIs
    results.append(await test_list_sop_documents())
    results.append(await test_sop_metrics())
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests Passed: {sum(results)}/{len(results)}")
    print(f"Tests Failed: {len(results) - sum(results)}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
