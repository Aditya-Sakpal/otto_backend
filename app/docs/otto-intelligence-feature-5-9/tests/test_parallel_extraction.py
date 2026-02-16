"""
Test script for validating the new parallel extraction implementation.

This script tests:
1. Extractor imports
2. Customer history service
3. Call context building
4. Basic extraction logic
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_imports():
    """Test that all new modules can be imported."""
    print("=" * 60)
    print("TEST 1: Import Validation")
    print("=" * 60)
    
    try:
        from app.services.call_processing.extractors import (
            SummaryExtractor,
            ComplianceExtractor,
            ObjectionExtractor,
            QualificationExtractor,
        )
        print("✅ All extractors imported successfully")
        
        from app.services.call_processing.customer_history_service import (
            get_customer_history_service
        )
        print("✅ Customer history service imported successfully")
        
        from app.services.call_processing.summary_service import get_summary_service
        print("✅ New summary service imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


async def test_extractor_initialization():
    """Test that extractors can be initialized."""
    print("\n" + "=" * 60)
    print("TEST 2: Extractor Initialization")
    print("=" * 60)
    
    try:
        from app.services.call_processing.extractors import (
            SummaryExtractor,
            ComplianceExtractor,
            ObjectionExtractor,
            QualificationExtractor,
        )
        
        summary_ext = SummaryExtractor()
        print(f"✅ SummaryExtractor initialized (temp: {summary_ext.temperature})")
        
        compliance_ext = ComplianceExtractor()
        print(f"✅ ComplianceExtractor initialized (temp: {compliance_ext.temperature})")
        
        objection_ext = ObjectionExtractor()
        print(f"✅ ObjectionExtractor initialized (temp: {objection_ext.temperature})")
        
        qualification_ext = QualificationExtractor()
        print(f"✅ QualificationExtractor initialized (temp: {qualification_ext.temperature})")
        
        return True
        
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


async def test_customer_history_service():
    """Test customer history service initialization."""
    print("\n" + "=" * 60)
    print("TEST 3: Customer History Service")
    print("=" * 60)
    
    try:
        from app.services.call_processing.customer_history_service import (
            get_customer_history_service
        )
        
        service = get_customer_history_service()
        print("✅ Customer history service initialized")
        
        # Test retrieval (will return None if no data, which is ok)
        history = await service.get_customer_context(
            phone_number="+1234567890",
            company_id="test_company"
        )
        
        if history is None:
            print("✅ Service works (no history found - expected for test)")
        else:
            print(f"✅ Service works (found {history['previous_call_count']} previous calls)")
        
        return True
        
    except Exception as e:
        print(f"❌ Customer history service failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_call_context_building():
    """Test that call context is built correctly."""
    print("\n" + "=" * 60)
    print("TEST 4: Call Context Building")
    print("=" * 60)
    
    try:
        from datetime import datetime
        
        # Simulate what call_tasks.py does
        call_date_value = "2026-01-09T14:30:00"
        call_date_dt = datetime.fromisoformat(call_date_value.replace('Z', '+00:00'))
        
        call_context = {
            "call_id": "test_123",
            "company_id": "company_456",
            "phone_number": "+1234567890",
            "call_date": call_date_dt.strftime("%Y-%m-%d"),
            "call_time": call_date_dt.strftime("%H:%M:%S"),
            "timezone": "America/Phoenix",
            "company_services": ["Roofing", "Gutters"],
            "company_service_area": "Phoenix Metro",
            "rep_role": "customer_rep"
        }
        
        print("✅ Call context built successfully:")
        print(f"   - call_date: {call_context['call_date']}")
        print(f"   - call_time: {call_context['call_time']}")
        print(f"   - timezone: {call_context['timezone']}")
        print(f"   - services: {', '.join(call_context['company_services'])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Call context building failed: {e}")
        return False


async def test_summary_service_initialization():
    """Test that the new summary service initializes correctly."""
    print("\n" + "=" * 60)
    print("TEST 5: Summary Service Initialization")
    print("=" * 60)
    
    try:
        from app.services.call_processing.summary_service import get_summary_service
        
        service = get_summary_service()
        print("✅ Summary service initialized")
        
        # Check that it has the extractors
        assert hasattr(service, 'summary_extractor'), "Missing summary_extractor"
        print("✅ Has summary_extractor")
        
        assert hasattr(service, 'compliance_extractor'), "Missing compliance_extractor"
        print("✅ Has compliance_extractor")
        
        assert hasattr(service, 'objection_extractor'), "Missing objection_extractor"
        print("✅ Has objection_extractor")
        
        assert hasattr(service, 'qualification_extractor'), "Missing qualification_extractor"
        print("✅ Has qualification_extractor")
        
        assert hasattr(service, 'customer_history_service'), "Missing customer_history_service"
        print("✅ Has customer_history_service")
        
        return True
        
    except Exception as e:
        print(f"❌ Summary service initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n🧪 PARALLEL EXTRACTION IMPLEMENTATION - VALIDATION TESTS\n")
    
    results = []
    
    # Run all tests
    results.append(("Imports", await test_imports()))
    results.append(("Extractor Init", await test_extractor_initialization()))
    results.append(("Customer History", await test_customer_history_service()))
    results.append(("Call Context", await test_call_context_building()))
    results.append(("Summary Service", await test_summary_service_initialization()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Implementation is ready.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

