"""Application middleware."""

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings


async def force_https_middleware(request: Request, call_next):
    """
    Force HTTPS redirects when running behind a reverse proxy.

    This middleware checks for common reverse proxy headers to determine
    if the original request was made over HTTP, and redirects to HTTPS if needed.
    """
    if settings.force_https:
        # Check reverse proxy headers to determine the original protocol
        # Common headers set by reverse proxies:
        # - X-Forwarded-Proto: original protocol (http/https)
        # - X-Forwarded-Ssl: on if HTTPS
        # - X-Scheme: original scheme
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        forwarded_ssl = request.headers.get("x-forwarded-ssl", "").lower()
        x_scheme = request.headers.get("x-scheme", "").lower()

        # Determine if the original request was not HTTPS
        is_http = (
            forwarded_proto == "http" or forwarded_ssl == "off" or x_scheme == "http"
        )

        # Only redirect GET requests to avoid losing POST data
        if is_http and request.method == "GET":
            # Construct HTTPS URL
            url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(url), status_code=301)

    response = await call_next(request)
    return response


async def add_security_headers(request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # XSS Protection (legacy, but doesn't hurt)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://challenges.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self' https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; "
        "frame-ancestors 'none';"
    )

    # Enforce HTTPS (if not in debug mode)
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=()"
    )

    return response
