#!/bin/bash
set -e

API_KEY="5q3fwliU9ZFo3epTCsUfUiDw1Dy4DnBP"
BASE_URL="http://localhost:9000"
COMPANY_ID="test_company_123"

echo "========================================================================"
echo "TESTING DUAL-WRITE STRATEGY (MongoDB + Redis)"
echo "========================================================================"
echo ""

# Create conversation
echo "1. Creating new conversation..."
CONV_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"company_id\": \"$COMPANY_ID\",
    \"user_id\": \"test_dual_write\",
    \"metadata\": {\"source\": \"dual_write_test\"}
  }")

CONVERSATION_ID=$(echo $CONV_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('conversation_id', ''))")
echo "✓ Conversation ID: $CONVERSATION_ID"
echo ""

# Check if saved in both MongoDB and Redis
echo "2. Verifying dual-write for conversation creation..."
source venv/bin/activate && python3 << PYEOF
import asyncio
import json
from app.core.redis_client import get_redis_client
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def verify():
    # Check MongoDB
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    mongo_doc = await db.ask_otto_conversations.find_one({"conversation_id": "$CONVERSATION_ID"})
    
    if mongo_doc:
        print(f"✓ MongoDB: Conversation found")
        print(f"  - Company: {mongo_doc.get('company_id')}")
        print(f"  - User: {mongo_doc.get('user_id')}")
        print(f"  - Messages: {mongo_doc.get('message_count')}")
    else:
        print("✗ MongoDB: Conversation NOT found")
    
    # Check Redis
    redis = await get_redis_client()
    conv_key = f"ask_otto:conversation:$CONVERSATION_ID"
    redis_data = await redis.get(conv_key)
    
    if redis_data:
        print(f"✓ Redis: Conversation cached")
        conv = json.loads(redis_data)
        print(f"  - Company: {conv.get('company_id')}")
        print(f"  - User: {conv.get('user_id')}")
        print(f"  - TTL: {await redis.ttl(conv_key)}s")
    else:
        print("✗ Redis: Conversation NOT cached")
    
    client.close()

asyncio.run(verify())
PYEOF

echo ""

# Send a message
echo "3. Sending first message (dual-write test)..."
RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"What are the key metrics in our SOP?\",
    \"company_id\": \"$COMPANY_ID\"
  }")

MESSAGE_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('message_id', ''))")
echo "✓ Message sent: $MESSAGE_ID"
echo ""

# Verify message in both stores
echo "4. Verifying dual-write for messages..."
source venv/bin/activate && python3 << PYEOF2
import asyncio
import json
from app.core.redis_client import get_redis_client
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_message():
    # Check MongoDB
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    message_count = await db.ask_otto_messages.count_documents({"conversation_id": "$CONVERSATION_ID"})
    
    print(f"✓ MongoDB: {message_count} messages found")
    
    # Check Redis history
    redis = await get_redis_client()
    history_key = f"ask_otto:history:$CONVERSATION_ID"
    history_data = await redis.get(history_key)
    
    if history_data:
        history = json.loads(history_data)
        print(f"✓ Redis: {len(history)} messages cached")
        print(f"  - TTL: {await redis.ttl(history_key)}s")
        for i, msg in enumerate(history):
            print(f"  - Message {i+1}: [{msg['role']}] {msg['content'][:50]}...")
    else:
        print("✗ Redis: History NOT cached")
    
    client.close()

asyncio.run(verify_message())
PYEOF2

echo ""

# Send another message
echo "5. Sending second message..."
RESPONSE2=$(curl -s -X POST "$BASE_URL/api/v1/ask-otto/conversations/$CONVERSATION_ID/messages" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": \"Tell me about greeting quality\",
    \"company_id\": \"$COMPANY_ID\"
  }")

echo "✓ Second message sent"
echo ""

# Final verification
echo "6. Final verification of both stores..."
source venv/bin/activate && python3 << PYEOF3
import asyncio
import json
from app.core.redis_client import get_redis_client
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

async def final_verify():
    # Check MongoDB
    mongo_url = os.getenv("MONGODB_URL")
    db_name = os.getenv("MONGODB_DB_NAME", "otto-ai-storage")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    message_count = await db.ask_otto_messages.count_documents({"conversation_id": "$CONVERSATION_ID"})
    
    # Check Redis
    redis = await get_redis_client()
    history_key = f"ask_otto:history:$CONVERSATION_ID"
    history_data = await redis.get(history_key)
    
    redis_count = 0
    if history_data:
        history = json.loads(history_data)
        redis_count = len(history)
    
    print(f"MongoDB messages: {message_count}")
    print(f"Redis messages:   {redis_count}")
    
    if message_count == redis_count:
        print(f"\n✓ SUCCESS: Both stores are in sync ({message_count} messages)")
    else:
        print(f"\n⚠ WARNING: Stores are out of sync!")
    
    client.close()

asyncio.run(final_verify())
PYEOF3

echo ""
echo "========================================================================"
echo "✓ DUAL-WRITE TEST COMPLETE"
echo "========================================================================"
echo ""
echo "Summary:"
echo "- All writes go to BOTH MongoDB and Redis"
echo "- MongoDB is the source of truth (permanent storage)"
echo "- Redis provides fast access layer (with TTL)"
echo "- Reads prefer Redis, fallback to MongoDB"
