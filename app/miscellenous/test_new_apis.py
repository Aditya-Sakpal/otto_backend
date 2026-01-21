"""
Test script for newly created APIs.

Tests:
1. GET /api/v1/leads/{lead_id}/details - Lead details API
2. POST /api/v1/leads/{lead_id}/assign - Lead assignment API
3. GET /api/v1/calls/by-objection/self?objection={objection} - Objection details API

Uses real data from seed_dummy_data.sql
"""
import asyncio
import httpx
import json
from uuid import UUID

# Test data from seed_dummy_data.sql
BASE_URL = "http://127.0.0.1:8000/api/v1"
COMPANY_ID = "11111111-1111-1111-1111-111111111111"
LEAD_ID = "20000000-0000-0000-0000-000000000001"  # Qualified booked lead
LEAD_ID_UNASSIGNED = "20000000-0000-0000-0000-000000000004"  # New lead (unassigned)
SALES_REP_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"  # Mike Salesman
CSR_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"  # Lisa Support

# Get access token by logging in
async def get_access_token():
    """Get access token by logging in"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{BASE_URL}/auth/login"
        payload = {
            "email": "sales1@acme.com",
            "password": "SecurePassword123!"  # Default password from seed data
        }
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                return data.get("access_token", "")
            else:
                print(f"Login failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Login error: {e}")
            return None

ACCESS_TOKEN = None  # Will be set by get_access_token()


async def test_lead_details():
    """Test GET /api/v1/leads/{lead_id}/details"""
    print("\n" + "="*60)
    print("TEST 1: GET /api/v1/leads/{lead_id}/details")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{BASE_URL}/leads/{LEAD_ID}/details"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}" if ACCESS_TOKEN else "",
        }
        
        try:
            response = await client.get(url, headers=headers)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\nResponse Structure:")
                print(f"  - Lead ID: {data.get('id')}")
                print(f"  - Contact: {data.get('contact', {}).get('first_name')} {data.get('contact', {}).get('last_name')}")
                print(f"  - Agent: {data.get('agent', {}).get('first_name') if data.get('agent') else 'None'}")
                print(f"  - Conversations: {len(data.get('conversations', []))} conversations")
                print(f"  - Overall Engagement Summary: {data.get('overall_engagement', {}).get('summary', 'N/A')[:100]}...")
                print("\nFull Response:")
                print(json.dumps(data, indent=2, default=str))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_lead_assignment():
    """Test POST /api/v1/leads/{lead_id}/assign"""
    print("\n" + "="*60)
    print("TEST 2: POST /api/v1/leads/{lead_id}/assign")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{BASE_URL}/leads/{LEAD_ID_UNASSIGNED}/assign"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}" if ACCESS_TOKEN else "",
            "Content-Type": "application/json",
        }
        payload = {
            "sales_rep_id": SALES_REP_ID
        }
        
        try:
            response = await client.post(url, headers=headers, json=payload)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\nResponse:")
                print(f"  - Lead ID: {data.get('lead', {}).get('id')}")
                print(f"  - Assigned Rep ID: {data.get('lead', {}).get('assigned_rep_id')}")
                print(f"  - Assigned By: {data.get('assigned_by')}")
                print(f"  - Assigned At: {data.get('assigned_at')}")
                print("\nFull Response:")
                print(json.dumps(data, indent=2, default=str))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_calls_by_objection():
    """Test GET /api/v1/calls/by-objection/self?objection={objection}"""
    print("\n" + "="*60)
    print("TEST 3: GET /api/v1/calls/by-objection/self?objection=authority")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{BASE_URL}/calls/by-objection/self"
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}" if ACCESS_TOKEN else "",
        }
        params = {
            "objection": "authority",
            "company_id": COMPANY_ID,
        }
        
        try:
            response = await client.get(url, headers=headers, params=params)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("\nResponse Structure:")
                print(f"  - Objection: {data.get('objection')}")
                print(f"  - Calls: {len(data.get('calls', []))} calls")
                print(f"  - Unbooked Leads: {len(data.get('unbooked_leads', []))} leads")
                print(f"  - Most Coaching Need: {len(data.get('most_coaching_need', []))} CSRs")
                
                if data.get('calls'):
                    print("\nFirst Call:")
                    first_call = data['calls'][0]
                    print(f"  - Contact: {first_call.get('contact_name')}")
                    print(f"  - Recording URL: {first_call.get('call_recording_url')}")
                
                if data.get('most_coaching_need'):
                    print("\nMost Coaching Need:")
                    for csr in data['most_coaching_need'][:3]:
                        print(f"  - {csr.get('csr_name')}: {csr.get('unbooked_calls')} unbooked calls")
                
                print("\nFull Response:")
                print(json.dumps(data, indent=2, default=str))
                return True
            else:
                print(f"Error: {response.text}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False


async def test_all_objections():
    """Test all objection types"""
    print("\n" + "="*60)
    print("TEST 4: Testing all objection types")
    print("="*60)
    
    objections = ["authority", "price", "timing", "competitor", "need"]
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for objection in objections:
            print(f"\nTesting objection: {objection}")
            url = f"{BASE_URL}/calls/by-objection/self"
            headers = {
                "Authorization": f"Bearer {ACCESS_TOKEN}" if ACCESS_TOKEN else "",
            }
            params = {
                "objection": objection,
                "company_id": COMPANY_ID,
            }
            
            try:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code == 200:
                    data = response.json()
                    print(f"  - Calls: {len(data.get('calls', []))}")
                    print(f"  - Unbooked Leads: {len(data.get('unbooked_leads', []))}")
                    print(f"  - CSRs Needing Coaching: {len(data.get('most_coaching_need', []))}")
                else:
                    print(f"  - Error: {response.status_code} - {response.text[:100]}")
            except Exception as e:
                print(f"  - Error: {e}")


async def main():
    """Run all tests"""
    global ACCESS_TOKEN
    
    print("\n" + "="*60)
    print("TESTING NEWLY CREATED APIs")
    print("="*60)
    print("\nUsing test data from seed_dummy_data.sql:")
    print(f"  - Company ID: {COMPANY_ID}")
    print(f"  - Lead ID: {LEAD_ID}")
    print(f"  - Sales Rep ID: {SALES_REP_ID}")
    
    # Get access token
    print("\nLogging in to get access token...")
    ACCESS_TOKEN = await get_access_token()
    
    if not ACCESS_TOKEN:
        print("\nERROR: Failed to get access token. Make sure:")
        print("  1. Server is running on http://127.0.0.1:8000")
        print("  2. Database has seed data (run seed_dummy_data.sql)")
        print("  3. User sales1@acme.com exists with password SecurePassword123!")
        return
    
    print("Access token obtained successfully!")
    
    results = []
    
    # Test 1: Lead Details
    results.append(await test_lead_details())
    
    # Test 2: Lead Assignment
    results.append(await test_lead_assignment())
    
    # Test 3: Calls by Objection
    results.append(await test_calls_by_objection())
    
    # Test 4: All Objections
    await test_all_objections()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests Passed: {sum(results)}/{len(results)}")
    print(f"Tests Failed: {len(results) - sum(results)}/{len(results)}")


if __name__ == "__main__":
    asyncio.run(main())
