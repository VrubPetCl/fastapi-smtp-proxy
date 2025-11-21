"""Database models using SQLAlchemy."""
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
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


class APIKey(Base):
    """API Key model - JWT tokens for client authentication."""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=False)  # Description/name for the key
    key_hash = Column(String(255), unique=True, nullable=False, index=True)  # Hash of the JWT

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    client = relationship("Client", back_populates="api_keys")


class EmailLog(Base):
    """Email log model - tracks sent emails."""

    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)

    # Email details
    to_addresses = Column(Text, nullable=False)  # JSON array of recipients
    subject = Column(String(998), nullable=False)
    from_email = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False)  # sent, failed, etc.
    error_message = Column(Text, nullable=True)

    # Metadata
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    smtp_response = Column(Text, nullable=True)

    # Relationships
    client = relationship("Client", back_populates="email_logs")
