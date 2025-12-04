"""Rate limiting utilities for the application."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def get_client_identifier(request: Request) -> str:
    """
    Get a unique identifier for rate limiting.

    For authenticated API requests, use the client_id from the token.
    For unauthenticated requests (web UI), use IP address.
    """
    # Try to get client_id from request state (set by auth dependency)
    if hasattr(request.state, "client_id"):
        identifier = f"client:{request.state.client_id}"
        logger.debug(f"Rate limit identifier: {identifier}")
        return identifier

    # Fall back to IP address for unauthenticated requests
    ip = get_remote_address(request)
    logger.debug(f"Rate limit identifier (IP): {ip}")
    return ip


# Initialize the limiter with Redis-like behavior but using in-memory storage
# For production, consider using Redis backend: storage_uri="redis://localhost:6379"
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=[],  # No default limits, we'll apply per-route
    storage_uri="memory://",  # Use in-memory storage (upgrade to Redis for multi-instance deployments)
    strategy="fixed-window",  # Use fixed-window strategy for predictable behavior
)


def get_email_rate_limits() -> list[str]:
    """
    Get rate limit strings for email sending endpoint.

    Returns a list of rate limit strings in slowapi format.
    Each client gets multiple tiers of protection.
    """
    return [
        f"{settings.rate_limit_per_minute}/minute",
        f"{settings.rate_limit_per_hour}/hour",
        f"{settings.rate_limit_per_day}/day",
    ]


def get_global_rate_limits() -> list[str]:
    """
    Get global rate limit strings (across all clients).

    These limits protect the entire service from overload.
    """
    return [
        f"{settings.global_rate_limit_per_second}/second",
        f"{settings.global_rate_limit_per_minute}/minute",
    ]
