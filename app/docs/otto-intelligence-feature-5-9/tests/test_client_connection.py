"""
Quick API Connection Test Script for Shunya API Clients
Run this to verify your API key and connection are working correctly.
"""
import asyncio
import httpx

# ============ CONFIGURATION ============
API_KEY = "your-api-key-here"  # ← Replace with your actual API key
BASE_URL = "https://ottoai.shunyalabs.ai"  # ← Replace with actual base URL
# ======================================


async def test_connection():
    """Test API connection and authentication"""
    
    print("=" * 60)
    print("🔧 SHUNYA API CONNECTION TEST")
    print("=" * 60)
    
    
    print(f"\n📍 Base URL: {BASE_URL}")
    print(f"🔑 API Key: {API_KEY[:8]}...{API_KEY[-4:]}")
    print(f"🔑 API Key Length: {len(API_KEY)} characters")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    print("\n" + "=" * 60)
    print("TEST 1: Health Check (No Auth Required)")
    print("=" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BASE_URL}/health")
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Response: {response.json()}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "=" * 60)
    print("TEST 2: API Status (Auth Required)")
    print("=" * 60)
    print(f"Headers being sent: {headers}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{BASE_URL}/api/v1/status",
                headers=headers
            )
            
            if response.status_code == 200:
                print(f"✅ SUCCESS! Status: {response.status_code}")
                print(f"✅ Response: {response.json()}")
                print("\n🎉 Your API key is working correctly!")
            else:
                print(f"❌ FAILED! Status: {response.status_code}")
                print(f"❌ Response: {response.json()}")
                
                if response.status_code == 401:
                    print("\n💡 TIP: Your API key is missing or incorrect")
                    print("   - Check for typos in the API key")
                    print("   - Check for extra spaces/newlines")
                    print("   - Verify the key matches your .env file")
                    
    except Exception as e:
        print(f"❌ Failed: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_connection())

