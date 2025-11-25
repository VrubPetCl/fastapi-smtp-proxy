"""Utility functions for extracting real client IP addresses from proxy headers."""
import logging
from typing import Optional
from fastapi import Request

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """
    Extract the real client IP address from request headers.

    This function is designed for deployments behind Cloudflare and other reverse proxies.
    Since firewall rules only allow Cloudflare IPs to connect directly, we can trust
    the proxy headers they inject.

    Header priority order:
    1. CF-Connecting-IP - Cloudflare's header containing the original client IP
    2. X-Forwarded-For - Standard proxy header (uses leftmost IP from the chain)
    3. X-Real-IP - Alternative proxy header
    4. request.client.host - Direct connection IP (fallback)

    Args:
        request: FastAPI Request object

    Returns:
        str: The client's IP address, or "unknown" if unable to determine

    Examples:
        >>> # Behind Cloudflare
        >>> # CF-Connecting-IP: 1.2.3.4
        >>> get_client_ip(request)  # Returns: "1.2.3.4"

        >>> # X-Forwarded-For with multiple proxies
        >>> # X-Forwarded-For: 1.2.3.4, proxy1, proxy2
        >>> get_client_ip(request)  # Returns: "1.2.3.4" (leftmost)
    """
    # Priority 1: Cloudflare's CF-Connecting-IP header
    # This is the most reliable when behind Cloudflare
    cf_connecting_ip = request.headers.get("cf-connecting-ip")
    if cf_connecting_ip:
        ip = cf_connecting_ip.strip()
        logger.debug(f"Client IP from CF-Connecting-IP: {ip}")
        return ip

    # Priority 2: X-Forwarded-For header
    # Format: "client, proxy1, proxy2"
    # The leftmost IP is the original client
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        # Take the leftmost IP (original client)
        ips = [ip.strip() for ip in x_forwarded_for.split(",")]
        if ips and ips[0]:
            ip = ips[0]
            logger.debug(f"Client IP from X-Forwarded-For: {ip} (chain: {x_forwarded_for})")
            return ip

    # Priority 3: X-Real-IP header
    # Some proxies set this instead of X-Forwarded-For
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        ip = x_real_ip.strip()
        logger.debug(f"Client IP from X-Real-IP: {ip}")
        return ip

    # Priority 4: Direct connection (fallback)
    # This should only happen in development or if firewall rules are bypassed
    if request.client and request.client.host:
        ip = request.client.host
        logger.debug(f"Client IP from direct connection: {ip}")
        return ip

    # Unable to determine IP
    logger.warning("Unable to determine client IP address from request")
    return "unknown"


def get_client_ip_with_metadata(request: Request) -> dict:
    """
    Extract client IP with additional metadata about the source.

    Useful for debugging and security logging.

    Args:
        request: FastAPI Request object

    Returns:
        dict: Contains 'ip', 'source', and 'headers' information

    Example:
        >>> result = get_client_ip_with_metadata(request)
        >>> print(result)
        {
            'ip': '1.2.3.4',
            'source': 'cf-connecting-ip',
            'headers': {
                'cf-connecting-ip': '1.2.3.4',
                'x-forwarded-for': '1.2.3.4, proxy1',
                'x-real-ip': None
            }
        }
    """
    headers = {
        "cf-connecting-ip": request.headers.get("cf-connecting-ip"),
        "x-forwarded-for": request.headers.get("x-forwarded-for"),
        "x-real-ip": request.headers.get("x-real-ip"),
        "direct": request.client.host if request.client else None
    }

    # Determine which header was used
    source = "unknown"
    ip = "unknown"

    if headers["cf-connecting-ip"]:
        ip = headers["cf-connecting-ip"].strip()
        source = "cf-connecting-ip"
    elif headers["x-forwarded-for"]:
        ips = [ip.strip() for ip in headers["x-forwarded-for"].split(",")]
        if ips and ips[0]:
            ip = ips[0]
            source = "x-forwarded-for"
    elif headers["x-real-ip"]:
        ip = headers["x-real-ip"].strip()
        source = "x-real-ip"
    elif headers["direct"]:
        ip = headers["direct"]
        source = "direct"

    return {
        "ip": ip,
        "source": source,
        "headers": headers
    }
