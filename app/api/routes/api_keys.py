"""API key management endpoints (Admin)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import APIKeyCreate, APIKeyResponse
from app.schemas import Client, APIKey, AdminUser
from app.auth import get_admin_user, create_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin", "api-keys"])


@router.post(
    "/api-keys",
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
            detail=f"Client with ID {api_key_data.client_id} not found",
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


@router.get(
    "/clients/{client_id}/api-keys",
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


@router.delete(
    "/api-keys/{api_key_id}",
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
            detail=f"API key with ID {api_key_id} not found",
        )

    api_key.is_active = False
    await db.commit()

    logger.info(f"Deactivated API key ID: {api_key_id}")

    return None
