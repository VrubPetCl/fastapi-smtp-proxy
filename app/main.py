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
from app.schemas import Client, APIKey, EmailLog
from app.auth import get_current_client, create_api_key
from app.smtp_service import send_email

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
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Send an email via SMTP using the authenticated client's configuration.

    This endpoint accepts email data in the format compatible with wp-smtp-api
    and sends it through the client's preconfigured SMTP server.
    """
    try:
        # Send email
        success, message, smtp_response = await send_email(client, email_request)

        # Log the email
        email_log = EmailLog(
            client_id=client.id,
            to_addresses=json.dumps([str(email) for email in email_request.to]),
            subject=email_request.subject,
            from_email=email_request.from_email or client.default_from_email or client.smtp_username,
            status="sent" if success else "failed",
            error_message=None if success else message,
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
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new client with SMTP configuration.

    In production, this should be protected with admin authentication.
    """
    # Check if client name already exists
    result = await db.execute(select(Client).where(Client.name == client_data.name))
    existing_client = result.scalar_one_or_none()

    if existing_client:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client with name '{client_data.name}' already exists"
        )

    # Create new client
    new_client = Client(
        name=client_data.name,
        smtp_host=client_data.smtp_host,
        smtp_port=client_data.smtp_port,
        smtp_username=client_data.smtp_username,
        smtp_password=client_data.smtp_password,  # TODO: Encrypt in production
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
    db: AsyncSession = Depends(get_db),
):
    """
    List all clients.

    In production, this should be protected with admin authentication.
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
    db: AsyncSession = Depends(get_db),
):
    """
    Get client details by ID.

    In production, this should be protected with admin authentication.
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
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new API key for a client.

    In production, this should be protected with admin authentication.
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
    db: AsyncSession = Depends(get_db),
):
    """
    List all API keys for a client.

    In production, this should be protected with admin authentication.
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
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate an API key.

    In production, this should be protected with admin authentication.
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
