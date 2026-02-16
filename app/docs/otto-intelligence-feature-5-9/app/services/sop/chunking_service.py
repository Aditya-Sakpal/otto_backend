"""
SOP Document Chunking Service

Handles context-aware chunking of SOP documents for processing and indexing.
"""

import logging
from typing import List, Dict, Any
import tiktoken

from app.models.sop import ExtractedContent, SOPChunk
from app.models.enums import ChunkType


logger = logging.getLogger(__name__)


class ChunkingService:
    """Service for chunking SOP documents"""
    
    def __init__(self, max_chunk_tokens: int = 8000, overlap_tokens: int = 500):
        """
        Initialize chunking service.
        
        Args:
            max_chunk_tokens: Maximum tokens per chunk
            overlap_tokens: Token overlap between chunks
        """
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens
        
        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except:
            logger.warning("Failed to load tiktoken, using character-based estimation")
            self.tokenizer = None
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Rough estimation: 1 token ≈ 4 characters
            return len(text) // 4
    
    async def chunk_document(
        self,
        extracted_content: ExtractedContent,
        sop_id: str,
        company_id: str
    ) -> List[SOPChunk]:
        """
        Chunk SOP document using context-aware strategy.
        
        Strategy:
        1. Try section-based chunking (preserve complete sections)
        2. If section too large, split by paragraphs
        3. If still too large, split by tokens with overlap
        
        Args:
            extracted_content: Extracted document content
            sop_id: SOP document ID
            company_id: Company ID
            
        Returns:
            List of SOPChunk objects
        """
        chunks = []
        chunk_index = 0
        
        # Process each section
        for section in extracted_content.sections:
            section_tokens = self.count_tokens(section.content)
            
            if section_tokens <= self.max_chunk_tokens:
                # Section fits in one chunk
                chunk = SOPChunk(
                    chunk_id=f"sop_chunk_{sop_id}_{chunk_index:03d}",
                    sop_id=sop_id,
                    company_id=company_id,
                    chunk_index=chunk_index,
                    section_title=section.title,
                    parent_section=None,
                    text=section.content,
                    token_count=section_tokens,
                    chunk_type=self._classify_chunk_type(section.content)
                )
                chunks.append(chunk)
                chunk_index += 1
            else:
                # Section needs splitting
                section_chunks = await self._split_large_section(
                    section.content,
                    section.title,
                    sop_id,
                    company_id,
                    chunk_index
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)
        
        # If no sections (unlikely), chunk the raw text
        if not chunks and extracted_content.raw_text:
            raw_chunks = await self._split_text_with_overlap(
                extracted_content.raw_text,
                sop_id,
                company_id,
                0,
                "Document Content"
            )
            chunks.extend(raw_chunks)
        
        return chunks
    
    async def _split_large_section(
        self,
        section_text: str,
        section_title: str,
        sop_id: str,
        company_id: str,
        start_index: int
    ) -> List[SOPChunk]:
        """Split large section into chunks"""
        chunks = []
        
        # Try splitting by paragraphs first
        paragraphs = section_text.split('\n\n')
        
        current_chunk = ""
        current_tokens = 0
        chunk_index = start_index
        
        for para in paragraphs:
            para_tokens = self.count_tokens(para)
            
            if current_tokens + para_tokens <= self.max_chunk_tokens:
                # Add paragraph to current chunk
                current_chunk += para + "\n\n"
                current_tokens += para_tokens
            else:
                # Save current chunk
                if current_chunk:
                    chunk = SOPChunk(
                        chunk_id=f"sop_chunk_{sop_id}_{chunk_index:03d}",
                        sop_id=sop_id,
                        company_id=company_id,
                        chunk_index=chunk_index,
                        section_title=section_title,
                        parent_section=None,
                        text=current_chunk.strip(),
                        token_count=current_tokens,
                        chunk_type=self._classify_chunk_type(current_chunk)
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                
                # Handle oversized paragraph
                if para_tokens > self.max_chunk_tokens:
                    # Split paragraph with token-based chunking
                    para_chunks = await self._split_text_with_overlap(
                        para,
                        sop_id,
                        company_id,
                        chunk_index,
                        section_title
                    )
                    chunks.extend(para_chunks)
                    chunk_index += len(para_chunks)
                    current_chunk = ""
                    current_tokens = 0
                else:
                    # Start new chunk with this paragraph
                    current_chunk = para + "\n\n"
                    current_tokens = para_tokens
        
        # Save final chunk
        if current_chunk:
            chunk = SOPChunk(
                chunk_id=f"sop_chunk_{sop_id}_{chunk_index:03d}",
                sop_id=sop_id,
                company_id=company_id,
                chunk_index=chunk_index,
                section_title=section_title,
                parent_section=None,
                text=current_chunk.strip(),
                token_count=current_tokens,
                chunk_type=self._classify_chunk_type(current_chunk)
            )
            chunks.append(chunk)
        
        return chunks
    
    async def _split_text_with_overlap(
        self,
        text: str,
        sop_id: str,
        company_id: str,
        start_index: int,
        section_title: str
    ) -> List[SOPChunk]:
        """
        Split text with token-based chunking and overlap.
        """
        chunks = []
        
        if not self.tokenizer:
            # Fallback to character-based chunking
            return await self._split_by_characters(
                text, sop_id, company_id, start_index, section_title
            )
        
        # Tokenize text
        tokens = self.tokenizer.encode(text)
        
        chunk_index = start_index
        start_pos = 0
        
        while start_pos < len(tokens):
            # Extract chunk
            end_pos = min(start_pos + self.max_chunk_tokens, len(tokens))
            chunk_tokens = tokens[start_pos:end_pos]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            
            # Create chunk
            chunk = SOPChunk(
                chunk_id=f"sop_chunk_{sop_id}_{chunk_index:03d}",
                sop_id=sop_id,
                company_id=company_id,
                chunk_index=chunk_index,
                section_title=section_title,
                parent_section=None,
                text=chunk_text,
                token_count=len(chunk_tokens),
                chunk_type=self._classify_chunk_type(chunk_text)
            )
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start_pos = end_pos - self.overlap_tokens
            chunk_index += 1
        
        return chunks
    
    async def _split_by_characters(
        self,
        text: str,
        sop_id: str,
        company_id: str,
        start_index: int,
        section_title: str
    ) -> List[SOPChunk]:
        """Fallback character-based chunking"""
        chunks = []
        max_chars = self.max_chunk_tokens * 4  # 1 token ≈ 4 chars
        overlap_chars = self.overlap_tokens * 4
        
        chunk_index = start_index
        start_pos = 0
        
        while start_pos < len(text):
            end_pos = min(start_pos + max_chars, len(text))
            chunk_text = text[start_pos:end_pos]
            
            chunk = SOPChunk(
                chunk_id=f"sop_chunk_{sop_id}_{chunk_index:03d}",
                sop_id=sop_id,
                company_id=company_id,
                chunk_index=chunk_index,
                section_title=section_title,
                parent_section=None,
                text=chunk_text,
                token_count=self.count_tokens(chunk_text),
                chunk_type=self._classify_chunk_type(chunk_text)
            )
            chunks.append(chunk)
            
            start_pos = end_pos - overlap_chars
            chunk_index += 1
        
        return chunks
    
    def _classify_chunk_type(self, text: str) -> ChunkType:
        """Classify chunk content type"""
        text_lower = text.lower()
        
        # Check for metric-related content
        metric_keywords = ["metric", "score", "evaluate", "measure", "kpi", "performance"]
        metric_count = sum(1 for kw in metric_keywords if kw in text_lower)
        
        # Check for criteria
        criteria_keywords = ["criteria", "rating", "excellent", "good", "poor", "needs improvement"]
        criteria_count = sum(1 for kw in criteria_keywords if kw in text_lower)
        
        # Check for procedures
        procedure_keywords = ["step", "procedure", "should", "must", "guideline", "process"]
        procedure_count = sum(1 for kw in procedure_keywords if kw in text_lower)
        
        # Classify based on keyword counts
        if metric_count >= 2:
            return ChunkType.METRIC
        elif criteria_count >= 2:
            return ChunkType.CRITERIA
        elif procedure_count >= 2:
            return ChunkType.PROCEDURE
        else:
            return ChunkType.GENERAL

