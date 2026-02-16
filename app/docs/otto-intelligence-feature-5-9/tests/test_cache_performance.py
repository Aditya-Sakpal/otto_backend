#!/usr/bin/env python3
"""
Test to measure the performance improvement of Redis caching for conversation history
"""

import asyncio
import time
from app.core.database import get_database
from app.core.redis_client import get_redis_client
from app.services.ask_otto.conversation_service import get_conversation_service

async def test_cache_performance():
    print("=" * 70)
    print("CONVERSATION HISTORY CACHING PERFORMANCE TEST")
    print("=" * 70)
    print()
    
    # Setup
    db = await get_database()
    redis = await get_redis_client()
    service = get_conversation_service()
    
    # Use an existing conversation with messages
    conversation_id = "conv_ad57558dbce94c99a889b0bf658da58f"
    
    print(f"Testing conversation: {conversation_id}")
    print()
    
    # Test 1: Clear cache and fetch from MongoDB
    print("Test 1: Fetch from MongoDB (cache cleared)")
    await redis.delete(f"ask_otto:history:{conversation_id}")
    
    start = time.perf_counter()
    history_from_db = await service.get_conversation_history(db, conversation_id, limit=10)
    end = time.perf_counter()
    time_from_db = (end - start) * 1000
    
    print(f"  ✓ Fetched {len(history_from_db)} messages from MongoDB")
    print(f"  ⏱  Time: {time_from_db:.2f}ms")
    print()
    
    # Test 2: Fetch from Redis cache
    print("Test 2: Fetch from Redis cache")
    
    start = time.perf_counter()
    history_from_cache = await service.get_conversation_history(db, conversation_id, limit=10)
    end = time.perf_counter()
    time_from_cache = (end - start) * 1000
    
    print(f"  ✓ Fetched {len(history_from_cache)} messages from Redis")
    print(f"  ⏱  Time: {time_from_cache:.2f}ms")
    print()
    
    # Test 3: Multiple reads from cache
    print("Test 3: 10 consecutive reads from cache")
    times = []
    
    for i in range(10):
        start = time.perf_counter()
        await service.get_conversation_history(db, conversation_id, limit=10)
        end = time.perf_counter()
        times.append((end - start) * 1000)
    
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    print(f"  ✓ Completed 10 reads")
    print(f"  ⏱  Average: {avg_time:.2f}ms")
    print(f"  ⏱  Min: {min_time:.2f}ms")
    print(f"  ⏱  Max: {max_time:.2f}ms")
    print()
    
    # Performance improvement
    improvement = ((time_from_db - time_from_cache) / time_from_db) * 100
    speedup = time_from_db / time_from_cache
    
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"MongoDB fetch time:    {time_from_db:.2f}ms")
    print(f"Redis cache time:      {time_from_cache:.2f}ms")
    print(f"Performance gain:      {improvement:.1f}% faster")
    print(f"Speedup factor:        {speedup:.1f}x")
    print()
    
    # Verify cache contents
    cached_data = await redis.get(f"ask_otto:history:{conversation_id}")
    if cached_data:
        import json
        cached_history = json.loads(cached_data)
        print(f"✓ Cache verified: {len(cached_history)} messages stored")
        print(f"  TTL: {await redis.ttl(f'ask_otto:history:{conversation_id}')}s remaining")
    else:
        print("✗ Cache not found!")

if __name__ == "__main__":
    asyncio.run(test_cache_performance())
