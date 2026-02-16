#!/bin/bash
set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
COMPANY_ID="test_company_123"

echo "========================================================================"
echo "TESTING REDIS CACHING FOR CONVERSATION HISTORY"
echo "========================================================================"
echo ""

# Create conversation
echo "1. Creating new conversation..."
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"company_id\": \"$COMPANY_ID\",
    \"user_id\": \"test_redis_cache\",
    \"metadata\": {\"source\": \"redis_test\"}
  }")

CONVERSATION_ID=$(echo $CONV_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('conversation_id', ''))")
echo "✓ Conversation ID: $CONVERSATION_ID"
echo ""

# Send first message
echo "2. Sending first message (will cache history in Redis)..."
START=$(date +%s%N)
RESPONSE1=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What are the key sales metrics?\",
    \"company_id\": \"$COMPANY_ID\"
  }")
END=$(date +%s%N)
TIME1=$(( (END - START) / 1000000 ))

echo "✓ First message sent (${TIME1}ms)"
echo ""

# Send second message (should use cached history)
echo "3. Sending second message (should use Redis cache for history)..."
START=$(date +%s%N)
RESPONSE2=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"Tell me more about objection handling\",
    \"company_id\": \"$COMPANY_ID\"
  }")
END=$(date +%s%N)
TIME2=$(( (END - START) / 1000000 ))

echo "✓ Second message sent (${TIME2}ms)"
echo ""

# Send third message
echo "4. Sending third message (still using Redis cache)..."
START=$(date +%s%N)
RESPONSE3=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What about greeting quality?\",
    \"company_id\": \"$COMPANY_ID\"
  }")
END=$(date +%s%N)
TIME3=$(( (END - START) / 1000000 ))

echo "✓ Third message sent (${TIME3}ms)"
echo ""

# Check Redis directly
echo "5. Checking Redis cache..."
source venv/bin/activate && python3 << PYEOF
import asyncio
import json
from app.core.redis_client import get_redis_client

async def check_redis():
    redis = await get_redis_client()
    
    # Check conversation cache
    conv_key = f"ask_otto:conversation:$CONVERSATION_ID"
    conv_data = await redis.get(conv_key)
    
    if conv_data:
        print(f"✓ Conversation cached in Redis")
        conv = json.loads(conv_data)
        print(f"  Message count: {conv.get('message_count')}")
    else:
        print("✗ Conversation NOT in Redis cache")
    
    # Check history cache
    history_key = f"ask_otto:history:$CONVERSATION_ID"
    history_data = await redis.get(history_key)
    
    if history_data:
        print(f"✓ Conversation history cached in Redis")
        history = json.loads(history_data)
        print(f"  Cached messages: {len(history)}")
        print(f"  Last message: {history[-1]['content'][:50]}...")
    else:
        print("✗ History NOT in Redis cache")

asyncio.run(check_redis())
PYEOF

echo ""
echo "6. Response times comparison:"
echo "  First message:  ${TIME1}ms"
echo "  Second message: ${TIME2}ms"
echo "  Third message:  ${TIME3}ms"
echo ""

# Show actual responses
echo "7. Sample responses:"
echo ""
echo "First Response:"
echo "$RESPONSE1" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  Answer: {data.get('answer', '')[:100]}...\")"
echo ""

echo "Second Response:"
echo "$RESPONSE2" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  Answer: {data.get('answer', '')[:100]}...\")"
echo ""

echo "Third Response:"
echo "$RESPONSE3" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"  Answer: {data.get('answer', '')[:100]}...\")"

echo ""
echo "========================================================================"
echo "✓ REDIS CACHING TEST COMPLETE"
echo "========================================================================"
echo ""
echo "Notes:"
echo "- Conversation metadata is cached for 1 hour"
echo "- Conversation history is cached for 5 minutes"
echo "- Cache is invalidated when new messages are added"
echo "- Subsequent queries use cached history for faster performance"
