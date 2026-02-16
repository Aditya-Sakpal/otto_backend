"""
Audio Service

Service for downloading and handling audio files.
"""

import os
import tempfile
import logging
from typing import Optional
from urllib.parse import urlparse
import aiohttp
import boto3
from botocore.exceptions import ClientError
from ...config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class AudioService:
    """Service for audio file operations"""
    
    def __init__(self):
        self.s3_client = None
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION or 'us-east-1'
            )
    
    async def download_audio(self, audio_url: str) -> str:
        """
        Download audio file from URL or S3, or use local file.
        
        Args:
            audio_url: S3 URL (s3://bucket/key), HTTP URL, or local file path
            
        Returns:
            Path to downloaded temporary file or local file
        """
        if audio_url.startswith('s3://'):
            return await self._download_from_s3(audio_url)
        elif audio_url.startswith('http://') or audio_url.startswith('https://'):
            return await self._download_from_http(audio_url)
        elif audio_url.startswith('file://'):
            # Local file path
            return audio_url[7:]  # Remove file:// prefix
        elif audio_url.startswith('/'):
            # Absolute local path
            if os.path.exists(audio_url):
                return audio_url
            else:
                raise ValueError(f"Local file not found: {audio_url}")
        else:
            raise ValueError(f"Unsupported audio URL format: {audio_url}")
    
    async def _download_from_s3(self, s3_url: str) -> str:
        """Download audio from S3"""
        if not self.s3_client:
            raise Exception("S3 client not configured. Set AWS credentials.")
        
        # Parse S3 URL: s3://bucket/key
        parts = s3_url[5:].split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
        
        bucket = parts[0]
        key = parts[1]
        
        # Create temporary file
        suffix = os.path.splitext(key)[1] or '.wav'
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        )
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            self.s3_client.download_file(bucket, key, temp_path)
            return temp_path
        except ClientError as e:
            os.remove(temp_path)
            raise Exception(f"Failed to download from S3: {str(e)}")
    
    async def _download_from_http(self, http_url: str) -> str:
        """Download audio from HTTP URL"""
        # Extract filename and extension from URL path (before query parameters)
        from urllib.parse import urlparse
        parsed_url = urlparse(http_url)
        url_path = parsed_url.path
        suffix = os.path.splitext(url_path)[1] or '.wav'
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix
        )
        temp_path = temp_file.name
        temp_file.close()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(http_url) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}: {await response.text()}")
                    
                    with open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
            
            return temp_path
            
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise Exception(f"Failed to download from HTTP: {str(e)}")
    
    def cleanup_temp_file(self, file_path: str) -> None:
        """Delete temporary audio file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass  # Ignore cleanup errors


# Singleton instance
_audio_service: Optional[AudioService] = None


def get_audio_service() -> AudioService:
    """Get singleton audio service instance"""
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioService()
    return _audio_service

