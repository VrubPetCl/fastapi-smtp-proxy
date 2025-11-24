"""Application configuration management."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "FastAPI SMTP Proxy"
    app_version: str = "1.0.0"
    debug: bool = False

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 720  # 30 days

    # Encryption
    encryption_key: str  # Fernet key for encrypting sensitive data (SMTP passwords, etc.)

    # Database
    database_url: str = "sqlite+aiosqlite:///./smtp_proxy.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: Optional[str] = None  # Comma-separated list of allowed origins

    # Security
    force_https: bool = False  # Force HTTPS redirects (for reverse proxy deployments)

    # Cloudflare Turnstile (optional - if not set, captcha is disabled)
    cf_turnstile_site_key: Optional[str] = None
    cf_turnstile_secret_key: Optional[str] = None

    @property
    def turnstile_enabled(self) -> bool:
        """Check if Cloudflare Turnstile is enabled."""
        return bool(self.cf_turnstile_site_key and self.cf_turnstile_secret_key)

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
