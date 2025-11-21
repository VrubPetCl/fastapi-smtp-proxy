"""Authentication and authorization utilities."""
import jwt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.schemas import Client, APIKey
from app.database import get_db
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def create_api_key(client_id: int, key_name: str, expires_at: Optional[datetime] = None) -> tuple[str, str]:
    """
    Create a new JWT API key for a client.

    Args:
        client_id: The client ID
        key_name: Name/description of the API key
        expires_at: Optional expiration datetime

    Returns:
        tuple: (jwt_token, key_hash)
    """
    # Set expiration
    if expires_at is None:
        expires_at = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)

    # Create JWT payload
    payload = {
        "client_id": client_id,
        "key_name": key_name,
        "exp": expires_at,
        "iat": datetime.utcnow(),
    }

    # Generate JWT token
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    # Create hash of the token for storage
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    return token, key_hash


def verify_jwt_token(token: str) -> dict:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string

    Returns:
        dict: Decoded token payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


async def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Client:
    """
    Dependency to get the current authenticated client.

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        Client: The authenticated client

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    # Verify JWT token
    payload = verify_jwt_token(token)

    client_id = payload.get("client_id")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing client_id"
        )

    # Create hash of the token
    key_hash = hashlib.sha256(token.encode()).hexdigest()

    # Verify API key exists and is active
    result = await db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .where(APIKey.client_id == client_id)
        .where(APIKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key"
        )

    # Check if API key has expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired"
        )

    # Get client
    result = await db.execute(
        select(Client)
        .where(Client.id == client_id)
        .where(Client.is_active == True)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client not found or inactive"
        )

    # Update last_used_at timestamp
    api_key.last_used_at = datetime.utcnow()
    await db.commit()

    logger.info(f"Client authenticated: {client.name} (ID: {client.id})")

    return client
