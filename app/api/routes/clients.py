"""Client management endpoints (Admin)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import ClientCreate, ClientResponse
from app.schemas import Client, AdminUser
from app.auth import get_admin_user
from app.encryption import get_encryption

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/clients", tags=["admin", "clients"])


@router.post(
    "",
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
            detail=f"Client with name '{client_data.name}' already exists",
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


@router.get(
    "",
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
        select(Client).order_by(Client.created_at.desc()).offset(skip).limit(limit)
    )
    clients = result.scalars().all()

    return [ClientResponse.model_validate(client) for client in clients]


@router.get(
    "/{client_id}",
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
            detail=f"Client with ID {client_id} not found",
        )

    return ClientResponse.model_validate(client)
