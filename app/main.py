"""FastAPI SMTP Proxy main application."""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.lifespan import lifespan
from app.core.middleware import force_https_middleware, add_security_headers
from app.core.exceptions import http_exception_handler
from app.core.rate_limit import limiter
from app.api.routes import health, email, clients, api_keys, analytics
from app import web

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="FastAPI-based SMTP proxy for sending emails via preconfigured SMTP connections",
    lifespan=lifespan,
)

# Add rate limiter state to app
app.state.limiter = limiter

# Add CORS middleware
# Configure allowed origins from environment or use secure defaults
allowed_origins = (
    settings.cors_origins.split(",")
    if hasattr(settings, "cors_origins") and settings.cors_origins
    else ["http://localhost:8000", "https://localhost:8000"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Restricted to specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # Specific methods only
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-API-Key",
    ],  # Specific headers only
)

# Add custom middleware
app.middleware("http")(force_https_middleware)
app.middleware("http")(add_security_headers)

# Add SlowAPI middleware for rate limiting
app.add_middleware(SlowAPIMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(health.router)
app.include_router(email.router)
app.include_router(clients.router)
app.include_router(api_keys.router)
app.include_router(analytics.client_router)
app.include_router(analytics.admin_router)
app.include_router(web.router)


# Custom rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    """Handle rate limit exceeded errors with a custom response."""
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": "Rate limit exceeded",
            "message": str(exc.detail),
        },
    )


# Exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
