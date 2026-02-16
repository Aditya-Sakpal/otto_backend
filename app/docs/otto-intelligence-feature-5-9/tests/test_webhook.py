#!/usr/bin/env python3
"""
Webhook Test Script

Tests webhook endpoints to verify they can receive messages.
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Optional

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


async def test_webhook_endpoint(
    webhook_url: str,
    test_name: str = "Generic Test",
    payload: Optional[dict] = None
):
    """
    Test a webhook endpoint with a sample payload.
    
    Args:
        webhook_url: The webhook URL to test
        test_name: Name of the test
        payload: Custom payload to send (uses default if None)
    """
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST: {test_name}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"URL: {webhook_url}")
    
    # Default payload if not provided
    if payload is None:
        payload = {
            "job_id": "test-job-123",
            "status": "completed",
            "event_type": "call_processing",
            "timestamp": datetime.utcnow().isoformat(),
            "call_id": "test-call-456",
            "summary_url": "/api/v1/call-processing/summary/test-call-456",
            "chunks_url": "/api/v1/call-processing/chunks/test-call-456"
        }
    
    print(f"\n{YELLOW}Payload:{RESET}")
    print(json.dumps(payload, indent=2))
    
    try:
        print(f"\n{YELLOW}Sending POST request...{RESET}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Otto-Intelligence-Webhook-Test/1.0"
                }
            )
            
            print(f"\n{YELLOW}Response:{RESET}")
            print(f"Status Code: {response.status_code}")
            print(f"Headers: {dict(response.headers)}")
            
            # Try to parse response body
            try:
                response_json = response.json()
                print(f"\n{YELLOW}Response Body (JSON):{RESET}")
                print(json.dumps(response_json, indent=2))
            except Exception:
                response_text = response.text
                print(f"\n{YELLOW}Response Body (Text):{RESET}")
                print(response_text[:500])  # First 500 chars
            
            # Evaluate result
            if 200 <= response.status_code < 300:
                print(f"\n{GREEN}✅ SUCCESS: Webhook accepted the message{RESET}")
                return True
            elif response.status_code == 500:
                print(f"\n{RED}❌ FAILURE: Server returned 500 Internal Server Error{RESET}")
                print(f"{RED}   This means the endpoint received our request but crashed processing it.{RESET}")
                return False
            elif response.status_code == 400:
                print(f"\n{RED}❌ FAILURE: Bad Request (400){RESET}")
                print(f"{RED}   The endpoint rejected our payload structure.{RESET}")
                return False
            elif response.status_code == 404:
                print(f"\n{RED}❌ FAILURE: Not Found (404){RESET}")
                print(f"{RED}   The endpoint URL does not exist.{RESET}")
                return False
            else:
                print(f"\n{YELLOW}⚠️  WARNING: Unexpected status code {response.status_code}{RESET}")
                return False
    
    except httpx.TimeoutException:
        print(f"\n{RED}❌ FAILURE: Request timed out (>10 seconds){RESET}")
        print(f"{RED}   The endpoint is not responding.{RESET}")
        return False
    
    except httpx.ConnectError as e:
        print(f"\n{RED}❌ FAILURE: Connection error{RESET}")
        print(f"{RED}   Could not connect to the endpoint: {str(e)}{RESET}")
        return False
    
    except Exception as e:
        print(f"\n{RED}❌ FAILURE: Unexpected error{RESET}")
        print(f"{RED}   {type(e).__name__}: {str(e)}{RESET}")
        return False


async def test_minimal_payload(webhook_url: str):
    """Test with a minimal payload to see if it's a payload structure issue."""
    minimal_payload = {
        "test": "Hello from Otto Intelligence",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return await test_webhook_endpoint(
        webhook_url,
        test_name="Minimal Payload Test",
        payload=minimal_payload
    )


async def test_call_processing_completed(webhook_url: str):
    """Test with the exact payload we send for call processing completion."""
    payload = {
        "job_id": "edab31ed-5dbd-4c94-a54e-1184c749c737",
        "status": "completed",
        "event_type": "call_processing",
        "timestamp": datetime.utcnow().isoformat(),
        "call_id": "13277c1f-844e-4366-8e1f-881b8f179c83",
        "summary_url": "/api/v1/call-processing/summary/13277c1f-844e-4366-8e1f-881b8f179c83",
        "chunks_url": "/api/v1/call-processing/chunks/13277c1f-844e-4366-8e1f-881b8f179c83"
    }
    
    return await test_webhook_endpoint(
        webhook_url,
        test_name="Call Processing Completed",
        payload=payload
    )


async def test_call_processing_failed(webhook_url: str):
    """Test with a failure payload."""
    payload = {
        "job_id": "test-job-failed-123",
        "status": "failed",
        "event_type": "call_processing",
        "timestamp": datetime.utcnow().isoformat(),
        "call_id": "test-call-failed-456",
        "error": {
            "message": "Test error message",
            "type": "TestException"
        }
    }
    
    return await test_webhook_endpoint(
        webhook_url,
        test_name="Call Processing Failed",
        payload=payload
    )


async def test_insights_generation(webhook_url: str):
    """Test with insights generation payload."""
    payload = {
        "job_id": "insight-job-123",
        "status": "completed",
        "event_type": "insight_generation",
        "timestamp": datetime.utcnow().isoformat(),
        "company_id": "test-company-123",
        "insights_url": "/api/v1/insights/test-company-123"
    }
    
    return await test_webhook_endpoint(
        webhook_url,
        test_name="Insights Generation",
        payload=payload
    )


async def test_sop_processing(webhook_url: str):
    """Test with SOP processing payload."""
    payload = {
        "job_id": "sop-job-123",
        "status": "completed",
        "event_type": "sop_processing",
        "timestamp": datetime.utcnow().isoformat(),
        "document_id": "test-doc-123",
        "sop_url": "/api/v1/sop/test-doc-123"
    }
    
    return await test_webhook_endpoint(
        webhook_url,
        test_name="SOP Processing",
        payload=payload
    )


async def main():
    """Main test runner."""
    print(f"{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}OTTO INTELLIGENCE - WEBHOOK ENDPOINT TEST SUITE{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    # Webhook URL to test
    webhook_url = "https://otto-backend-stage-8040383b5e71.herokuapp.com/api/v1/webhooks/shoonya/job-complete"
    
    print(f"\nTarget Endpoint: {webhook_url}")
    print(f"\n{YELLOW}Starting tests...{RESET}")
    
    results = []
    
    # Test 1: Minimal payload (simplest test)
    results.append(("Minimal Payload", await test_minimal_payload(webhook_url)))
    
    # Test 2: Call processing completed (actual payload)
    results.append(("Call Processing (Completed)", await test_call_processing_completed(webhook_url)))
    
    # Test 3: Call processing failed
    results.append(("Call Processing (Failed)", await test_call_processing_failed(webhook_url)))
    
    # Test 4: Insights generation
    results.append(("Insights Generation", await test_insights_generation(webhook_url)))
    
    # Test 5: SOP processing
    results.append(("SOP Processing", await test_sop_processing(webhook_url)))
    
    # Summary
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{BLUE}{'='*80}{RESET}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{status} - {test_name}")
    
    print(f"\n{BLUE}Total: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}🎉 All tests passed! The webhook endpoint is working correctly.{RESET}")
    elif passed == 0:
        print(f"\n{RED}⚠️  All tests failed! The webhook endpoint has issues.{RESET}")
        print(f"{YELLOW}Possible causes:{RESET}")
        print(f"  1. Endpoint is down or misconfigured")
        print(f"  2. Endpoint expects different payload structure")
        print(f"  3. Endpoint has internal bugs (500 errors)")
        print(f"  4. Authentication/authorization required")
    else:
        print(f"\n{YELLOW}⚠️  Some tests failed. Check specific test results above.{RESET}")
    
    print(f"\n{BLUE}{'='*80}{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
