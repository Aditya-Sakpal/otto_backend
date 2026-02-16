#!/bin/bash
set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
COMPANY_ID="test_company_123"

echo "========================================================================"
echo "TESTING EMBEDDING PERFORMANCE (Preloaded Model)"
echo "========================================================================"
echo ""

# Create conversation
echo "Creating conversation..."
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"company_id\": \"$COMPANY_ID\",
    \"user_id\": \"test_perf\",
    \"metadata\": {\"source\": \"perf_test\"}
  }")

CONVERSATION_ID=$(echo $CONV_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('conversation_id', ''))")
echo "✓ Conversation ID: $CONVERSATION_ID"
echo ""

# Test 1: Simple query (should be fast with preloaded model)
echo "Test 1: First query (model already loaded)..."
START_TIME=$(date +%s%3N)

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What are the key metrics in our sales SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

END_TIME=$(date +%s%3N)
DURATION=$((END_TIME - START_TIME))

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"✓ Response received in {$DURATION}ms\")
print(f\"  Server response time: {data.get('metadata', {}).get('response_time_ms', 'N/A')}ms\")
print(f\"  Answer length: {len(data.get('answer', ''))} chars\")
print(f\"  Sources found: {len(data.get('sources', []))}\")
"

echo ""
echo "Test 2: Second query (model should already be in memory)..."
START_TIME=$(date +%s%3N)

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What should reps do during objection handling?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

END_TIME=$(date +%s%3N)
DURATION=$((END_TIME - START_TIME))

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"✓ Response received in {$DURATION}ms\")
print(f\"  Server response time: {data.get('metadata', {}).get('response_time_ms', 'N/A')}ms\")
print(f\"  Answer length: {len(data.get('answer', ''))} chars\")
print(f\"  Sources found: {len(data.get('sources', []))}\")
"

echo ""
echo "========================================================================"
echo "✓ PERFORMANCE TEST COMPLETE"
echo "========================================================================"
echo ""
echo "Note: With preloaded model, subsequent queries should be faster"
echo "      because the model is already in GPU/CPU memory."
