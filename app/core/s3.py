"""
S3 storage utility.

Handles uploading files to AWS S3.
Supports separate buckets for documents and audio files.
"""
from typing import Optional, Literal
from datetime import datetime
import uuid

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not installed. URL streaming will fail. Install with: pip install httpx")

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.warning("boto3 not installed. S3 uploads will fail. Install with: pip install boto3")


BucketType = Literal["documents", "audio"]


class S3Service:
    """Service for S3 file uploads."""

    def __init__(self):
        """Initialize S3 service."""
        if not BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is not installed. Install with: pip install boto3")

        # Support both new separate buckets and legacy single bucket
        self.documents_bucket = settings.S3_DOCUMENTS_BUCKET or settings.S3_BUCKET
        self.audio_bucket = settings.S3_AUDIO_BUCKET or settings.S3_BUCKET

        if not self.documents_bucket or not self.audio_bucket:
            raise ValueError(
                "S3 buckets not configured. Set S3_DOCUMENTS_BUCKET and S3_AUDIO_BUCKET "
                "(or S3_BUCKET for backward compatibility)"
            )

        self.region = settings.AWS_REGION

        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID if settings.AWS_ACCESS_KEY_ID else None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY if settings.AWS_SECRET_ACCESS_KEY else None,
            region_name=self.region,
        )

    def _determine_bucket_type(self, content_type: Optional[str] = None) -> BucketType:
        """
        Determine bucket type from content type.

        Args:
            content_type: MIME type of the file

        Returns:
            Bucket type: 'documents' or 'audio'
        """
        if content_type:
            # Audio file types
            if content_type.startswith("audio/"):
                return "audio"
            # Document file types
            elif content_type.startswith("application/") or content_type.startswith("text/") or content_type.startswith("image/"):
                return "documents"

        # Default to documents if cannot determine
        return "documents"

    def _get_bucket_name(self, bucket_type: BucketType) -> str:
        """
        Get bucket name for the specified bucket type.

        Args:
            bucket_type: Type of bucket ('documents' or 'audio')

        Returns:
            Bucket name
        """
        if bucket_type == "audio":
            return self.audio_bucket
        return self.documents_bucket

    def generate_s3_key(self, prefix: str, filename: Optional[str] = None, extension: str = "wav") -> str:
        """
        Generate S3 key for a file.

        Args:
            prefix: Prefix path (e.g., "recordings", "audio")
            filename: Optional filename (will generate UUID if not provided)
            extension: File extension (default: "wav")

        Returns:
            S3 key path
        """
        if filename:
            # Use provided filename but ensure it's safe
            safe_filename = filename.replace(" ", "_").replace("/", "_")
        else:
            # Generate unique filename
            timestamp = datetime.utcnow().strftime("%Y%m%d")
            unique_id = str(uuid.uuid4())[:8]
            safe_filename = f"{timestamp}_{unique_id}"

        return f"{prefix}/{safe_filename}.{extension}"

    async def upload_file(
        self,
        file_bytes: bytes,
        s3_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        bucket_type: Optional[BucketType] = None,
    ) -> str:
        """
        Upload file to S3.

        Args:
            file_bytes: File content as bytes
            s3_key: S3 key (path) for the file
            content_type: Optional content type (e.g., "audio/x-wav", "application/pdf")
            metadata: Optional metadata dictionary
            bucket_type: Optional bucket type ('documents' or 'audio').
                        If not provided, will be determined from content_type

        Returns:
            S3 URL of the uploaded file
        """
        try:
            # Determine bucket type if not provided
            if bucket_type is None:
                bucket_type = self._determine_bucket_type(content_type)

            bucket_name = self._get_bucket_name(bucket_type)

            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type

            if metadata:
                # Convert metadata to S3 metadata format (string values only)
                s3_metadata = {f"metadata-{k}": str(v) for k, v in metadata.items()}
                extra_args['Metadata'] = s3_metadata

            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=file_bytes,
                **extra_args
            )

            # Generate public URL
            url = f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

            logger.info(f"Uploaded file to S3 bucket '{bucket_name}' (type: {bucket_type}): {s3_key}")
            return url

        except ClientError as e:
            logger.error(f"Error uploading file to S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading file to S3: {e}")
            raise

    async def upload_from_url(
        self,
        url: str,
        s3_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        bucket_type: Optional[BucketType] = None,
    ) -> str:
        """
        Stream file from URL directly to S3 (avoids loading large files into RAM).

        Args:
            url: Source URL to download from
            s3_key: S3 key (path) for the file
            content_type: Optional content type (e.g., "audio/mpeg", "audio/x-wav")
            metadata: Optional metadata dictionary
            bucket_type: Optional bucket type ('documents' or 'audio').
                        If not provided, will be determined from content_type

        Returns:
            S3 URL of the uploaded file
        """
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed. Install with: pip install httpx")

        try:
            # Determine bucket type if not provided
            if bucket_type is None:
                bucket_type = self._determine_bucket_type(content_type)

            bucket_name = self._get_bucket_name(bucket_type)

            # Stream from URL to S3
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout for large files
                async with client.stream('GET', url) as response:
                    response.raise_for_status()

                    # Get content type from response if not provided
                    if not content_type:
                        content_type = response.headers.get('content-type', 'application/octet-stream')

                    extra_args = {}
                    if content_type:
                        extra_args['ContentType'] = content_type

                    if metadata:
                        # Convert metadata to S3 metadata format (string values only)
                        s3_metadata = {f"metadata-{k}": str(v) for k, v in metadata.items()}
                        extra_args['Metadata'] = s3_metadata

                    # Use upload_fileobj for streaming
                    from botocore.awsrequest import AWSRequest
                    from botocore.endpoint import Endpoint
                    from botocore.auth import SigV4Auth
                    from botocore.httpsession import URLLib3Session
                    import io

                    # Read stream in chunks and upload
                    buffer = io.BytesIO()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        buffer.write(chunk)

                    buffer.seek(0)
                    self.s3_client.upload_fileobj(
                        buffer,
                        bucket_name,
                        s3_key,
                        ExtraArgs=extra_args
                    )

            # Generate public URL
            s3_url = f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"

            logger.info(f"Streamed file from URL to S3 bucket '{bucket_name}' (type: {bucket_type}): {s3_key}")
            return s3_url

        except ClientError as e:
            logger.error(f"Error streaming file from URL to S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error streaming file from URL to S3: {e}")
            raise

    def get_public_url(self, s3_key: str, bucket_type: Optional[BucketType] = None) -> str:
        """
        Get public URL for an S3 key.

        Args:
            s3_key: S3 key (path)
            bucket_type: Optional bucket type ('documents' or 'audio').
                        Defaults to documents if not provided

        Returns:
            Public S3 URL
        """
        if bucket_type is None:
            bucket_type = "documents"
        bucket_name = self._get_bucket_name(bucket_type)
        return f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"


def get_s3_service() -> Optional[S3Service]:
    """
    Get S3 service instance.

    Returns:
        S3Service instance or None if not configured
    """
    try:
        return S3Service()
    except (RuntimeError, ValueError) as e:
        logger.warning(f"S3 service not available: {e}")
        return None
