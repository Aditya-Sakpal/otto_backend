"""
Custom exceptions for Otto Intelligence Service
"""

from fastapi import HTTPException, status


class OttoIntelligenceException(Exception):
    """Base exception for Otto Intelligence Service"""
    pass


class APIKeyInvalidError(HTTPException):
    """Raised when API key is invalid or missing"""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


class ResourceNotFoundError(HTTPException):
    """Raised when requested resource is not found"""
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} '{identifier}' not found",
        )


class ResourceConflictError(HTTPException):
    """Raised when resource already exists"""
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
        )


class ValidationError(HTTPException):
    """Raised when validation fails"""
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class ProcessingError(OttoIntelligenceException):
    """Raised when processing fails"""
    pass


class TranscriptionError(ProcessingError):
    """Raised when transcription fails"""
    pass


class SummarizationError(ProcessingError):
    """Raised when summarization fails"""
    pass


class RAGIndexingError(ProcessingError):
    """Raised when RAG indexing fails"""
    pass



