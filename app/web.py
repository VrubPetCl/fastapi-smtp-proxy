"""Web routes for admin dashboard."""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from collections import defaultdict
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from itsdangerous import URLSafeTimedSerializer
from app.database import get_db
from app.schemas import AdminUser, Client, APIKey, EmailLog
from app.web_auth import authenticate_admin, create_password_reset_token, reset_password, verify_reset_token
from app.config import settings
from app.encryption import get_encryption

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Session serializer for secure cookies
serializer = URLSafeTimedSerializer(settings.jwt_secret_key)

# Rate limiting for login attempts
login_attempts: Dict[str, list] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_PERIOD = 900  # 15 minutes in seconds


def get_session_data(request: Request) -> dict:
    """Extract session data from request."""
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return {}

    try:
        return serializer.loads(session_cookie, max_age=7200)  # 2 hours
    except (Exception,):  # Fixed: specific exception handling
        return {}


def create_session_cookie(data: dict) -> str:
    """Create a signed session cookie."""
    return serializer.dumps(data)


def check_rate_limit(identifier: str) -> bool:
    """
    Check if the identifier (IP/username) has exceeded rate limit.

    Returns True if request is allowed, False if rate limited.
    """
    now = datetime.utcnow()
    cutoff_time = now - timedelta(seconds=LOCKOUT_PERIOD)

    # Remove old attempts
    login_attempts[identifier] = [
        attempt_time for attempt_time in login_attempts[identifier]
        if attempt_time > cutoff_time
    ]

    # Check if rate limited
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        return False

    # Record this attempt
    login_attempts[identifier].append(now)
    return True


def require_admin(request: Request):
    """Dependency to require admin authentication."""
    session = get_session_data(request)
    if not session.get("admin_id"):
        raise HTTPException(
            status_code=http_status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"}
        )
    return session


# ============================================================================
# Authentication Routes
# ============================================================================

@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Display login page."""
    session = get_session_data(request)
    if session.get("admin_id"):
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "session": session})


@router.post("/admin/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Process login form."""
    # Rate limiting check
    client_ip = request.client.host if request.client else "unknown"
    rate_limit_key = f"{client_ip}:{username}"

    if not check_rate_limit(rate_limit_key):
        logger.warning(f"Rate limit exceeded for login attempt: {username} from {client_ip}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": {},
                "error": "Too many login attempts. Please try again in 15 minutes."
            },
            status_code=429
        )

    admin = await authenticate_admin(db, username, password)

    if not admin:
        logger.warning(f"Failed login attempt for: {username} from {client_ip}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": {},
                "error": "Invalid username or password"
            },
            status_code=400
        )

    # Create session
    session_data = {
        "admin_id": admin.id,
        "username": admin.username,
        "is_superuser": admin.is_superuser
    }
    session_cookie = create_session_cookie(session_data)

    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key="session",
        value=session_cookie,
        httponly=True,  # Prevent JavaScript access (XSS protection)
        secure=True,    # HTTPS only (MITM protection)
        samesite="lax", # CSRF protection
        max_age=7200    # 2 hours (reduced from 7 days)
    )

    return response


@router.get("/admin/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("session")
    return response


@router.get("/admin/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Display forgot password page."""
    session = get_session_data(request)
    return templates.TemplateResponse("forgot_password.html", {"request": request, "session": session})


@router.post("/admin/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Process forgot password form."""
    # Find admin by email
    result = await db.execute(select(AdminUser).where(AdminUser.email == email))
    admin = result.scalar_one_or_none()

    if admin:
        # Create reset token
        token = await create_password_reset_token(db, admin.id)
        # In production, send email with reset link
        logger.info(f"Password reset requested for {admin.email}. Token: {token}")

    # Always show success message (don't reveal if email exists)
    return templates.TemplateResponse(
        "forgot_password.html",
        {
            "request": request,
            "session": {},
            "success": "If that email exists, a password reset link has been sent."
        }
    )


@router.get("/admin/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """Display reset password page."""
    # Verify token is valid
    admin = await verify_reset_token(db, token)

    if not admin:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": {},
                "error": "Invalid or expired reset token"
            }
        )

    session = get_session_data(request)
    return templates.TemplateResponse(
        "reset_password.html",
        {"request": request, "session": session, "token": token}
    )


@router.post("/admin/reset-password/{token}")
async def reset_password_submit(
    request: Request,
    token: str,
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Process reset password form."""
    if password != confirm_password:
        return templates.TemplateResponse(
            "reset_password.html",
            {
                "request": request,
                "session": {},
                "token": token,
                "error": "Passwords do not match"
            },
            status_code=400
        )

    success = await reset_password(db, token, password)

    if not success:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": {},
                "error": "Invalid or expired reset token"
            }
        )

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "session": {},
            "success": "Password reset successfully. Please login."
        }
    )


# ============================================================================
# Dashboard Routes
# ============================================================================

@router.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display admin dashboard."""
    # Get statistics
    total_clients = await db.scalar(select(func.count()).select_from(Client))
    active_api_keys = await db.scalar(
        select(func.count()).select_from(APIKey).where(APIKey.is_active == True)
    )

    # Get emails from last 30 days
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    result = await db.execute(
        select(
            func.count(EmailLog.id).label('total'),
            func.sum(
                case((EmailLog.status == 'sent', 1), else_=0)
            ).label('sent')
        ).where(EmailLog.sent_at >= thirty_days_ago)
    )
    email_stats = result.first()

    total_emails = email_stats.total if email_stats.total else 0
    emails_sent = email_stats.sent if email_stats.sent else 0
    success_rate = (emails_sent / total_emails * 100) if total_emails > 0 else 0

    # Get recent emails
    result = await db.execute(
        select(EmailLog, Client)
        .join(Client)
        .order_by(EmailLog.sent_at.desc())
        .limit(10)
    )
    recent_emails_raw = result.all()

    recent_emails = [
        {
            "subject": email.subject,
            "status": email.status,
            "sent_at": email.sent_at,
            "client_name": client.name
        }
        for email, client in recent_emails_raw
    ]

    stats = {
        "total_clients": total_clients,
        "active_api_keys": active_api_keys,
        "total_emails": total_emails,
        "success_rate": success_rate
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "session": session,
            "stats": stats,
            "recent_emails": recent_emails
        }
    )


@router.get("/admin/clients", response_class=HTMLResponse)
async def clients_list(
    request: Request,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display clients list."""
    # Get all clients with API key count
    result = await db.execute(
        select(
            Client,
            func.count(APIKey.id).label('api_key_count')
        )
        .outerjoin(APIKey)
        .group_by(Client.id)
        .order_by(Client.created_at.desc())
    )

    clients_data = result.all()

    clients = [
        {
            "id": client.id,
            "name": client.name,
            "smtp_host": client.smtp_host,
            "smtp_port": client.smtp_port,
            "smtp_username": client.smtp_username,
            "is_active": client.is_active,
            "created_at": client.created_at,
            "api_key_count": api_key_count
        }
        for client, api_key_count in clients_data
    ]

    return templates.TemplateResponse(
        "clients.html",
        {
            "request": request,
            "session": session,
            "clients": clients
        }
    )


@router.get("/admin/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    client_id: Optional[int] = None,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display analytics page with detailed metrics."""
    from app.analytics_service import get_analytics_summary
    from datetime import datetime, timedelta

    # Parse dates or use defaults (last 30 days)
    end_date_obj = datetime.utcnow()
    start_date_obj = end_date_obj - timedelta(days=30)

    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
            end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        except ValueError:
            pass

    # Get all clients for filter dropdown
    result = await db.execute(select(Client).order_by(Client.name))
    clients = result.scalars().all()

    # Get analytics summary
    analytics = await get_analytics_summary(
        db=db,
        client_id=client_id,
        start_date=start_date_obj,
        end_date=end_date_obj
    )

    return templates.TemplateResponse(
        "analytics.html",
        {
            "request": request,
            "session": session,
            "analytics": analytics,
            "clients": clients,
            "client_id": client_id,
            "start_date": start_date or start_date_obj.strftime('%Y-%m-%d'),
            "end_date": end_date or end_date_obj.strftime('%Y-%m-%d'),
            "start_date_obj": start_date_obj,
            "end_date_obj": end_date_obj,
        }
    )


# ============================================================================
# Client Management Routes
# ============================================================================

@router.get("/admin/clients/new", response_class=HTMLResponse)
async def new_client_page(
    request: Request,
    session: dict = Depends(require_admin),
):
    """Display new client form."""
    return templates.TemplateResponse(
        "client_form.html",
        {"request": request, "session": session, "client": None}
    )


@router.post("/admin/clients/new")
async def create_client(
    request: Request,
    name: str = Form(...),
    smtp_host: str = Form(...),
    smtp_port: int = Form(...),
    smtp_username: str = Form(...),
    smtp_password: str = Form(...),
    from_email: str = Form(...),
    from_name: Optional[str] = Form(None),
    use_tls: bool = Form(False),
    is_active: bool = Form(False),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new client."""
    # Encrypt SMTP password before storing
    encryption = get_encryption()
    encrypted_password = encryption.encrypt(smtp_password)

    # Create new client
    client = Client(
        name=name,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=encrypted_password,  # Encrypted
        from_email=from_email,
        from_name=from_name,
        use_tls=use_tls,
        is_active=is_active
    )

    db.add(client)
    await db.commit()
    await db.refresh(client)

    return RedirectResponse(url=f"/admin/clients/{client.id}", status_code=302)


@router.get("/admin/clients/{client_id}", response_class=HTMLResponse)
async def client_detail(
    request: Request,
    client_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display client details."""
    # Get client
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get statistics
    api_key_count = await db.scalar(
        select(func.count()).select_from(APIKey).where(APIKey.client_id == client_id)
    )

    result = await db.execute(
        select(
            func.count(EmailLog.id).label('total'),
            func.sum(case((EmailLog.status == 'sent', 1), else_=0)).label('sent'),
            func.sum(case((EmailLog.status == 'failed', 1), else_=0)).label('failed')
        ).where(EmailLog.client_id == client_id)
    )
    email_stats = result.first()

    total_emails = email_stats.total if email_stats.total else 0
    emails_sent = email_stats.sent if email_stats.sent else 0
    emails_failed = email_stats.failed if email_stats.failed else 0
    success_rate = (emails_sent / total_emails * 100) if total_emails > 0 else 0

    # Get recent emails
    result = await db.execute(
        select(EmailLog)
        .where(EmailLog.client_id == client_id)
        .order_by(EmailLog.sent_at.desc())
        .limit(10)
    )
    recent_emails = result.scalars().all()

    stats = {
        "api_key_count": api_key_count,
        "total_emails": total_emails,
        "emails_sent": emails_sent,
        "emails_failed": emails_failed,
        "success_rate": success_rate
    }

    return templates.TemplateResponse(
        "client_detail.html",
        {
            "request": request,
            "session": session,
            "client": client,
            "stats": stats,
            "recent_emails": recent_emails
        }
    )


@router.get("/admin/clients/{client_id}/edit", response_class=HTMLResponse)
async def edit_client_page(
    request: Request,
    client_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display edit client form."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return templates.TemplateResponse(
        "client_form.html",
        {"request": request, "session": session, "client": client}
    )


@router.post("/admin/clients/{client_id}/edit")
async def update_client(
    request: Request,
    client_id: int,
    name: str = Form(...),
    smtp_host: str = Form(...),
    smtp_port: int = Form(...),
    smtp_username: str = Form(...),
    smtp_password: Optional[str] = Form(None),
    from_email: str = Form(...),
    from_name: Optional[str] = Form(None),
    use_tls: bool = Form(False),
    is_active: bool = Form(False),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update client."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Update fields
    client.name = name
    client.smtp_host = smtp_host
    client.smtp_port = smtp_port
    client.smtp_username = smtp_username
    client.from_email = from_email
    client.from_name = from_name
    client.use_tls = use_tls
    client.is_active = is_active

    # Only update password if provided
    if smtp_password and smtp_password.strip():
        encryption = get_encryption()
        client.smtp_password = encryption.encrypt(smtp_password)  # Encrypted

    await db.commit()

    return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=302)


@router.post("/admin/clients/{client_id}/delete")
async def delete_client(
    client_id: int,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete client."""
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    await db.delete(client)
    await db.commit()

    return RedirectResponse(url="/admin/clients", status_code=302)


# ============================================================================
# API Key Management Routes
# ============================================================================

@router.get("/admin/clients/{client_id}/keys", response_class=HTMLResponse)
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

    # Check if we just created a new key (passed via query param)
    new_api_key = request.query_params.get("new_key")

    return templates.TemplateResponse(
        "client_keys.html",
        {
            "request": request,
            "session": session,
            "client": client,
            "api_keys": api_keys,
            "new_api_key": new_api_key
        }
    )


@router.get("/admin/clients/{client_id}/keys/new", response_class=HTMLResponse)
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
        {"request": request, "session": session, "client": client}
    )


@router.post("/admin/clients/{client_id}/keys/new")
async def create_api_key(
    client_id: int,
    description: Optional[str] = Form(None),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Generate new API key."""
    import secrets

    # Get client
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Generate API key
    api_key = f"smtp_{secrets.token_urlsafe(32)}"

    # Create API key record
    key_record = APIKey(
        client_id=client_id,
        key_hash=api_key,  # In production, hash this
        key_prefix=api_key[:12],
        key_suffix=api_key[-4:],
        description=description,
        is_active=True
    )

    db.add(key_record)
    await db.commit()

    # Redirect back to keys page with the new key in the URL
    return RedirectResponse(
        url=f"/admin/clients/{client_id}/keys?new_key={api_key}",
        status_code=302
    )


@router.post("/admin/clients/{client_id}/keys/{key_id}/revoke")
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


@router.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request):
    """Redirect /admin to /admin/dashboard or /admin/login."""
    session = get_session_data(request)
    if session.get("admin_id"):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)
