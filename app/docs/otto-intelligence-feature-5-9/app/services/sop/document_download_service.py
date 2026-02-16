"""
Document Download Service

Service for downloading documents (PDFs, Word docs) from S3, HTTP, or local paths.
Based on audio_service.py pattern.
"""

import os
import tempfile
import logging
from typing import Tuple
from urllib.parse import urlparse
import aiohttp
import boto3
from botocore.exceptions import ClientError
from ...config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class DocumentDownloadService:
    """Service for document download operations"""
    
    def __init__(self):
        self.s3_client = None
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION or 'us-east-1'
            )
    
    async def download_document(self, document_url: str, max_size_mb: int = 50) -> Tuple[bytes, str, str]:
        """
        Download document file from URL or S3, or use local file.
        
        Args:
            document_url: S3 URL (s3://bucket/key), HTTP URL, or local file path
            max_size_mb: Maximum file size in MB (default: 50MB)
            
        Returns:
            Tuple of (file_bytes, content_type, filename)
        """
        if document_url.startswith('s3://'):
            return await self._download_from_s3(document_url, max_size_mb)
        elif document_url.startswith('http://') or document_url.startswith('https://'):
            return await self._download_from_http(document_url, max_size_mb)
        elif document_url.startswith('file://'):
            # Local file path
            local_path = document_url[7:]  # Remove file:// prefix
            return await self._read_local_file(local_path, max_size_mb)
        elif document_url.startswith('/'):
            # Absolute local path
            return await self._read_local_file(document_url, max_size_mb)
        else:
            raise ValueError(f"Unsupported document URL format: {document_url}")
    
    async def _download_from_s3(self, s3_url: str, max_size_mb: int) -> Tuple[bytes, str, str]:
        """Download document from S3"""
        if not self.s3_client:
            raise Exception("S3 client not configured. Set AWS credentials in environment.")
        
        # Parse S3 URL: s3://bucket/key
        parts = s3_url[5:].split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
        
        bucket = parts[0]
        key = parts[1]
        
        # Extract filename
        filename = key.split('/')[-1]
        
        # Create temporary file
        suffix = os.path.splitext(key)[1] or '.pdf'
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        )
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            # Download from S3
            self.s3_client.download_file(bucket, key, temp_path)
            
            # Read file bytes
            with open(temp_path, 'rb') as f:
                file_bytes = f.read()
            
            # Check size
            file_size = len(file_bytes)
            max_size = max_size_mb * 1024 * 1024
            if file_size > max_size:
                raise ValueError(
                    f"File too large: {file_size} bytes. Maximum: {max_size} bytes ({max_size_mb}MB)"
                )
            
            # Determine content type
            content_type = self._get_content_type(filename)
            
            logger.info(f"Downloaded from S3: {filename}, size: {file_size} bytes, type: {content_type}")
            
            return file_bytes, content_type, filename
            
        except ClientError as e:
            raise Exception(f"Failed to download from S3: {str(e)}")
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    async def _download_from_http(self, http_url: str, max_size_mb: int) -> Tuple[bytes, str, str]:
        """Download document from HTTP URL"""
        # Extract filename from URL path
        parsed_url = urlparse(http_url)
        url_path = parsed_url.path
        filename = url_path.split('/')[-1] if url_path else 'document.pdf'
        
        # Ensure filename has extension
        if '.' not in filename:
            filename = f"{filename}.pdf"
        
        max_size = max_size_mb * 1024 * 1024
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(http_url) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}: {await response.text()}")
                    
                    # Check content length if available
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > max_size:
                        raise ValueError(
                            f"File too large: {int(content_length)} bytes. Maximum: {max_size} bytes ({max_size_mb}MB)"
                        )
                    
                    # Download content
                    file_bytes = await response.read()
                    
                    # Check actual size
                    if len(file_bytes) > max_size:
                        raise ValueError(
                            f"File too large: {len(file_bytes)} bytes. Maximum: {max_size} bytes ({max_size_mb}MB)"
                        )
                    
                    # Get content type from response or filename
                    content_type = response.headers.get('content-type', 'application/octet-stream')
                    if 'octet-stream' in content_type or 'html' in content_type:
                        # Try to determine from filename
                        content_type = self._get_content_type(filename)
                    
                    logger.info(f"Downloaded from HTTP: {filename}, size: {len(file_bytes)} bytes, type: {content_type}")
                    
                    return file_bytes, content_type, filename
            
        except Exception as e:
            raise Exception(f"Failed to download from HTTP: {str(e)}")
    
    async def _read_local_file(self, file_path: str, max_size_mb: int) -> Tuple[bytes, str, str]:
        """Read local file"""
        if not os.path.exists(file_path):
            raise ValueError(f"Local file not found: {file_path}")
        
        max_size = max_size_mb * 1024 * 1024
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > max_size:
            raise ValueError(
                f"File too large: {file_size} bytes. Maximum: {max_size} bytes ({max_size_mb}MB)"
            )
        
        # Read file
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        # Extract filename
        filename = os.path.basename(file_path)
        
        # Determine content type
        content_type = self._get_content_type(filename)
        
        logger.info(f"Read local file: {filename}, size: {file_size} bytes, type: {content_type}")
        
        return file_bytes, content_type, filename
    
    def _get_content_type(self, filename: str) -> str:
        """Determine content type from filename"""
        lower_filename = filename.lower()
        
        if lower_filename.endswith('.pdf'):
            return 'application/pdf'
        elif lower_filename.endswith('.docx'):
            return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif lower_filename.endswith('.doc'):
            return 'application/msword'
        else:
            return 'application/octet-stream'


# Singleton instance
_document_download_service = None


def get_document_download_service() -> DocumentDownloadService:
    """Get singleton document download service instance"""
    global _document_download_service
    if _document_download_service is None:
        _document_download_service = DocumentDownloadService()
    return _document_download_service
