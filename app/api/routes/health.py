"""Health check and debug endpoints."""

from datetime import datetime

from fastapi import APIRouter, Request

from app.config import settings
from app.ip_utils import get_client_ip_with_metadata

router = APIRouter(tags=["health"])


@router.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@router.get("/debug/ip")
async def debug_ip(request: Request):
    """
    Debug endpoint to verify IP address extraction.

    Returns detailed information about how the client IP is being detected,
    including all relevant headers and the chosen IP address.

    Useful for verifying that Cloudflare and reverse proxy headers are
    being properly forwarded and parsed.
    """
    ip_metadata = get_client_ip_with_metadata(request)

    return {
        "detected_ip": ip_metadata["ip"],
        "source": ip_metadata["source"],
        "headers": {
            "cf-connecting-ip": ip_metadata["headers"]["cf-connecting-ip"],
            "x-forwarded-for": ip_metadata["headers"]["x-forwarded-for"],
            "x-real-ip": ip_metadata["headers"]["x-real-ip"],
            "direct_connection": ip_metadata["headers"]["direct"],
        },
        "user_agent": request.headers.get("user-agent"),
        "all_headers": dict(request.headers),
        "info": {
            "description": "This endpoint shows how your IP address is being detected",
            "priority_order": [
                "1. CF-Connecting-IP (Cloudflare)",
                "2. X-Forwarded-For (leftmost IP)",
                "3. X-Real-IP (generic proxy)",
                "4. Direct connection (fallback)",
            ],
        },
    }
