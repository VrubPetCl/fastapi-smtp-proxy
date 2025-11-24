"""Cloudflare Turnstile captcha verification."""
import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str, remote_ip: Optional[str] = None) -> bool:
    """
    Verify a Cloudflare Turnstile token.

    Args:
        token: The Turnstile token from the client
        remote_ip: Optional client IP address for additional validation

    Returns:
        bool: True if verification successful, False otherwise
    """
    if not settings.turnstile_enabled:
        # If Turnstile is not configured, bypass verification
        logger.info("Turnstile not enabled, skipping verification")
        return True

    if not token:
        logger.warning("No Turnstile token provided")
        return False

    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "secret": settings.cf_turnstile_secret_key,
                "response": token,
            }

            # Add remote IP if provided (optional but recommended)
            if remote_ip:
                payload["remoteip"] = remote_ip

            response = await client.post(
                TURNSTILE_VERIFY_URL,
                data=payload,
                timeout=10.0
            )

            if response.status_code != 200:
                logger.error(f"Turnstile API returned status {response.status_code}")
                return False

            result = response.json()

            if result.get("success"):
                logger.info("Turnstile verification successful")
                return True
            else:
                error_codes = result.get("error-codes", [])
                logger.warning(f"Turnstile verification failed: {error_codes}")
                return False

    except httpx.TimeoutException:
        logger.error("Turnstile verification timeout")
        return False
    except Exception as e:
        logger.error(f"Turnstile verification error: {str(e)}")
        return False
