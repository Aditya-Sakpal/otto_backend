#!/bin/bash
# Simplified Feature 1 End-to-End Test with Local Audio File

set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
AUDIO_FILE="/home/uwcuser/otto-intelligence/Mock Call Sample Recording With Call Flow Guide_16khz.wav"
TEST_CALL_ID="test_call_$(date +%s)"
TEST_COMPANY_ID="test_company_123"

echo "==========================================="
echo "Feature 1: Call Processing Pipeline Test"
echo "==========================================="
echo ""
echo "Test Call ID: $TEST_CALL_ID"
echo "Audio File: $AUDIO_FILE"
echo ""

# Check if audio file exists
if [ ! -f "$AUDIO_FILE" ]; then
    echo "ERROR: Audio file not found: $AUDIO_FILE"
    exit 1
fi

# 1. Health check
echo "1. Testing Health Endpoint..."
HEALTH_RESPONSE=$(curl -s "$BASE_URL/health")
echo "Response: $HEALTH_RESPONSE"
echo ""

# 2. Submit call for processing with local file path
echo "2. Submitting call for processing..."
PROCESS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/v1/call-processing/process" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "'"$TEST_CALL_ID"'",
    "company_id": "'"$TEST_COMPANY_ID"'",
    "audio_url": "'"$AUDIO_FILE"'",
    "phone_number": "+14805551234",
    "duration": 300,
    "metadata": {
      "rep_name": "Travis",
      "customer_name": "Kevin",
      "call_type": "inbound"
    },
    "options": {
      "skip_rag_indexing": false,
      "skip_summary_generation": false,
      "priority": "normal"
    }
  }')

HTTP_STATUS=$(echo "$PROCESS_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
RESPONSE_BODY=$(echo "$PROCESS_RESPONSE" | sed '/HTTP_STATUS/d')

echo "HTTP Status: $HTTP_STATUS"
echo "Response Body:"
echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
echo ""

if [ "$HTTP_STATUS" != "202" ]; then
    echo "ERROR: Expected 202, got $HTTP_STATUS"
    exit 1
fi

# Extract job_id from response
JOB_ID=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)
if [ -z "$JOB_ID" ]; then
    echo "ERROR: Could not extract job_id from response"
    exit 1
fi

echo "Job ID: $JOB_ID"
echo ""

# 3. Poll for completion
echo "3. Polling for job completion (max 10 minutes)..."
MAX_ATTEMPTS=120  # 10 minutes max (5 second intervals)
ATTEMPT=0
STATUS="queued"

while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ] && [ "$STATUS" != "completed" ] && [ "$STATUS" != "failed" ]; do
    sleep 5
    ATTEMPT=$((ATTEMPT + 1))
    
    STATUS_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/status/$JOB_ID" \
      -H "X-API-Key: $API_KEY")
    
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")
    PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('percent', 0))" 2>/dev/null || echo "0")
    CURRENT_STEP=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('progress', {}).get('current_step', ''))" 2>/dev/null || echo "unknown")
    
    echo "Attempt $ATTEMPT/$MAX_ATTEMPTS - Status: $STATUS, Progress: $PROGRESS%, Step: $CURRENT_STEP"
    
    # If there's an error in the status
    if [ "$STATUS" = "error" ]; then
        echo "ERROR: Status check returned error"
        echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
        break
    fi
done

echo ""
echo "================================"
echo "Final Status: $STATUS"
echo "================================"
echo ""
echo "Full Status Response:"
echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
echo ""

# If failed, show error details
if [ "$STATUS" = "failed" ]; then
    echo "ERROR DETAILS:"
    echo "$STATUS_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(json.dumps(data.get('error', {}), indent=2))" 2>/dev/null || echo "Could not parse error"
    echo ""
    exit 1
fi

# 4. If completed, fetch the summary
if [ "$STATUS" = "completed" ]; then
    echo "4. Fetching call summary..."
    SUMMARY_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "$BASE_URL/api/v1/call-processing/summary/$TEST_CALL_ID" \
      -H "X-API-Key: $API_KEY")
    
    HTTP_STATUS=$(echo "$SUMMARY_RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
    SUMMARY_BODY=$(echo "$SUMMARY_RESPONSE" | sed '/HTTP_STATUS/d')
    
    echo "HTTP Status: $HTTP_STATUS"
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "Summary Response:"
        echo "$SUMMARY_BODY" | python3 -m json.tool 2>/dev/null || echo "$SUMMARY_BODY"
    else
        echo "ERROR: Failed to fetch summary"
        echo "$SUMMARY_BODY"
    fi
    echo ""
    
    # 5. Check MongoDB
    echo "5. Checking MongoDB for stored data..."
    python3 << 'EOF'
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys

async def check_mongo():
    try:
        # Get MongoDB URL from environment
        from dotenv import load_dotenv
        load_dotenv()
        
        mongodb_url = os.getenv("MONGODB_URL")
        db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
        
        if not mongodb_url:
            print("✗ MONGODB_URL not set in environment")
            return False
        
        client = AsyncIOMotorClient(mongodb_url)
        db = client[db_name]
        
        # Check call
        call = await db.calls.find_one({"call_id": os.getenv("TEST_CALL_ID")})
        if call:
            print(f"✓ Call found in MongoDB")
            print(f"  - Call ID: {call['call_id']}")
            print(f"  - Company ID: {call['company_id']}")
            print(f"  - Status: {call.get('status')}")
            print(f"  - Has transcript: {bool(call.get('transcript'))}")
            print(f"  - Transcript length: {len(call.get('transcript', ''))}")
            print(f"  - Has summary: {bool(call.get('summary'))}")
            print(f"  - Number of chunks: {len(call.get('chunks', []))}")
            
            if call.get('summary'):
                summary = call['summary']
                print(f"  - Summary keys: {list(summary.keys())}")
            
            client.close()
            return True
        else:
            print(f"✗ Call NOT found in MongoDB (searched for: {os.getenv('TEST_CALL_ID')})")
            client.close()
            return False
    except Exception as e:
        print(f"✗ MongoDB check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(check_mongo())
sys.exit(0 if result else 1)
EOF

    MONGO_STATUS=$?
    echo ""
    
    # 6. Check Milvus
    echo "6. Checking Milvus for indexed vectors..."
    python3 << 'EOF'
import os
import sys

try:
    from pymilvus import MilvusClient
    from dotenv import load_dotenv
    
    load_dotenv()
    
    milvus_uri = os.getenv("MILVUS_URI")
    milvus_token = os.getenv("MILVUS_TOKEN")
    collection_name = os.getenv("MILVUS_COLLECTION", "otto_intelligence_v1")
    test_call_id = os.getenv("TEST_CALL_ID")
    
    if not milvus_uri or not milvus_token:
        print("✗ MILVUS_URI or MILVUS_TOKEN not set")
        sys.exit(1)
    
    client = MilvusClient(
        uri=milvus_uri,
        token=milvus_token
    )
    
    # Query for vectors related to this call
    results = client.query(
        collection_name=collection_name,
        filter=f'doc_id == "{test_call_id}"',
        output_fields=["id", "tenant_id", "corpus_type", "doc_id", "created_at"],
        limit=20
    )
    
    print(f"Found {len(results)} vectors in Milvus for call {test_call_id}:")
    for i, result in enumerate(results):
        print(f"  {i+1}. ID: {result.get('id')}")
        print(f"     Corpus Type: {result.get('corpus_type')}")
        print(f"     Tenant ID: {result.get('tenant_id')}")
        print(f"     Doc ID: {result.get('doc_id')}")
        print(f"     Created: {result.get('created_at')}")
    
    if len(results) == 0:
        print(f"✗ No vectors found in Milvus for call {test_call_id}")
        print(f"   Searched collection: {collection_name}")
        print(f"   Filter: doc_id == \"{test_call_id}\"")
        sys.exit(1)
    else:
        print(f"✓ RAG indexing successful: {len(results)} vectors indexed")
        sys.exit(0)

except Exception as e:
    print(f"✗ Milvus check failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

    MILVUS_STATUS=$?
    echo ""
    
    # 7. Check Redis
    echo "7. Checking Redis for job status..."
    python3 << 'EOF'
import asyncio
import redis.asyncio as redis
import os
import json
import sys

async def check_redis():
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        redis_url = os.getenv("REDIS_URL")
        job_id = os.getenv("JOB_ID")
        
        if not redis_url:
            print("✗ REDIS_URL not set")
            return False
        
        r = redis.from_url(redis_url, decode_responses=True)
        
        job_key = f"job:{job_id}:status"
        status_data = await r.get(job_key)
        
        if status_data:
            status_obj = json.loads(status_data)
            print(f"✓ Job status found in Redis:")
            print(f"  Job ID: {status_obj.get('job_id')}")
            print(f"  Status: {status_obj.get('status')}")
            print(f"  Progress: {status_obj.get('progress', {}).get('percent')}%")
            print(f"  Current Step: {status_obj.get('progress', {}).get('current_step')}")
            print(f"  Updated: {status_obj.get('updated_at')}")
            await r.close()
            return True
        else:
            print(f"✗ Job status NOT found in Redis (key: {job_key})")
            await r.close()
            return False
    except Exception as e:
        print(f"✗ Redis check failed: {e}")
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(check_redis())
sys.exit(0 if result else 1)
EOF

    REDIS_STATUS=$?
    echo ""
    
    # Summary
    echo "================================"
    echo "Test Results Summary"
    echo "================================"
    echo "MongoDB Storage: $([ $MONGO_STATUS -eq 0 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo "Milvus RAG Indexing: $([ $MILVUS_STATUS -eq 0 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo "Redis Status Cache: $([ $REDIS_STATUS -eq 0 ] && echo '✓ PASS' || echo '✗ FAIL')"
    echo ""
    
    if [ $MONGO_STATUS -eq 0 ] && [ $MILVUS_STATUS -eq 0 ] && [ $REDIS_STATUS -eq 0 ]; then
        echo "==========================================="
        echo "       Test Result: SUCCESS ✓"
        echo "==========================================="
        exit 0
    else
        echo "==========================================="
        echo "       Test Result: PARTIAL FAILURE"
        echo "==========================================="
        exit 1
    fi
else
    echo "==========================================="
    echo "       Test Result: FAILED ✗"
    echo "       Status: $STATUS"
    echo "==========================================="
    exit 1
fi

