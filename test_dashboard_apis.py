"""
Test script to test all dashboard-related APIs and map them to frontend sections.

This script tests all relevant APIs for the dashboard screens shown in the screenshots.
"""
import asyncio
import httpx
import json
from datetime import date, timedelta
from uuid import UUID

# Base URL for the API
BASE_URL = "http://localhost:8001"
COMPANY_ID = "11111111-1111-1111-1111-111111111111"

# Test company ID from seed data
TEST_COMPANY_ID = "11111111-1111-1111-1111-111111111111"


async def test_api(endpoint: str, method: str = "GET", params: dict = None, data: dict = None):
    """Test an API endpoint and return the response."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, params=params, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        print(f"[ERROR] Error {e.response.status_code} for {endpoint}")
        print(f"   Response: {e.response.text[:200]}")
        return None
    except Exception as e:
        print(f"[ERROR] Exception for {endpoint}: {e}")
        return None


async def test_all_apis():
    """Test all dashboard-related APIs."""
    
    print("=" * 80)
    print("DASHBOARD API TESTING & MAPPING")
    print("=" * 80)
    print()
    
    # Calculate date range (last 30 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    results = {}
    
    # ============================================================================
    # 1. DASHBOARD OVERVIEW SECTION
    # ============================================================================
    print("SECTION 1: DASHBOARD OVERVIEW")
    print("-" * 80)
    
    # 1.1 Company Overview (Total Leads, Qualified Leads, Booked Appointments)
    print("\n1.1 Testing: GET /api/v1/metrics/exec/company-overview")
    print("   Purpose: Get total leads, qualified leads, booked appointments")
    result = await test_api(
        "/api/v1/metrics/exec/company-overview",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )
    results["company_overview"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Total Leads: {result.get('total_leads', 'N/A')}")
        print(f"   Qualified Leads: {result.get('qualified_leads', 'N/A')}")
        print(f"   Booked Appointments: {result.get('total_appointments', 'N/A')}")
        print(f"   Total Calls: {result.get('total_calls', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # 1.2 Booking Rate Improvement
    print("\n1.2 Testing: GET /api/v1/metrics/booking-rate-improvement")
    print("   Purpose: Get booking rate improvement graph data")
    result = await test_api(
        "/api/v1/metrics/booking-rate-improvement",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )
    results["booking_rate_improvement"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Current Rate: {result.get('current_rate', 'N/A')}")
        print(f"   Previous Rate: {result.get('previous_rate', 'N/A')}")
        print(f"   Improvement: {result.get('improvement_percentage', 'N/A')}%")
    else:
        print("   [FAIL] Failed")
    
    # 1.3 Bookings Summary
    print("\n1.3 Testing: GET /api/v1/metrics/bookings/summary")
    print("   Purpose: Get bookings summary (total, confirmed, pending, cancelled)")
    result = await test_api(
        "/api/v1/metrics/bookings/summary",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )
    results["bookings_summary"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Total Bookings: {result.get('total_bookings', 'N/A')}")
        print(f"   Confirmed: {result.get('confirmed_bookings', 'N/A')}")
        print(f"   Pending: {result.get('pending_bookings', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # ============================================================================
    # 2. UNBOOKED APPOINTMENTS CARD
    # ============================================================================
    print("\n\nSECTION 2: UNBOOKED APPOINTMENTS CARD")
    print("-" * 80)
    
    # 2.1 Unbooked Leads
    print("\n2.1 Testing: GET /api/v1/metrics/leads/unbooked")
    print("   Purpose: Get unbooked appointments with details")
    result = await test_api(
        "/api/v1/metrics/leads/unbooked",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "limit": 20
        }
    )
    results["unbooked_leads"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Total Unbooked: {result.get('total_unbooked', 'N/A')}")
        leads = result.get('leads', [])
        print(f"   Leads Returned: {len(leads)}")
        if leads:
            print(f"   Sample Lead: {leads[0].get('contact_card', {}).get('first_name', 'N/A')} - {leads[0].get('status', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # 2.2 Leads by Status (qualified_unbooked)
    print("\n2.2 Testing: GET /api/v1/leads?status=qualified_unbooked")
    print("   Purpose: Alternative endpoint for unbooked leads")
    result = await test_api(
        "/api/v1/leads",
        params={
            "company_id": TEST_COMPANY_ID,
            "status": "qualified_unbooked",
            "limit": 20
        }
    )
    results["leads_unbooked"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Leads Returned: {len(result) if isinstance(result, list) else 'N/A'}")
    else:
        print("   [FAIL] Failed")
    
    # ============================================================================
    # 3. TOP OBJECTIONS
    # ============================================================================
    print("\n\nSECTION 3: TOP OBJECTIONS")
    print("-" * 80)
    
    # 3.1 Top Objections (Metrics)
    print("\n3.1 Testing: GET /api/v1/metrics/objections/top")
    print("   Purpose: Get top objections with counts")
    result = await test_api(
        "/api/v1/metrics/objections/top",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "limit": 10
        }
    )
    results["top_objections_metrics"] = result
    if result:
        print(f"   [OK] Success!")
        objections = result.get('objections', [])
        print(f"   Objections Returned: {len(objections)}")
        if objections:
            for obj in objections[:5]:
                print(f"   - {obj.get('objection_type', 'N/A')}: {obj.get('count', 0)} ({obj.get('percentage', 0)}%)")
    else:
        print("   [FAIL] Failed")
    
    # 3.2 Top Objections (Analytics)
    print("\n3.2 Testing: GET /api/v1/analytics/top-objections")
    print("   Purpose: Alternative endpoint for top objections")
    result = await test_api(
        "/api/v1/analytics/top-objections",
        params={
            "company_id": TEST_COMPANY_ID
        }
    )
    results["top_objections_analytics"] = result
    if result:
        print(f"   [OK] Success!")
        objections = result if isinstance(result, list) else result.get('objections', [])
        print(f"   Objections Returned: {len(objections)}")
        if objections:
            for obj in objections[:5]:
                print(f"   - {obj.get('objection_type', 'N/A')}: {obj.get('count', 0)}")
    else:
        print("   [FAIL] Failed")
    
    # 3.3 Objections Summary
    print("\n3.3 Testing: GET /api/v1/metrics/objections/summary")
    print("   Purpose: Get objections summary")
    result = await test_api(
        "/api/v1/metrics/objections/summary",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date)
        }
    )
    results["objections_summary"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Total Objections: {result.get('total_objections', 'N/A')}")
        print(f"   Unique Types: {result.get('unique_types', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # ============================================================================
    # 4. QUEUED LEADS READY FOR BOOKING
    # ============================================================================
    print("\n\nSECTION 4: QUEUED LEADS READY FOR BOOKING")
    print("-" * 80)
    
    # 4.1 Auto-Queued Leads
    print("\n4.1 Testing: GET /api/v1/metrics/csr/auto-queued-leads")
    print("   Purpose: Get auto-queued leads ready for booking")
    result = await test_api(
        "/api/v1/metrics/csr/auto-queued-leads",
        params={
            "company_id": TEST_COMPANY_ID,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "limit": 20
        }
    )
    results["auto_queued_leads"] = result
    if result:
        print(f"   [OK] Success!")
        leads = result.get('leads', [])
        print(f"   Leads Returned: {len(leads)}")
        if leads:
            print(f"   Sample Lead: {leads[0].get('contact_card', {}).get('first_name', 'N/A')} - {leads[0].get('status', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # ============================================================================
    # 5. LEADS BY PRIORITY
    # ============================================================================
    print("\n\nSECTION 5: LEADS BY PRIORITY")
    print("-" * 80)
    
    # 5.1 Leads by Priority
    print("\n5.1 Testing: GET /api/v1/leads?sort=priority")
    print("   Purpose: Get leads sorted by priority/urgency")
    result = await test_api(
        "/api/v1/leads",
        params={
            "company_id": TEST_COMPANY_ID,
            "sort": "priority",
            "limit": 20
        }
    )
    results["leads_priority"] = result
    if result:
        print(f"   [OK] Success!")
        print(f"   Leads Returned: {len(result) if isinstance(result, list) else 'N/A'}")
        if isinstance(result, list) and result:
            print(f"   Sample Lead: {result[0].get('contact_card', {}).get('first_name', 'N/A')} - Priority: {result[0].get('priority', 'N/A')}")
    else:
        print("   [FAIL] Failed")
    
    # 5.2 Objection Calls (for objection & response column)
    print("\n5.2 Testing: GET /api/v1/analytics/objection-calls")
    print("   Purpose: Get calls with objections (for objection & response column)")
    result = await test_api(
        "/api/v1/analytics/objection-calls",
        params={
            "company_id": TEST_COMPANY_ID,
            "objection": "price"
        }
    )
    results["objection_calls"] = result
    if result:
        print(f"   [OK] Success!")
        calls = result if isinstance(result, list) else result.get('calls', [])
        print(f"   Calls Returned: {len(calls)}")
    else:
        print("   [FAIL] Failed")
    
    # ============================================================================
    # SUMMARY & MAPPING
    # ============================================================================
    print("\n\n" + "=" * 80)
    print("API TO FRONTEND SECTION MAPPING")
    print("=" * 80)
    print()
    
    mapping = {
        "Dashboard Overview Section": [
            "GET /api/v1/metrics/exec/company-overview - Total Leads, Qualified Leads, Booked Appointments",
            "GET /api/v1/metrics/booking-rate-improvement - Booking Rate Improvement Graph",
            "GET /api/v1/metrics/bookings/summary - Bookings Summary (optional)"
        ],
        "Unbooked Appointments Card": [
            "GET /api/v1/metrics/leads/unbooked - Primary endpoint (includes details, reason, last spoken)",
            "GET /api/v1/leads?status=qualified_unbooked - Alternative endpoint"
        ],
        "Top Objections": [
            "GET /api/v1/metrics/objections/top - Primary endpoint (includes counts and percentages)",
            "GET /api/v1/analytics/top-objections - Alternative endpoint",
            "GET /api/v1/metrics/objections/summary - Summary statistics (optional)"
        ],
        "Queued Leads Ready for Booking": [
            "GET /api/v1/metrics/csr/auto-queued-leads - Primary endpoint (prioritized leads)"
        ],
        "Leads by Priority": [
            "GET /api/v1/leads?sort=priority - Primary endpoint (leads sorted by priority/urgency)",
            "GET /api/v1/analytics/objection-calls?objection={type} - For objection & response column"
        ]
    }
    
    for section, apis in mapping.items():
        print(f"[*] {section}:")
        for api in apis:
            print(f"   - {api}")
        print()
    
    print("=" * 80)
    print("TESTING COMPLETE")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    asyncio.run(test_all_apis())
