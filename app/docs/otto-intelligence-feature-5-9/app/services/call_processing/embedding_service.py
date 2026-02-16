"""
Embedding Service

HuggingFace sentence-transformers embedding generation for RAG indexing.
"""

import asyncio
from typing import List, Optional, Dict, Any
import hashlib
import json
import logging
import torch
from sentence_transformers import SentenceTransformer
from ...core.redis_client import get_redis_client
from ...config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using HuggingFace models"""
    
    def __init__(self, preload: bool = False):
        self.model_name = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.cache_ttl = 3600  # 1 hour cache for embeddings
        self.model = None
        self.device = None
        
        if preload:
            self._load_model()
    
    def _load_model(self):
        """Load the embedding model with CUDA if available"""
        if self.model is None:
            # Determine device (CUDA if available, else CPU)
            if torch.cuda.is_available():
                self.device = "cuda"
                logger.info(f"Loading embedding model '{self.model_name}' on CUDA")
            else:
                self.device = "cpu"
                logger.info(f"Loading embedding model '{self.model_name}' on CPU")
            
            # Load model on the appropriate device
            self.model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(f"✓ Embedding model loaded successfully on {self.device}")
            
        return self.model
    
    async def generate_embedding(
        self,
        text: str,
        use_cache: bool = True
    ) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            use_cache: Whether to use Redis cache
            
        Returns:
            Embedding vector
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        # Check cache first
        if use_cache:
            cached = await self._get_cached_embedding(text)
            if cached:
                return cached
        
        try:
            # Run in thread pool to avoid blocking
            model = self._load_model()
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(text, convert_to_numpy=True)
            )
            
            # Convert to list
            embedding_list = embedding.tolist()
            
            # Cache the result
            if use_cache:
                await self._cache_embedding(text, embedding_list)
            
            return embedding_list
            
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")
    
    async def generate_embeddings_batch(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            use_cache: Whether to use Redis cache
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Filter empty texts
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return []
        
        # Check cache for each text
        embeddings = []
        texts_to_embed = []
        text_indices = []
        
        if use_cache:
            for i, text in enumerate(texts):
                cached = await self._get_cached_embedding(text)
                if cached:
                    embeddings.append((i, cached))
                else:
                    texts_to_embed.append(text)
                    text_indices.append(i)
        else:
            texts_to_embed = texts
            text_indices = list(range(len(texts)))
        
        # Generate embeddings for uncached texts
        if texts_to_embed:
            try:
                model = self._load_model()
                loop = asyncio.get_event_loop()
                batch_embeddings = await loop.run_in_executor(
                    None,
                    lambda: model.encode(texts_to_embed, convert_to_numpy=True, batch_size=32)
                )
                
                for i, embedding in enumerate(batch_embeddings):
                    embedding_list = embedding.tolist()
                    original_index = text_indices[i]
                    embeddings.append((original_index, embedding_list))
                    
                    # Cache the result
                    if use_cache:
                        await self._cache_embedding(texts_to_embed[i], embedding_list)
                
            except Exception as e:
                raise Exception(f"Failed to generate batch embeddings: {str(e)}")
        
        # Sort by original index and return
        embeddings.sort(key=lambda x: x[0])
        return [emb for _, emb in embeddings]
    
    async def _get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding from Redis"""
        try:
            redis = await get_redis_client()
            cache_key = self._get_cache_key(text)
            
            cached_data = await redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
            
            return None
            
        except Exception:
            # If cache fails, just return None
            return None
    
    async def _cache_embedding(self, text: str, embedding: List[float]) -> None:
        """Cache embedding in Redis"""
        try:
            redis = await get_redis_client()
            cache_key = self._get_cache_key(text)
            
            await redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(embedding)
            )
            
        except Exception:
            # If caching fails, just ignore
            pass
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{self.model_name}:{text_hash}"
    
    async def get_embedding_for_query(self, query: str) -> List[float]:
        """
        Get embedding for a search query with query-specific caching.
        
        Args:
            query: Search query text
            
        Returns:
            Embedding vector
        """
        return await self.generate_embedding(query, use_cache=True)


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service(preload: bool = False) -> EmbeddingService:
    """
    Get singleton embedding service instance.
    
    Args:
        preload: If True, load the model immediately on first call
        
    Returns:
        EmbeddingService instance
    """
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService(preload=preload)
    return _embedding_service


def preload_embedding_model():
    """
    Preload the embedding model at application startup.
    Should be called during FastAPI lifespan startup.
    """
    logger.info("Preloading embedding model...")
    service = get_embedding_service(preload=True)
    logger.info("✓ Embedding model preloaded successfully")
    return service

