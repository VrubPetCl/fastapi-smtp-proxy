"""Database models using SQLAlchemy."""
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text, Float, Index
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Client(Base):
    """Client model - represents an SMTP client configuration."""

    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)

    # SMTP Configuration
    smtp_host = Column(String(255), nullable=False)
    smtp_port = Column(Integer, nullable=False)
    smtp_username = Column(String(255), nullable=False)
    smtp_password = Column(Text, nullable=False)  # Should be encrypted in production
    smtp_use_tls = Column(Boolean, default=True)
    smtp_use_ssl = Column(Boolean, default=False)

    # Default email settings
    default_from_email = Column(String(255), nullable=True)
    default_from_name = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    api_keys = relationship("APIKey", back_populates="client", cascade="all, delete-orphan")
    email_logs = relationship("EmailLog", back_populates="client", cascade="all, delete-orphan")
    analytics_snapshots = relationship("AnalyticsSnapshot", back_populates="client", cascade="all, delete-orphan")


class APIKey(Base):
    """API Key model - JWT tokens for client authentication."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=True)  # Description/name for the key (optional)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)  # Hash of the JWT

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    client = relationship("Client", back_populates="api_keys")
    email_logs = relationship("EmailLog", back_populates="api_key")

    @property
    def key_prefix(self) -> str:
        """Get the first 8 characters of the key for display."""
        return self.key_hash[:8] if self.key_hash else ""

    @property
    def key_suffix(self) -> str:
        """Get the last 4 characters of the key for display."""
        return self.key_hash[-4:] if self.key_hash else ""

    @property
    def description(self) -> str:
        """Alias for name to match template expectations."""
        return self.name if self.name else ""


class EmailLog(Base):
    """Email log model - tracks sent emails with detailed analytics."""

    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    api_key_id = Column(Integer, ForeignKey("api_keys.id"), nullable=True, index=True)

    # Email details
    to_addresses = Column(Text, nullable=False)  # JSON array of recipients
    to_count = Column(Integer, default=1, nullable=False)  # Number of recipients
    cc_count = Column(Integer, default=0, nullable=False)  # Number of CC recipients
    bcc_count = Column(Integer, default=0, nullable=False)  # Number of BCC recipients
    subject = Column(String(998), nullable=False)
    from_email = Column(String(255), nullable=True)
    content_type = Column(String(50), nullable=True)  # text/html or text/plain

    # Status and error tracking
    status = Column(String(50), nullable=False, index=True)  # sent, failed, etc.
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True, index=True)  # SMTP error category

    # Attachment analytics
    attachment_count = Column(Integer, default=0, nullable=False)
    total_attachment_size = Column(Integer, default=0, nullable=False)  # bytes

    # Performance metrics
    processing_time_ms = Column(Float, nullable=True)  # Total processing time
    smtp_connection_time_ms = Column(Float, nullable=True)  # SMTP connection time

    # Temporal data for analytics
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)  # 1, 2, 3, 4
    month = Column(Integer, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0-6 (Monday-Sunday)
    hour = Column(Integer, nullable=False)  # 0-23

    # SMTP response
    smtp_response = Column(Text, nullable=True)

    # Security tracking
    source_ip = Column(String(45), nullable=True, index=True)  # IPv4 (15) or IPv6 (45)
    user_agent = Column(String(500), nullable=True)
    country_code = Column(String(2), nullable=True, index=True)  # ISO 3166-1 alpha-2

    # Relationships
    client = relationship("Client", back_populates="email_logs")
    api_key = relationship("APIKey", back_populates="email_logs")

    __table_args__ = (
        Index('idx_client_quarter', 'client_id', 'year', 'quarter'),
        Index('idx_status_quarter', 'status', 'year', 'quarter'),
        Index('idx_sent_at_client', 'sent_at', 'client_id'),
        Index('idx_source_ip_sent_at', 'source_ip', 'sent_at'),
    )


class ArchivedEmailLog(Base):
    """Archived email logs - stores rotated data from previous quarters."""

    __tablename__ = "archived_email_logs"

    id = Column(Integer, primary_key=True, index=True)
    original_id = Column(Integer, nullable=False, index=True)  # Original EmailLog ID
    client_id = Column(Integer, nullable=False, index=True)
    api_key_id = Column(Integer, nullable=True)

    # Email details (minimal for archival)
    to_count = Column(Integer, default=1, nullable=False)
    cc_count = Column(Integer, default=0, nullable=False)
    bcc_count = Column(Integer, default=0, nullable=False)
    subject_hash = Column(String(64), nullable=True)  # SHA256 hash for privacy
    content_type = Column(String(50), nullable=True)

    # Status and error tracking
    status = Column(String(50), nullable=False, index=True)
    error_type = Column(String(100), nullable=True, index=True)

    # Attachment analytics
    attachment_count = Column(Integer, default=0, nullable=False)
    total_attachment_size = Column(Integer, default=0, nullable=False)

    # Performance metrics
    processing_time_ms = Column(Float, nullable=True)
    smtp_connection_time_ms = Column(Float, nullable=True)

    # Temporal data
    sent_at = Column(DateTime, nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)
    hour = Column(Integer, nullable=False)

    # Archival metadata
    archived_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_archived_client_quarter', 'client_id', 'year', 'quarter'),
        Index('idx_archived_sent_at', 'sent_at'),
    )


class AnalyticsSnapshot(Base):
    """Quarterly analytics snapshots - aggregated metrics per client."""

    __tablename__ = "analytics_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)

    # Time period
    year = Column(Integer, nullable=False, index=True)
    quarter = Column(Integer, nullable=False, index=True)  # 1, 2, 3, 4
    month = Column(Integer, nullable=True, index=True)  # Optional: monthly snapshots

    # Volume metrics
    total_emails = Column(Integer, default=0, nullable=False)
    total_sent = Column(Integer, default=0, nullable=False)
    total_failed = Column(Integer, default=0, nullable=False)
    success_rate = Column(Float, default=0.0, nullable=False)  # Percentage

    # Recipient metrics
    total_recipients = Column(Integer, default=0, nullable=False)
    total_cc = Column(Integer, default=0, nullable=False)
    total_bcc = Column(Integer, default=0, nullable=False)

    # Attachment metrics
    emails_with_attachments = Column(Integer, default=0, nullable=False)
    total_attachments = Column(Integer, default=0, nullable=False)
    total_attachment_bytes = Column(Integer, default=0, nullable=False)
    avg_attachment_size = Column(Float, default=0.0, nullable=False)

    # Performance metrics
    avg_processing_time_ms = Column(Float, default=0.0, nullable=False)
    avg_smtp_connection_time_ms = Column(Float, default=0.0, nullable=False)
    max_processing_time_ms = Column(Float, default=0.0, nullable=False)
    min_processing_time_ms = Column(Float, default=0.0, nullable=False)

    # Content type distribution
    html_emails = Column(Integer, default=0, nullable=False)
    plain_text_emails = Column(Integer, default=0, nullable=False)

    # Peak usage metrics
    peak_hour = Column(Integer, nullable=True)  # Hour with most emails (0-23)
    peak_day = Column(Integer, nullable=True)  # Day of week with most emails (0-6)
    peak_emails_in_hour = Column(Integer, default=0, nullable=False)

    # Error analytics
    error_types_json = Column(Text, nullable=True)  # JSON with error type counts

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = relationship("Client", back_populates="analytics_snapshots")

    __table_args__ = (
        Index('idx_analytics_client_period', 'client_id', 'year', 'quarter', 'month'),
    )


class LoginAttempt(Base):
    """Track login attempts for security monitoring."""

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False, index=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False, index=True)
    failure_reason = Column(String(100), nullable=True)  # invalid_password, user_not_found, etc.
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    country_code = Column(String(2), nullable=True, index=True)  # ISO 3166-1 alpha-2
    city = Column(String(100), nullable=True)

    __table_args__ = (
        Index('idx_ip_attempted_at', 'ip_address', 'attempted_at'),
        Index('idx_username_attempted_at', 'username', 'attempted_at'),
        Index('idx_success_attempted_at', 'success', 'attempted_at'),
    )


class AdminUser(Base):
    """Admin user model for dashboard access."""

    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)

    # Permissions
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    password_reset_tokens = relationship("PasswordResetToken", back_populates="admin_user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    """Password reset token model."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    admin_user = relationship("AdminUser", back_populates="password_reset_tokens")
