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

        # Log credential status (without exposing secrets)
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            logger.info(
                f"S3 service initializing without explicit credentials. "
                f"Will use default credential chain (IAM role, environment, or config files). "
                f"Buckets: documents='{self.documents_bucket}', audio='{self.audio_bucket}', region='{self.region}'"
            )
        else:
            logger.info(
                f"S3 service initializing with explicit AWS credentials. "
                f"Buckets: documents='{self.documents_bucket}', audio='{self.audio_bucket}', region='{self.region}'"
            )

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
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            logger.error(
                f"Error uploading file to S3 bucket '{bucket_name}': "
                f"Code={error_code}, Message={error_message}, Key={s3_key}, "
                f"AWS_ACCESS_KEY_ID={'***' if settings.AWS_ACCESS_KEY_ID else 'Not set'}, "
                f"Region={self.region}"
            )

            # Provide more helpful error messages for common issues
            if error_code == 'AccessDenied':
                raise PermissionError(
                    f"Access denied uploading to S3 bucket '{bucket_name}'. "
                    f"Please check: 1) AWS credentials have PutObject permission, "
                    f"2) Bucket policy allows writes, 3) IAM user/role has s3:PutObject permission, "
                    f"4) Bucket name '{bucket_name}' exists and is accessible in region '{self.region}'"
                ) from e
            elif error_code == 'NoSuchBucket':
                raise ValueError(
                    f"S3 bucket '{bucket_name}' does not exist in region '{self.region}'"
                ) from e

            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading file to S3 bucket '{bucket_name}': {e}")
            raise

    async def upload_from_url(
        self,
        url: str,
        s3_key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        bucket_type: Optional[BucketType] = None,
        headers: Optional[dict] = None,
    ) -> str:
        try:
            if bucket_type is None:
                bucket_type = self._determine_bucket_type(content_type)
            bucket_name = self._get_bucket_name(bucket_type)

            # 1. Use follow_redirects=True (Crucial for CTM)
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                async with client.stream('GET', url, headers=headers) as response:
                    # If CTM returns 404 or 403, this will catch it
                    response.raise_for_status()

                    if not content_type:
                        content_type = response.headers.get('content-type', 'audio/wav')

                    extra_args = {'ContentType': content_type}
                    if metadata:
                        extra_args['Metadata'] = {f"metadata-{k}": str(v) for k, v in metadata.items()}

                    # 2. Simplified bytes handling
                    # Since boto3's upload_fileobj is synchronous, we fetch the content
                    # CTM recordings are typically 2MB-20MB, which fits easily in memory
                    file_content = await response.aread()

                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=file_content,
                        **extra_args
                    )

            s3_url = f"https://{bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            logger.info(f"Successfully moved CTM recording to S3: {s3_key}")
            return s3_url

        except httpx.HTTPStatusError as e:
            logger.error(f"CTM Link returned error {e.response.status_code} for URL: {url}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in upload_from_url: {e}")
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

    def generate_presigned_url(
        self,
        s3_key: str,
        expiration: int = 14400,
        content_type: Optional[str] = None,
        bucket_type: Optional[BucketType] = None,
    ) -> str:
        """
        Generate a pre-signed URL for uploading a file to S3.

        Args:
            s3_key: S3 key (path) for the file
            expiration: URL expiration time in seconds (default: 3600 = 1 hour)
            content_type: Optional content type (e.g., "audio/x-wav", "audio/mpeg")
            bucket_type: Optional bucket type ('documents' or 'audio').
                        If not provided, will be determined from content_type

        Returns:
            Pre-signed URL for PUT operation
        """
        try:
            # Determine bucket type if not provided
            if bucket_type is None:
                bucket_type = self._determine_bucket_type(content_type)

            bucket_name = self._get_bucket_name(bucket_type)

            # Generate pre-signed URL for PUT operation
            params = {
                "Bucket": bucket_name,
                "Key": s3_key,
            }

            # Add content type if provided
            if content_type:
                params["ContentType"] = content_type

            url = self.s3_client.generate_presigned_url(
                "put_object",
                Params=params,
                ExpiresIn=expiration,
            )

            logger.info(
                f"Generated pre-signed URL for S3 bucket '{bucket_name}' (type: {bucket_type}): {s3_key}"
            )
            return url

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                f"Error generating pre-signed URL for S3 bucket '{bucket_name}': "
                f"Code={error_code}, Key={s3_key}"
            )
            raise
        except Exception as e:
            logger.error(f"Unexpected error generating pre-signed URL: {e}")
            raise

    async def delete_file(self, s3_key: str, bucket_type: Optional[BucketType] = None) -> bool:
        """
        Delete file from S3.

        Args:
            s3_key: S3 key (path) of the file to delete
            bucket_type: Optional bucket type ('documents' or 'audio').
                        If not provided, will default to documents

        Returns:
            True if file was deleted, False if it didn't exist
        """
        try:
            if bucket_type is None:
                bucket_type = "documents"

            bucket_name = self._get_bucket_name(bucket_type)

            self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            logger.info(f"Deleted file from S3 bucket '{bucket_name}': {s3_key}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                logger.warning(f"File not found in S3 bucket '{bucket_name}': {s3_key}")
                return False
            logger.error(f"Error deleting file from S3 bucket '{bucket_name}': {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting file from S3: {e}")
            raise


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
