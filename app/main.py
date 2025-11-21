"""FastAPI SMTP Proxy main application."""
import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.config import settings
from app.database import get_db, init_db, close_db
from app.models import (
    EmailRequest,
    EmailResponse,
    ErrorResponse,
    ClientCreate,
    ClientResponse,
    APIKeyCreate,
    APIKeyResponse,
)
from app.schemas import Client, APIKey, EmailLog, AnalyticsSnapshot, AdminUser
from app.auth import get_current_client, get_current_client_and_key, create_api_key, get_admin_user
from app.smtp_service import send_email
from app.encryption import get_encryption
from app.analytics_service import (
    get_quarter, calculate_analytics_snapshot, get_analytics_summary,
    rotate_old_quarters, archive_quarter
)
from app.models import AnalyticsSummary, AnalyticsSnapshotResponse, RotationSummary
from app import web

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    await init_db()
    yield
    # Shutdown
    logger.info("Shutting down application")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="FastAPI-based SMTP proxy for sending emails via preconfigured SMTP connections",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security headers middleware
@app.middleware("http")
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
        "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )

    # Enforce HTTPS (if not in debug mode)
    if not settings.debug:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions policy
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=()"
    )

    return response


# Include web routes
app.include_router(web.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Email Sending Endpoints
# ============================================================================

@app.post(
    "/api/send",
    response_model=EmailResponse,
    responses={
        200: {"model": EmailResponse},
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Send email via SMTP",
    description="Send an email using the authenticated client's SMTP configuration",
)
async def send_email_endpoint(
    email_request: EmailRequest,
    client_and_key: tuple = Depends(get_current_client_and_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Send an email via SMTP using the authenticated client's configuration.

    This endpoint accepts email data in the format compatible with wp-smtp-api
    and sends it through the client's preconfigured SMTP server.
    """
    client, api_key_id = client_and_key

    try:
        # Send email and get metrics
        success, message, smtp_response, metrics = await send_email(client, email_request)

        # Calculate temporal fields for analytics
        sent_at = datetime.utcnow()
        year = sent_at.year
        quarter = get_quarter(sent_at)
        month = sent_at.month
        day_of_week = sent_at.weekday()  # 0 = Monday
        hour = sent_at.hour

        # Calculate attachment metrics
        attachment_count = len(email_request.attachments) if email_request.attachments else 0
        total_attachment_size = 0
        if email_request.attachments:
            for attachment in email_request.attachments:
                # Estimate size from base64 content (approximate)
                content = attachment.get('content', '')
                # Base64 encoding increases size by ~33%, so decode size is len * 0.75
                total_attachment_size += int(len(content) * 0.75)

        # Log the email with full analytics
        email_log = EmailLog(
            client_id=client.id,
            api_key_id=api_key_id,
            to_addresses=json.dumps([str(email) for email in email_request.to]),
            to_count=len(email_request.to),
            cc_count=len(email_request.cc) if email_request.cc else 0,
            bcc_count=len(email_request.bcc) if email_request.bcc else 0,
            subject=email_request.subject,
            from_email=email_request.from_email or client.default_from_email or client.smtp_username,
            content_type=email_request.content_type,
            status="sent" if success else "failed",
            error_message=None if success else message,
            error_type=metrics.get('error_type'),
            attachment_count=attachment_count,
            total_attachment_size=total_attachment_size,
            processing_time_ms=metrics.get('processing_time_ms'),
            smtp_connection_time_ms=metrics.get('smtp_connection_time_ms'),
            sent_at=sent_at,
            year=year,
            quarter=quarter,
            month=month,
            day_of_week=day_of_week,
            hour=hour,
            smtp_response=smtp_response,
        )
        db.add(email_log)
        await db.commit()

        if success:
            return EmailResponse(
                success=True,
                message=message,
                email_id=str(email_log.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"success": False, "error": message, "message": "Failed to send email"}
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_email_endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"success": False, "error": str(e), "message": "Internal server error"}
        )


# ============================================================================
# Client Management Endpoints (Admin)
# ============================================================================

@app.post(
    "/api/admin/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new client",
    description="Create a new client with SMTP configuration (admin only)",
)
async def create_client(
    client_data: ClientCreate,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new client with SMTP configuration.

    Requires admin authentication via HTTP Basic Auth.
    """
    # Check if client name already exists
    result = await db.execute(select(Client).where(Client.name == client_data.name))
    existing_client = result.scalar_one_or_none()

    if existing_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client with name '{client_data.name}' already exists"
        )

    # Encrypt SMTP password before storing
    encryption = get_encryption()
    encrypted_password = encryption.encrypt(client_data.smtp_password)

    # Create new client
    new_client = Client(
        name=client_data.name,
        smtp_host=client_data.smtp_host,
        smtp_port=client_data.smtp_port,
        smtp_username=client_data.smtp_username,
        smtp_password=encrypted_password,  # Encrypted
        smtp_use_tls=client_data.smtp_use_tls,
        smtp_use_ssl=client_data.smtp_use_ssl,
        default_from_email=client_data.default_from_email,
        default_from_name=client_data.default_from_name,
    )

    db.add(new_client)
    await db.commit()
    await db.refresh(new_client)

    logger.info(f"Created new client: {new_client.name} (ID: {new_client.id})")

    return ClientResponse.model_validate(new_client)


@app.get(
    "/api/admin/clients",
    response_model=list[ClientResponse],
    summary="List all clients",
    description="Get a list of all clients (admin only)",
)
async def list_clients(
    skip: int = 0,
    limit: int = 100,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all clients.

    Requires admin authentication via HTTP Basic Auth.
    """
    result = await db.execute(
        select(Client)
        .order_by(Client.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    clients = result.scalars().all()

    return [ClientResponse.model_validate(client) for client in clients]


@app.get(
    "/api/admin/clients/{client_id}",
    response_model=ClientResponse,
    summary="Get client details",
    description="Get details of a specific client (admin only)",
)
async def get_client(
    client_id: int,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get client details by ID.

    Requires admin authentication via HTTP Basic Auth.
    """
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {client_id} not found"
        )

    return ClientResponse.model_validate(client)


# ============================================================================
# API Key Management Endpoints (Admin)
# ============================================================================

@app.post(
    "/api/admin/api-keys",
    response_model=APIKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description="Create a new API key for a client (admin only)",
)
async def create_api_key_endpoint(
    api_key_data: APIKeyCreate,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key for a client.

    Requires admin authentication via HTTP Basic Auth.
    """
    # Verify client exists
    result = await db.execute(select(Client).where(Client.id == api_key_data.client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {api_key_data.client_id} not found"
        )

    # Create JWT token and hash
    jwt_token, key_hash = create_api_key(
        client_id=api_key_data.client_id,
        key_name=api_key_data.name,
        expires_at=api_key_data.expires_at,
    )

    # Save API key to database
    new_api_key = APIKey(
        client_id=api_key_data.client_id,
        name=api_key_data.name,
        key_hash=key_hash,
        expires_at=api_key_data.expires_at,
    )

    db.add(new_api_key)
    await db.commit()
    await db.refresh(new_api_key)

    logger.info(
        f"Created new API key '{new_api_key.name}' for client {client.name} (ID: {client.id})"
    )

    # Return response with JWT token (only shown once!)
    response = APIKeyResponse.model_validate(new_api_key)
    response.key = jwt_token  # Include the actual JWT token in response

    return response


@app.get(
    "/api/admin/clients/{client_id}/api-keys",
    response_model=list[APIKeyResponse],
    summary="List client API keys",
    description="Get all API keys for a specific client (admin only)",
)
async def list_client_api_keys(
    client_id: int,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all API keys for a client.

    Requires admin authentication via HTTP Basic Auth.
    Note: The actual JWT tokens are not returned, only metadata.
    """
    result = await db.execute(
        select(APIKey)
        .where(APIKey.client_id == client_id)
        .order_by(APIKey.created_at.desc())
    )
    api_keys = result.scalars().all()

    responses = []
    for api_key in api_keys:
        response = APIKeyResponse.model_validate(api_key)
        response.key = "***hidden***"  # Don't expose the actual key
        responses.append(response)

    return responses


@app.delete(
    "/api/admin/api-keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API key",
    description="Deactivate an API key (admin only)",
)
async def delete_api_key(
    api_key_id: int,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate an API key.

    Requires admin authentication via HTTP Basic Auth.
    """
    result = await db.execute(select(APIKey).where(APIKey.id == api_key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key with ID {api_key_id} not found"
        )

    api_key.is_active = False
    await db.commit()

    logger.info(f"Deactivated API key ID: {api_key_id}")

    return None


# ============================================================================
# Analytics Endpoints
# ============================================================================

@app.get(
    "/api/analytics/summary",
    response_model=AnalyticsSummary,
    summary="Get analytics summary",
    description="Get comprehensive analytics summary for a period",
)
async def get_analytics_summary_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get analytics summary for the authenticated client.

    Args:
        days: Number of days to include in the summary (default: 30)
    """
    from datetime import timedelta

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db,
        client_id=client.id,
        start_date=start_date,
        end_date=end_date
    )

    return summary


@app.get(
    "/api/analytics/snapshots",
    response_model=list[AnalyticsSnapshotResponse],
    summary="Get analytics snapshots",
    description="Get quarterly analytics snapshots for a client",
)
async def get_snapshots_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    limit: int = 10,
):
    """
    Get analytics snapshots for the authenticated client.

    Returns the most recent quarterly/monthly snapshots.
    """
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.client_id == client.id)
        .order_by(AnalyticsSnapshot.year.desc(), AnalyticsSnapshot.quarter.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()

    return [AnalyticsSnapshotResponse.model_validate(s) for s in snapshots]


@app.post(
    "/api/analytics/snapshot/create",
    response_model=AnalyticsSnapshotResponse,
    summary="Create analytics snapshot",
    description="Manually create an analytics snapshot for the current quarter",
)
async def create_snapshot_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an analytics snapshot for the authenticated client's current quarter.
    """
    from app.analytics_service import get_current_quarter

    year, quarter = get_current_quarter()
    snapshot = await calculate_analytics_snapshot(
        db=db,
        client_id=client.id,
        year=year,
        quarter=quarter
    )

    return AnalyticsSnapshotResponse.model_validate(snapshot)


# ============================================================================
# Admin Analytics Endpoints
# ============================================================================

@app.get(
    "/api/admin/analytics/summary",
    response_model=AnalyticsSummary,
    summary="Get global analytics summary",
    description="Get analytics summary across all clients (admin only)",
)
async def get_global_analytics_endpoint(
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get global analytics summary across all clients.

    Requires admin authentication via HTTP Basic Auth.
    """
    from datetime import timedelta

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db,
        start_date=start_date,
        end_date=end_date
    )

    return summary


@app.post(
    "/api/admin/analytics/rotate",
    response_model=list[RotationSummary],
    summary="Rotate old quarters",
    description="Manually trigger quarterly data rotation (admin only)",
)
async def rotate_quarters_endpoint(
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    keep_quarters: int = 2,
):
    """
    Manually trigger quarterly data rotation.

    This will archive email logs older than the specified number of quarters
    and create analytics snapshots.

    Requires admin authentication via HTTP Basic Auth.

    Args:
        keep_quarters: Number of recent quarters to keep (default: 2)
    """
    summaries = await rotate_old_quarters(db, keep_quarters)
    return summaries


@app.get(
    "/api/admin/analytics/client/{client_id}",
    response_model=AnalyticsSummary,
    summary="Get client analytics",
    description="Get analytics for a specific client (admin only)",
)
async def get_client_analytics_endpoint(
    client_id: int,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get analytics for a specific client.

    Requires admin authentication via HTTP Basic Auth.
    """
    from datetime import timedelta

    # Verify client exists
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {client_id} not found"
        )

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db,
        client_id=client_id,
        start_date=start_date,
        end_date=end_date
    )

    return summary


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions with consistent error format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail if isinstance(exc.detail, str) else exc.detail.get("error", ""),
            "message": exc.detail if isinstance(exc.detail, str) else exc.detail.get("message", ""),
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
