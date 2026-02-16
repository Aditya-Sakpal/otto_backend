"""
Conversation Service

Service for managing Ask Otto conversations with Redis caching.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import uuid
import json
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...models.conversation import Conversation, Message, MessageMetadata
from ...core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for conversation management with Redis caching"""
    
    def __init__(self):
        self.conversation_cache_ttl = 3600  # 1 hour
        self.history_cache_ttl = 300  # 5 minutes (shorter for frequently updated data)
    
    def _get_conversation_cache_key(self, conversation_id: str) -> str:
        """Get Redis cache key for conversation metadata"""
        return f"ask_otto:conversation:{conversation_id}"
    
    def _get_history_cache_key(self, conversation_id: str) -> str:
        """Get Redis cache key for conversation history"""
        return f"ask_otto:history:{conversation_id}"
    
    async def create_conversation(
        self,
        db: AsyncIOMotorDatabase,
        company_id: str,
        user_id: str,
        metadata: Dict[str, Any] = None
    ) -> Conversation:
        """
        Create a new conversation.
        Writes to BOTH MongoDB and Redis simultaneously.
        """
        conversation_id = str(uuid.uuid4())  # Pure UUID for conversation_id
        
        expires_at = datetime.utcnow() + timedelta(days=1)  # 24 hour expiry
        
        conversation = Conversation(
            conversation_id=conversation_id,
            company_id=company_id,
            user_id=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            expires_at=expires_at,
            message_count=0,
            metadata=metadata or {}
        )
        
        # DUAL WRITE: Save to BOTH MongoDB and Redis
        
        # 1. Save to MongoDB (permanent storage)
        await db.ask_otto_conversations.insert_one(conversation.dict())
        
        # 2. Save to Redis (fast access layer)
        try:
            redis = await get_redis_client()
            cache_key = self._get_conversation_cache_key(conversation_id)
            await redis.setex(
                cache_key,
                self.conversation_cache_ttl,
                json.dumps(conversation.dict(), default=str)
            )
            logger.info(f"✓ Dual-write: Conversation created in MongoDB and Redis (ID: {conversation_id})")
        except Exception as e:
            logger.error(f"Failed to write conversation to Redis (MongoDB write succeeded): {e}")
            # Continue - MongoDB has the data
        
        return conversation
    
    async def get_conversation(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str
    ) -> Optional[Conversation]:
        """
        Get conversation by ID.
        Reads from Redis for speed, with MongoDB as source of truth.
        """
        # Try Redis cache first (fast path)
        try:
            redis = await get_redis_client()
            cache_key = self._get_conversation_cache_key(conversation_id)
            cached_data = await redis.get(cache_key)
            
            if cached_data:
                logger.info(f"✓ Cache hit: Retrieved conversation from Redis (ID: {conversation_id})")
                doc = json.loads(cached_data)
                return Conversation(**doc)
        except Exception as e:
            logger.warning(f"Redis read failed, falling back to MongoDB: {e}")
        
        # Fetch from MongoDB (source of truth)
        logger.info(f"Cache miss: Fetching conversation from MongoDB (ID: {conversation_id})")
        doc = await db.ask_otto_conversations.find_one({"conversation_id": conversation_id})
        
        if not doc:
            return None
        
        doc.pop("_id", None)
        conversation = Conversation(**doc)
        
        # Write to Redis cache for next time (dual-write pattern)
        try:
            redis = await get_redis_client()
            cache_key = self._get_conversation_cache_key(conversation_id)
            await redis.setex(
                cache_key,
                self.conversation_cache_ttl,
                json.dumps(doc, default=str)
            )
            logger.info(f"✓ Populated Redis cache from MongoDB (ID: {conversation_id})")
        except Exception as e:
            logger.error(f"Failed to cache conversation in Redis: {e}")
            # Continue - we have the data from MongoDB
        
        return conversation
    
    async def delete_conversation(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str
    ) -> bool:
        """Delete a conversation and all its messages"""
        # Delete messages
        await db.ask_otto_messages.delete_many({"conversation_id": conversation_id})
        
        # Delete conversation
        result = await db.ask_otto_conversations.delete_one({"conversation_id": conversation_id})
        
        # Clear Redis cache
        try:
            redis = await get_redis_client()
            await redis.delete(self._get_conversation_cache_key(conversation_id))
            await redis.delete(self._get_history_cache_key(conversation_id))
            logger.debug(f"Cleared Redis cache for conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Failed to clear Redis cache: {e}")
        
        return result.deleted_count > 0
    
    async def add_message(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str,
        role: str,
        content: str,
        sources: List[Dict] = None,
        customer_context: Dict = None,
        suggested_follow_ups: List[str] = None,
        metadata: MessageMetadata = None
    ) -> Message:
        """
        Add a message to a conversation.
        Writes to BOTH MongoDB and Redis simultaneously.
        """
        message_id = f"msg_{uuid.uuid4().hex}"
        
        message = Message(
            message_id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources or [],
            customer_context=customer_context,
            suggested_follow_ups=suggested_follow_ups or [],
            metadata=metadata or MessageMetadata(),
            created_at=datetime.utcnow()
        )
        
        # DUAL WRITE: Save to BOTH MongoDB and Redis
        
        # 1. Save to MongoDB (permanent storage)
        await db.ask_otto_messages.insert_one(message.dict())
        
        # 2. Update conversation message count and timestamp in MongoDB
        await db.ask_otto_conversations.update_one(
            {"conversation_id": conversation_id},
            {
                "$inc": {"message_count": 1},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        
        # 3. Update Redis cache (fast access layer)
        try:
            redis = await get_redis_client()
            
            # Update conversation metadata cache
            conv_cache_key = self._get_conversation_cache_key(conversation_id)
            # Invalidate to force refresh with updated message count
            await redis.delete(conv_cache_key)
            
            # Update history cache by appending new message
            history_cache_key = self._get_history_cache_key(conversation_id)
            cached_history = await redis.get(history_cache_key)
            
            if cached_history:
                # Append to existing history
                history = json.loads(cached_history)
                history.append({"role": role, "content": content})
                
                # Keep only last 10 messages in cache
                if len(history) > 10:
                    history = history[-10:]
            else:
                # Fetch recent history from MongoDB to populate cache
                cursor = db.ask_otto_messages.find(
                    {"conversation_id": conversation_id}
                ).sort("created_at", -1).limit(10)
                
                messages = await cursor.to_list(length=10)
                messages.reverse()
                
                history = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in messages
                ]
            
            # Write to Redis
            await redis.setex(
                history_cache_key,
                self.history_cache_ttl,
                json.dumps(history)
            )
            logger.info(f"✓ Dual-write: Message saved to MongoDB and Redis (conversation: {conversation_id})")
                
        except Exception as e:
            logger.error(f"Failed to write to Redis (MongoDB write succeeded): {e}")
            # Continue - MongoDB has the data, Redis cache will be rebuilt on next read
        
        return message
    
    async def get_conversation_history(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Get conversation history in format suitable for LLM.
        Reads from Redis for speed, with MongoDB as source of truth.
        """
        # Try Redis cache first (fast path)
        try:
            redis = await get_redis_client()
            cache_key = self._get_history_cache_key(conversation_id)
            cached_data = await redis.get(cache_key)
            
            if cached_data:
                logger.info(f"✓ Cache hit: Retrieved conversation history from Redis (ID: {conversation_id})")
                history = json.loads(cached_data)
                # Return only the last 'limit' messages
                return history[-limit:] if len(history) > limit else history
        except Exception as e:
            logger.warning(f"Redis read failed, falling back to MongoDB: {e}")
        
        # Fetch from MongoDB (source of truth)
        logger.info(f"Cache miss: Fetching conversation history from MongoDB (ID: {conversation_id})")
        cursor = db.ask_otto_messages.find(
            {"conversation_id": conversation_id}
        ).sort("created_at", -1).limit(limit)
        
        messages = await cursor.to_list(length=limit)
        
        # Reverse to get chronological order
        messages.reverse()
        
        # Format for LLM
        history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
        
        # Write to Redis cache for next time (dual-write pattern)
        try:
            redis = await get_redis_client()
            cache_key = self._get_history_cache_key(conversation_id)
            await redis.setex(
                cache_key,
                self.history_cache_ttl,
                json.dumps(history)
            )
            logger.info(f"✓ Populated Redis cache from MongoDB (ID: {conversation_id})")
        except Exception as e:
            logger.error(f"Failed to cache conversation history in Redis: {e}")
            # Continue - we have the data from MongoDB
        
        return history
    
    async def get_messages(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str,
        limit: int = 50,
        before: Optional[str] = None
    ) -> tuple[List[Message], bool]:
        """Get messages with pagination"""
        query = {"conversation_id": conversation_id}
        
        if before:
            # Get message timestamp
            before_msg = await db.ask_otto_messages.find_one({"message_id": before})
            if before_msg:
                query["created_at"] = {"$lt": before_msg["created_at"]}
        
        cursor = db.ask_otto_messages.find(query).sort("created_at", -1).limit(limit + 1)
        messages = await cursor.to_list(length=limit + 1)
        
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]
        
        # Convert to Message objects
        message_objs = []
        for msg in messages:
            msg.pop("_id", None)
            message_objs.append(Message(**msg))
        
        return message_objs, has_more


# Singleton
_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """Get singleton instance"""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service

