"""
Chunking Service

Dynamic text chunking for long transcripts.
"""

from typing import List, Dict, Any, Optional
import tiktoken


class ChunkingService:
    """Service for dynamic text chunking"""
    
    def __init__(self):
        # Use cl100k_base encoding (GPT-4, GPT-3.5-turbo)
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self.max_chunk_tokens = 120000  # Qwen2.5-7B context window: 131K
        self.overlap_tokens = 200
        self.reserved_summary_tokens = 4000
        self.reserved_output_tokens = 4000
    
    def chunk_transcript(
        self,
        transcript: str,
        call_id: str,
        max_tokens: Optional[int] = None,
        segments: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunk transcript into manageable pieces with optional speaker-aware chunking.
        
        Args:
            transcript: Full transcript text
            call_id: Call identifier
            max_tokens: Maximum tokens per chunk (default: 120K)
            segments: Optional diarized segments for semantic chunking
            
        Returns:
            List of chunk dictionaries with metadata
        """
        if not transcript or not transcript.strip():
            return []
        
        max_tokens = max_tokens or self.max_chunk_tokens
        
        # Calculate effective chunk size
        effective_chunk_size = (
            max_tokens
            - self.reserved_summary_tokens
            - self.reserved_output_tokens
        )
        
        # If segments provided, use semantic chunking
        if segments:
            return self._chunk_by_segments(transcript, call_id, segments, effective_chunk_size)
        
        # Otherwise, use token-based chunking
        return self._chunk_by_tokens(transcript, call_id, effective_chunk_size)
    
    def _chunk_by_tokens(
        self,
        transcript: str,
        call_id: str,
        effective_chunk_size: int
    ) -> List[Dict[str, Any]]:
        """Traditional token-based chunking with overlap."""
        
        # Tokenize transcript
        tokens = self.encoding.encode(transcript)
        
        if len(tokens) <= effective_chunk_size:
            # Single chunk
            return [{
                "chunk_id": f"c_{call_id}_1",
                "chunk_index": 1,
                "text": transcript,
                "token_count": len(tokens),
                "start_token": 0,
                "end_token": len(tokens),
                "chunking_method": "token_based"
            }]
        
        # Multiple chunks with overlap
        chunks = []
        start_idx = 0
        chunk_index = 1
        
        while start_idx < len(tokens):
            # Calculate end index
            end_idx = start_idx + effective_chunk_size
            
            if end_idx > len(tokens):
                end_idx = len(tokens)
            
            # Extract chunk tokens
            chunk_tokens = tokens[start_idx:end_idx]
            chunk_text = self.encoding.decode(chunk_tokens)
            
            # Create chunk object
            chunk = {
                "chunk_id": f"c_{call_id}_{chunk_index}",
                "chunk_index": chunk_index,
                "text": chunk_text,
                "token_count": len(chunk_tokens),
                "start_token": start_idx,
                "end_token": end_idx,
                "chunking_method": "token_based"
            }
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            if end_idx < len(tokens):
                start_idx = end_idx - self.overlap_tokens
            else:
                break
            
            chunk_index += 1
        
        return chunks
    
    def _chunk_by_segments(
        self,
        transcript: str,
        call_id: str,
        segments: List[Dict[str, Any]],
        effective_chunk_size: int
    ) -> List[Dict[str, Any]]:
        """
        Semantic chunking based on speaker segments.
        
        Groups segments into chunks while:
        - Respecting token limits
        - Trying to keep speaker turns together
        - Breaking at natural conversation boundaries
        """
        chunks = []
        chunk_index = 1
        current_chunk_segments = []
        current_chunk_tokens = 0
        
        for i, segment in enumerate(segments):
            segment_text = segment.get("text", "")
            speaker = segment.get("speaker", "unknown")
            
            # Format segment with speaker label
            formatted_segment = f"{speaker}: {segment_text}"
            segment_tokens = self.count_tokens(formatted_segment)
            
            # Check if adding this segment would exceed chunk size
            would_exceed = (current_chunk_tokens + segment_tokens) > effective_chunk_size
            
            if would_exceed and current_chunk_segments:
                # Save current chunk
                chunk_text = "\n\n".join(current_chunk_segments)
                chunks.append({
                    "chunk_id": f"c_{call_id}_{chunk_index}",
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "token_count": current_chunk_tokens,
                    "segment_count": len(current_chunk_segments),
                    "chunking_method": "semantic_speaker_aware"
                })
                
                chunk_index += 1
                current_chunk_segments = []
                current_chunk_tokens = 0
            
            # Add segment to current chunk
            current_chunk_segments.append(formatted_segment)
            current_chunk_tokens += segment_tokens
        
        # Add final chunk if any segments remain
        if current_chunk_segments:
            chunk_text = "\n\n".join(current_chunk_segments)
            chunks.append({
                "chunk_id": f"c_{call_id}_{chunk_index}",
                "chunk_index": chunk_index,
                "text": chunk_text,
                "token_count": current_chunk_tokens,
                "segment_count": len(current_chunk_segments),
                "chunking_method": "semantic_speaker_aware"
            })
        
        return chunks
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        return len(self.encoding.encode(text))
    
    def truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to maximum tokens"""
        tokens = self.encoding.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.encoding.decode(tokens[:max_tokens])


# Singleton instance
_chunking_service: Optional['ChunkingService'] = None


def get_chunking_service() -> ChunkingService:
    """Get singleton chunking service instance"""
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    return _chunking_service

