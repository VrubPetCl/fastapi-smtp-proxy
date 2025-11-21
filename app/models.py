"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional
from datetime import datetime


class EmailRequest(BaseModel):
    """Email request model matching wp-smtp-api structure."""

    to: List[EmailStr] = Field(..., description="List of recipient email addresses")
    subject: str = Field(..., min_length=1, max_length=998, description="Email subject")
    content: str = Field(..., description="Email body content (HTML or plain text)")
    from_email: Optional[EmailStr] = Field(None, alias="from", description="Sender email address")
    from_name: Optional[str] = Field(None, description="Sender display name")
    timestamp: int = Field(..., description="Unix timestamp for replay prevention")
    content_type: str = Field(default="text/html", description="Content type: text/html or text/plain")
    headers: Optional[List[str]] = Field(default=None, description="Additional email headers")
    reply_to: Optional[EmailStr] = Field(None, description="Reply-to email address")
    cc: Optional[List[EmailStr]] = Field(default=None, description="CC recipients")
    bcc: Optional[List[EmailStr]] = Field(default=None, description="BCC recipients")
    attachments: Optional[List[dict]] = Field(default=None, description="Email attachments")

    @field_validator('content_type')
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        """Validate content type is either text/html or text/plain."""
        if v not in ['text/html', 'text/plain']:
            raise ValueError('content_type must be either "text/html" or "text/plain"')
        return v

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Validate timestamp is not too old (prevent replay attacks)."""
        current_timestamp = int(datetime.now().timestamp())
        max_age = 3600  # 1 hour

        if abs(current_timestamp - v) > max_age:
            raise ValueError(f'Timestamp is too old or in the future (max age: {max_age} seconds)')

        return v

    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "to": ["recipient@example.com"],
                "subject": "Test Email",
                "content": "<h1>Hello World</h1><p>This is a test email.</p>",
                "from": "sender@example.com",
                "from_name": "Sender Name",
                "timestamp": 1700000000,
                "content_type": "text/html",
                "reply_to": "reply@example.com",
                "cc": ["cc@example.com"],
                "bcc": ["bcc@example.com"]
            }
        }


class EmailResponse(BaseModel):
    """Email response model."""

    success: bool
    message: str
    email_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model."""

    success: bool = False
    error: str
    message: str


class ClientCreate(BaseModel):
    """Model for creating a new client."""

    name: str = Field(..., min_length=1, max_length=255)
    smtp_host: str = Field(..., min_length=1, max_length=255)
    smtp_port: int = Field(..., ge=1, le=65535)
    smtp_username: str = Field(..., min_length=1, max_length=255)
    smtp_password: str = Field(..., min_length=1)
    smtp_use_tls: bool = Field(default=True)
    smtp_use_ssl: bool = Field(default=False)
    default_from_email: Optional[EmailStr] = None
    default_from_name: Optional[str] = None


class ClientResponse(BaseModel):
    """Model for client response."""

    id: int
    name: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    default_from_email: Optional[str]
    default_from_name: Optional[str]
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class APIKeyCreate(BaseModel):
    """Model for creating a new API key."""

    client_id: int
    name: str = Field(..., min_length=1, max_length=255, description="API key name/description")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration date")


class APIKeyResponse(BaseModel):
    """Model for API key response."""

    id: int
    client_id: int
    name: str
    key: str  # JWT token (only shown on creation)
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True
