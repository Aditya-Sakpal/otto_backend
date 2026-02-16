"""
UUID Validation Utilities

Provides UUID validation for API request fields to ensure proper ID format.
"""

from typing import Any
from uuid import UUID


def validate_uuid(value: Any, field_name: str = "field") -> str:
    """
    Validate that a value is a valid UUID string.
    
    Args:
        value: The value to validate
        field_name: Name of the field for error messages
        
    Returns:
        str: The UUID as a string if valid
        
    Raises:
        ValueError: If the value is not a valid UUID
    """
    if value is None:
        raise ValueError(f"{field_name} cannot be null")
    
    if not isinstance(value, (str, UUID)):
        raise ValueError(f"{field_name} must be a valid UUID string")
    
    # Try to parse as UUID to validate format
    try:
        # Convert to string if UUID object
        if isinstance(value, UUID):
            return str(value)
        
        # Validate string is valid UUID format
        uuid_obj = UUID(value, version=4)
        return value
    except (ValueError, AttributeError):
        raise ValueError(
            f"{field_name} must be a valid UUID (format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)"
        )


def create_uuid_validator(field_name: str):
    """
    Create a Pydantic field validator for UUID fields.
    
    Args:
        field_name: Name of the field for error messages
        
    Returns:
        A field validator function
    """
    def validator(value: Any) -> str:
        return validate_uuid(value, field_name)
    return validator


# Common UUID field validators
call_id_validator = create_uuid_validator("call_id")
conversation_id_validator = create_uuid_validator("conversation_id")
job_id_validator = create_uuid_validator("job_id")
sop_id_validator = create_uuid_validator("sop_id")
company_id_validator = create_uuid_validator("company_id")
message_id_validator = create_uuid_validator("message_id")

