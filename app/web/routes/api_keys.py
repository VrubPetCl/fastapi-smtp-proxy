"""API key management routes."""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.schemas import Client, APIKey
from app.config import settings
from app.web.utils import require_admin, serializer

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/{client_id}/keys", response_class=HTMLResponse)
async def client_keys(
    request: Request,
    client_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display client API keys."""
    # Get client
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get API keys
    result = await db.execute(
        select(APIKey)
        .where(APIKey.client_id == client_id)
        .order_by(APIKey.created_at.desc())
    )
    api_keys = result.scalars().all()

    # Check if we just created a new key (passed via session cookie, not query param)
    new_api_key_cookie = request.cookies.get("new_api_key")
    new_api_key = None
    if new_api_key_cookie:
        try:
            # Decrypt the new API key from the session cookie
            new_api_key = serializer.loads(new_api_key_cookie, max_age=60)  # Only valid for 60 seconds
        except Exception:
            # Cookie expired or invalid
            pass

    response = templates.TemplateResponse(
        "client_keys.html",
        {
            "request": request,
            "session": session,
            "client": client,
            "api_keys": api_keys,
            "new_api_key": new_api_key
        }
    )

    # Clear the one-time cookie after displaying it
    if new_api_key_cookie:
        response.delete_cookie("new_api_key")

    return response


@router.get("/{client_id}/keys/new", response_class=HTMLResponse)
async def new_api_key_page(
    request: Request,
    client_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display new API key form."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return templates.TemplateResponse(
        "api_key_form.html",
        {
            "request": request,
            "session": session,
            "client": client,
            "now": datetime.utcnow()
        }
    )


@router.post("/{client_id}/keys/new")
async def create_api_key(
    client_id: int,
    description: Optional[str] = Form(None),
    expires_at: Optional[str] = Form(None),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Generate new API key using JWT tokens."""
    from app.auth import create_api_key as create_jwt_api_key

    # Get client
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Parse expiration date if provided
    expires_at_dt = None
    if expires_at and expires_at.strip():
        try:
            expires_at_dt = datetime.strptime(expires_at, '%Y-%m-%d')
            expires_at_dt = expires_at_dt.replace(hour=23, minute=59, second=59)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid expiration date format. Use YYYY-MM-DD")

    # Generate JWT API key using the existing auth function
    jwt_token, key_hash = create_jwt_api_key(
        client_id=client_id,
        key_name=description or f"API Key {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        expires_at=expires_at_dt
    )

    # Create API key record
    key_record = APIKey(
        client_id=client_id,
        name=description or f"API Key {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        key_hash=key_hash,  # Store SHA256 hash of the JWT
        expires_at=expires_at_dt,
        is_active=True
    )

    db.add(key_record)
    await db.commit()

    logger.info(f"Created JWT API key for client {client.name} (ID: {client_id})")

    # Store the JWT token in a secure, short-lived cookie instead of URL query parameter
    # This prevents the key from being logged in server logs, proxy logs, or browser history
    response = RedirectResponse(
        url=f"/admin/clients/{client_id}/keys",
        status_code=302
    )

    # Set a short-lived, secure cookie with the new JWT API key
    new_key_cookie = serializer.dumps(jwt_token)
    response.set_cookie(
        key="new_api_key",
        value=new_key_cookie,
        httponly=True,  # Prevent JavaScript access
        secure=settings.force_https,  # HTTPS only when enabled
        samesite="strict",  # Strict CSRF protection for sensitive data
        max_age=60  # Only valid for 60 seconds (one-time display)
    )

    return response


@router.post("/{client_id}/keys/{key_id}/revoke")
async def revoke_api_key(
    client_id: int,
    key_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Revoke API key."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.client_id == client_id
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False
    await db.commit()

    return RedirectResponse(url=f"/admin/clients/{client_id}/keys", status_code=302)
