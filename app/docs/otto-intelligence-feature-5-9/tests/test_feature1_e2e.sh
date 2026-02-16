#!/bin/bash
# Feature 1 End-to-End Testing Script
# Tests the complete call processing pipeline

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

# 2. Upload audio file to a temporary HTTP server (simulate S3)
# For testing, we'll use the file:// protocol or copy to a web-accessible location
# Since we can't use file:// directly, we'll need to serve it via HTTP

echo "2. Starting simple HTTP server for audio file..."
cd /home/uwcuser/otto-intelligence
python3 -m http.server 8888 &
HTTP_SERVER_PID=$!
echo "HTTP Server PID: $HTTP_SERVER_PID"
sleep 2

AUDIO_URL="http://localhost:8888/Mock%20Call%20Sample%20Recording%20With%20Call%20Flow%20Guide_16khz.wav"
echo "Audio URL: $AUDIO_URL"
echo ""

# 3. Submit call for processing
echo "3. Submitting call for processing..."
PROCESS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/v1/call-processing/process" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "call_id": "'"$TEST_CALL_ID"'",
    "company_id": "'"$TEST_COMPANY_ID"'",
    "audio_url": "'"$AUDIO_URL"'",
    "phone_number": "+14805551234",
    "call_date": "2026-01-09T14:30:00Z",
    "duration": 300,
    "metadata": {
      "rep_name": "Test Rep",
      "customer_name": "Test Customer",
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
echo "Response: $RESPONSE_BODY"
echo ""

if [ "$HTTP_STATUS" != "202" ]; then
    echo "ERROR: Expected 202, got $HTTP_STATUS"
    kill $HTTP_SERVER_PID 2>/dev/null || true
    exit 1
fi

# Extract job_id from response
JOB_ID=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")
echo "Job ID: $JOB_ID"
echo ""

# 4. Poll for completion
echo "4. Polling for job completion..."
MAX_ATTEMPTS=60  # 5 minutes max
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
done

echo ""
echo "Final Status: $STATUS"
echo "Full Response:"
echo "$STATUS_RESPONSE" | python3 -m json.tool
echo ""

# 5. If completed, fetch the summary
if [ "$STATUS" = "completed" ]; then
    echo "5. Fetching call summary..."
    SUMMARY_RESPONSE=$(curl -s "$BASE_URL/api/v1/call-processing/summary/$TEST_CALL_ID" \
      -H "X-API-Key: $API_KEY")
    
    echo "Summary Response:"
    echo "$SUMMARY_RESPONSE" | python3 -m json.tool
    echo ""
    
    # 6. Check MongoDB
    echo "6. Checking MongoDB for stored data..."
    echo "Connecting to MongoDB and querying..."
    python3 << EOF
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def check_mongo():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("MONGODB_DB_NAME", "otto-ai-storage")]
    
    # Check call
    call = await db.calls.find_one({"call_id": "$TEST_CALL_ID"})
    if call:
        print(f"✓ Call found in MongoDB: {call['call_id']}")
        print(f"  - Status: {call.get('status')}")
        print(f"  - Has transcript: {bool(call.get('transcript'))}")
        print(f"  - Has summary: {bool(call.get('summary'))}")
        print(f"  - Number of chunks: {len(call.get('chunks', []))}")
    else:
        print("✗ Call NOT found in MongoDB")
    
    client.close()

asyncio.run(check_mongo())
EOF
    echo ""
    
    # 7. Check Milvus
    echo "7. Checking Milvus for indexed vectors..."
    python3 << EOF
import asyncio
from pymilvus import MilvusClient
import os
from dotenv import load_dotenv

load_dotenv()

async def check_milvus():
    client = MilvusClient(
        uri=os.getenv("MILVUS_URI"),
        token=os.getenv("MILVUS_TOKEN")
    )
    
    collection_name = os.getenv("MILVUS_COLLECTION", "otto_intelligence_v1")
    
    # Query for vectors related to this call
    results = client.query(
        collection_name=collection_name,
        filter=f'doc_id == "{TEST_CALL_ID}"',
        output_fields=["id", "tenant_id", "corpus_type", "doc_id", "created_at"],
        limit=10
    )
    
    print(f"Found {len(results)} vectors in Milvus for call {TEST_CALL_ID}:")
    for i, result in enumerate(results):
        print(f"  {i+1}. ID: {result.get('id')}")
        print(f"     Corpus Type: {result.get('corpus_type')}")
        print(f"     Tenant ID: {result.get('tenant_id')}")
    
    if len(results) == 0:
        print("✗ No vectors found in Milvus!")
    else:
        print(f"✓ RAG indexing successful: {len(results)} vectors indexed")

asyncio.run(check_milvus())
EOF
    echo ""
    
    # 8. Check Redis
    echo "8. Checking Redis for job status..."
    python3 << EOF
import asyncio
import redis.asyncio as redis
import os
import json
from dotenv import load_dotenv

load_dotenv()

async def check_redis():
    r = redis.from_url(os.getenv("REDIS_URL"))
    
    job_key = f"job:{JOB_ID}:status"
    status_data = await r.get(job_key)
    
    if status_data:
        status_obj = json.loads(status_data)
        print(f"✓ Job status found in Redis:")
        print(f"  Job ID: {status_obj.get('job_id')}")
        print(f"  Status: {status_obj.get('status')}")
        print(f"  Progress: {status_obj.get('progress', {}).get('percent')}%")
        print(f"  Updated: {status_obj.get('updated_at')}")
    else:
        print(f"✗ Job status NOT found in Redis (key: {job_key})")
    
    await r.close()

asyncio.run(check_redis())
EOF
    echo ""
    
    echo "==========================================="
    echo "Test Result: SUCCESS ✓"
    echo "==========================================="
else
    echo "==========================================="
    echo "Test Result: FAILED ✗"
    echo "Final Status: $STATUS"
    echo "==========================================="
fi

# Cleanup
echo ""
echo "Cleaning up..."
kill $HTTP_SERVER_PID 2>/dev/null || true
echo "Done!"

