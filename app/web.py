"""Web routes for admin dashboard."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from itsdangerous import URLSafeTimedSerializer
from app.database import get_db
from app.schemas import AdminUser, Client, APIKey, EmailLog
from app.web_auth import authenticate_admin, create_password_reset_token, reset_password, verify_reset_token
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Session serializer for secure cookies
serializer = URLSafeTimedSerializer(settings.jwt_secret_key)


def get_session_data(request: Request) -> dict:
    """Extract session data from request."""
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return {}

    try:
        return serializer.loads(session_cookie, max_age=86400 * 7)  # 7 days
    except:
        return {}


def create_session_cookie(data: dict) -> str:
    """Create a signed session cookie."""
    return serializer.dumps(data)


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
    admin = await authenticate_admin(db, username, password)

    if not admin:
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
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=86400 * 7  # 7 days
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
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Display analytics page."""
    # For now, redirect to dashboard
    # In a full implementation, this would show detailed analytics
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@router.get("/admin", response_class=HTMLResponse)
async def admin_root(request: Request):
    """Redirect /admin to /admin/dashboard or /admin/login."""
    session = get_session_data(request)
    if session.get("admin_id"):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)
