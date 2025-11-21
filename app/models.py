"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import List, Optional, Dict
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


# ============================================================================
# Analytics Models
# ============================================================================

class AnalyticsSnapshotResponse(BaseModel):
    """Analytics snapshot response model."""

    id: int
    client_id: int
    year: int
    quarter: int
    month: Optional[int]

    # Volume metrics
    total_emails: int
    total_sent: int
    total_failed: int
    success_rate: float

    # Recipient metrics
    total_recipients: int
    total_cc: int
    total_bcc: int

    # Attachment metrics
    emails_with_attachments: int
    total_attachments: int
    total_attachment_bytes: int
    avg_attachment_size: float

    # Performance metrics
    avg_processing_time_ms: float
    avg_smtp_connection_time_ms: float
    max_processing_time_ms: float
    min_processing_time_ms: float

    # Content type distribution
    html_emails: int
    plain_text_emails: int

    # Peak usage metrics
    peak_hour: Optional[int]
    peak_day: Optional[int]
    peak_emails_in_hour: int

    # Error analytics
    error_types_json: Optional[str]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuarterlyAnalytics(BaseModel):
    """Quarterly analytics summary."""

    year: int
    quarter: int
    client_name: str
    total_emails: int
    success_rate: float
    total_recipients: int
    avg_processing_time_ms: float


class DailyMetrics(BaseModel):
    """Daily email metrics."""

    date: str  # YYYY-MM-DD
    total_emails: int
    total_sent: int
    total_failed: int
    success_rate: float


class HourlyDistribution(BaseModel):
    """Hourly distribution of emails."""

    hour: int  # 0-23
    email_count: int


class ErrorDistribution(BaseModel):
    """Error type distribution."""

    error_type: str
    count: int
    percentage: float


class AnalyticsSummary(BaseModel):
    """Comprehensive analytics summary."""

    # Time period
    period: str
    start_date: datetime
    end_date: datetime

    # Overall metrics
    total_emails: int
    total_sent: int
    total_failed: int
    success_rate: float

    # Volume trends
    daily_metrics: List[DailyMetrics]
    hourly_distribution: List[HourlyDistribution]

    # Performance
    avg_processing_time_ms: float
    p95_processing_time_ms: Optional[float]
    p99_processing_time_ms: Optional[float]

    # Top errors
    top_errors: List[ErrorDistribution]

    # Attachments
    total_attachments: int
    total_attachment_bytes: int
    emails_with_attachments: int


class RotationSummary(BaseModel):
    """Summary of quarterly rotation operation."""

    quarter: str  # "2024-Q1"
    emails_archived: int
    emails_deleted: int
    snapshot_created: bool
    archived_at: datetime
