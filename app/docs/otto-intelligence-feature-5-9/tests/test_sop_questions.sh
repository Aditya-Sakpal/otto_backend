#!/bin/bash
set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
COMPANY_ID="test_company_123"

echo "========================================================================"
echo "TESTING SOP-SPECIFIC QUESTIONS IN ASK OTTO"
echo "========================================================================"
echo ""

# Create conversation
echo "Creating conversation..."
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"company_id\": \"$COMPANY_ID\",
    \"user_id\": \"test_sop_user\",
    \"metadata\": {\"source\": \"sop_test\"}
  }")

CONVERSATION_ID=$(echo $CONV_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('conversation_id', ''))")
echo "✓ Conversation ID: $CONVERSATION_ID"
echo ""

# Test 1: SOP Objection Handling
echo "========================================="
echo "Test 1: SOP Objection Handling"
echo "========================================="
echo "Question: 'What are the objection handling steps in our sales SOP?'"
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What are the objection handling steps in our sales SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Answer:')
print(data.get('answer', 'No answer'))
print('\nSources:')
for src in data.get('sources', []):
    print(f\"  - {src['type']}: {src['excerpt'][:100]}... (confidence: {src['confidence']:.3f})\")
print(f\"\nMetadata: {data.get('metadata', {})}\")
"
echo ""

# Test 2: SOP Greeting Requirements
echo "========================================="
echo "Test 2: SOP Greeting Requirements"
echo "========================================="
echo "Question: 'What should be included in the call opening according to our SOP?'"
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What should be included in the call opening according to our SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Answer:')
print(data.get('answer', 'No answer'))
print('\nSources:')
for src in data.get('sources', []):
    print(f\"  - {src['type']}: {src['excerpt'][:100]}... (confidence: {src['confidence']:.3f})\")
"
echo ""

# Test 3: SOP Metrics Query
echo "========================================="
echo "Test 3: SOP Metrics Query"
echo "========================================="
echo "Question: 'What are the key performance metrics in our sales SOP?'"
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What are the key performance metrics in our sales SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Answer:')
print(data.get('answer', 'No answer'))
print('\nSources:')
for src in data.get('sources', []):
    print(f\"  - {src['type']}: {src['excerpt'][:80]}... (confidence: {src['confidence']:.3f})\")
print(f\"\nTotal sources: {len(data.get('sources', []))}\")
"
echo ""

# Test 4: BANT Qualification from SOP
echo "========================================="
echo "Test 4: BANT Qualification from SOP"
echo "========================================="
echo "Question: 'What is the BANT qualification process according to our SOP?'"
echo ""

RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What is the BANT qualification process according to our SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Answer:')
print(data.get('answer', 'No answer'))
print('\nSources:')
for src in data.get('sources', []):
    print(f\"  - {src['type']}: {src['excerpt'][:100]}... (confidence: {src['confidence']:.3f})\")
"
echo ""

echo "========================================================================"
echo "SOP QUESTION TESTING COMPLETE"
echo "========================================================================"
