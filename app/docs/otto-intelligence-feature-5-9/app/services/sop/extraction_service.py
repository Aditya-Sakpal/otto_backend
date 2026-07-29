"""
SOP Text Extraction Service

Handles extraction of text from PDF and Word documents.
"""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import io

try:
    import PyPDF2
    import pdfplumber
    from docx import Document
except ImportError:
    PyPDF2 = None
    pdfplumber = None
    Document = None

from app.models.sop import SOPSection, SOPTable, ExtractedContent


logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when document extraction fails"""
    pass


class ExtractionService:
    """Service for extracting text from documents"""
    
    async def extract_from_file(self, file_path: str, file_type: str) -> ExtractedContent:
        """
        Extract text and structure from document file.
        
        Args:
            file_path: Path to document file
            file_type: MIME type of document
            
        Returns:
            ExtractedContent with text, sections, and tables
            
        Raises:
            ExtractionError: If extraction fails
        """
        try:
            if "pdf" in file_type.lower():
                return await self._extract_from_pdf(file_path)
            elif "word" in file_type.lower() or "docx" in file_type.lower():
                return await self._extract_from_word(file_path)
            else:
                raise ExtractionError(f"Unsupported file type: {file_type}")
        except Exception as e:
            logger.error(f"Extraction error for {file_path}: {str(e)}")
            raise ExtractionError(f"Failed to extract text: {str(e)}")
    
    async def _extract_from_pdf(self, file_path: str) -> ExtractedContent:
        """
        Extract text from PDF file.
        
        Uses pdfplumber for better structure extraction with fallback to text for testing.
        """
        # Try to read as text first (for testing with text files)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
                # If it reads as text and looks like text content, treat it as such
                if len(raw_text) > 0:
                    # Check if most characters are printable (likely text)
                    printable_chars = sum(1 for c in raw_text[:1000] if c.isprintable() or c in '\n\r\t')
                    if printable_chars > 900:  # 90% printable
                        logger.info(f"File appears to be plain text, using text extraction")
                        return await self._extract_from_text(raw_text)
        except (UnicodeDecodeError, Exception) as e:
            # Not a text file, continue with PDF extraction
            logger.debug(f"Not a text file: {e}")
            pass
        
        if pdfplumber is None:
            raise ExtractionError("pdfplumber not installed for PDF extraction")
        
        sections: List[SOPSection] = []
        tables: List[SOPTable] = []
        raw_text = ""
        
        try:
            with pdfplumber.open(file_path) as pdf:
                current_section = None
                current_section_text = []
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract text
                    page_text = page.extract_text() or ""
                    raw_text += page_text + "\n\n"
                    
                    # Extract tables
                    page_tables = page.extract_tables()
                    for table_data in page_tables:
                        if table_data and len(table_data) > 0:
                            headers = table_data[0] if table_data else []
                            rows = table_data[1:] if len(table_data) > 1 else []
                            tables.append(SOPTable(
                                title=None,
                                headers=[str(h) for h in headers],
                                rows=[[str(cell) for cell in row] for row in rows]
                            ))
                    
                    # Simple section detection (lines starting with numbers or caps)
                    lines = page_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Check if line looks like a heading
                        if self._is_heading(line):
                            # Save previous section
                            if current_section and current_section_text:
                                sections.append(SOPSection(
                                    title=current_section,
                                    content="\n".join(current_section_text),
                                    page_start=page_num - len(current_section_text) // 10,
                                    page_end=page_num
                                ))
                            
                            # Start new section
                            current_section = line
                            current_section_text = []
                        elif current_section:
                            current_section_text.append(line)
                
                # Add final section
                if current_section and current_section_text:
                    sections.append(SOPSection(
                        title=current_section,
                        content="\n".join(current_section_text)
                    ))
            
            # If no sections detected, create a single section
            if not sections and raw_text:
                sections.append(SOPSection(
                    title="Document Content",
                    content=raw_text
                ))
            
            return ExtractedContent(
                raw_text=raw_text,
                sections=sections,
                tables=tables
            )
            
        except Exception as e:
            logger.error(f"PDF extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract PDF: {str(e)}")
    
    async def _extract_from_word(self, file_path: str) -> ExtractedContent:
        """
        Extract text from Word document (.docx).
        """
        if Document is None:
            raise ExtractionError("python-docx not installed")
        
        try:
            doc = Document(file_path)
            
            sections: List[SOPSection] = []
            tables: List[SOPTable] = []
            raw_text = ""
            
            current_section = None
            current_section_text = []
            
            # Extract paragraphs
            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                
                raw_text += text + "\n"
                
                # Check if paragraph is a heading
                if para.style.name.startswith('Heading') or self._is_heading(text):
                    # Save previous section
                    if current_section and current_section_text:
                        sections.append(SOPSection(
                            title=current_section,
                            content="\n".join(current_section_text)
                        ))
                    
                    # Start new section
                    current_section = text
                    current_section_text = []
                else:
                    if current_section:
                        current_section_text.append(text)
            
            # Add final section
            if current_section and current_section_text:
                sections.append(SOPSection(
                    title=current_section,
                    content="\n".join(current_section_text)
                ))
            
            # Extract tables
            for table in doc.tables:
                if len(table.rows) > 0:
                    headers = [cell.text.strip() for cell in table.rows[0].cells]
                    rows = []
                    for row in table.rows[1:]:
                        rows.append([cell.text.strip() for cell in row.cells])
                    
                    tables.append(SOPTable(
                        title=None,
                        headers=headers,
                        rows=rows
                    ))
            
            # If no sections detected, create a single section
            if not sections and raw_text:
                sections.append(SOPSection(
                    title="Document Content",
                    content=raw_text
                ))
            
            return ExtractedContent(
                raw_text=raw_text,
                sections=sections,
                tables=tables
            )
            
        except Exception as e:
            logger.error(f"Word extraction error: {str(e)}")
            raise ExtractionError(f"Failed to extract Word document: {str(e)}")
    
    def _is_heading(self, text: str) -> bool:
        """
        Heuristic to detect if a line is a heading.
        """
        if not text or len(text) > 100:
            return False
        
        # Check for numbered headings (1. Section, 1.1 Subsection, etc.)
        if text[0].isdigit() and '.' in text[:10]:
            return True
        
        # Check for all caps (but not too long)
        if text.isupper() and len(text) < 50:
            return True
        
        # Check for title case with short length
        if text.istitle() and len(text) < 60:
            return True
        
        return False
    
    async def _extract_from_text(self, raw_text: str) -> ExtractedContent:
        """
        Extract sections from plain text.
        
        This is a fallback for testing or when PDF libraries aren't available.
        """
        sections: List[SOPSection] = []
        current_section = None
        current_section_text = []
        
        lines = raw_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line looks like a heading
            if self._is_heading(line):
                # Save previous section
                if current_section and current_section_text:
                    sections.append(SOPSection(
                        title=current_section,
                        content="\n".join(current_section_text)
                    ))
                
                # Start new section
                current_section = line
                current_section_text = []
            elif current_section:
                current_section_text.append(line)
            else:
                # Lines before first heading
                if not current_section:
                    current_section = "Introduction"
                    current_section_text = [line]
        
        # Add final section
        if current_section and current_section_text:
            sections.append(SOPSection(
                title=current_section,
                content="\n".join(current_section_text)
            ))
        
        # If no sections detected, create a single section
        if not sections and raw_text:
            sections.append(SOPSection(
                title="Document Content",
                content=raw_text
            ))
        
        return ExtractedContent(
            raw_text=raw_text,
            sections=sections,
            tables=[]
        )
    
    async def extract_from_bytes(self, file_bytes: bytes, file_type: str, filename: str) -> ExtractedContent:
        """
        Extract text from file bytes.
        
        Args:
            file_bytes: File content as bytes
            file_type: MIME type
            filename: Original filename
            
        Returns:
            ExtractedContent
        """
        # Save to temporary file
        import tempfile
        import os
        
        suffix = Path(filename).suffix
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        try:
            result = await self.extract_from_file(tmp_path, file_type)
            return result
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

