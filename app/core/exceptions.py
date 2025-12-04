"""Exception handlers."""

from fastapi import HTTPException
from fastapi.responses import JSONResponse


async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": (
                exc.detail
                if isinstance(exc.detail, str)
                else exc.detail.get("error", "")
            ),
            "message": (
                exc.detail
                if isinstance(exc.detail, str)
                else exc.detail.get("message", "")
            ),
        },
    )
