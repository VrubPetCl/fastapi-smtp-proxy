"""Web routes for admin dashboard."""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from collections import defaultdict
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException, status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from itsdangerous import URLSafeTimedSerializer
from app.database import get_db
from app.schemas import AdminUser, Client, APIKey, EmailLog, LoginAttempt
from app.web_auth import authenticate_admin, create_password_reset_token, reset_password, verify_reset_token
from app.config import settings
from app.encryption import get_encryption
from app.turnstile import verify_turnstile_token

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

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "session": session,
            "turnstile_enabled": settings.turnstile_enabled,
            "turnstile_site_key": settings.cf_turnstile_site_key
        }
    )


@router.post("/admin/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    cf_turnstile_response: Optional[str] = Form(None, alias="cf-turnstile-response")
):
    """Process login form."""
    # Cloudflare Turnstile verification (if enabled)
    if settings.turnstile_enabled:
        if not cf_turnstile_response:
            logger.warning(f"Missing Turnstile token for login attempt: {username}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": {},
                    "turnstile_enabled": settings.turnstile_enabled,
                    "turnstile_site_key": settings.cf_turnstile_site_key,
                    "error": "Captcha verification is required. Please complete the captcha."
                },
                status_code=400
            )

        # Verify Turnstile token
        client_ip = request.client.host if request.client else None
        turnstile_valid = await verify_turnstile_token(cf_turnstile_response, client_ip)

        if not turnstile_valid:
            logger.warning(f"Invalid Turnstile token for login attempt: {username} from {client_ip}")
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "session": {},
                    "turnstile_enabled": settings.turnstile_enabled,
                    "turnstile_site_key": settings.cf_turnstile_site_key,
                    "error": "Captcha verification failed. Please try again."
                },
                status_code=400
            )

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
                "turnstile_enabled": settings.turnstile_enabled,
                "turnstile_site_key": settings.cf_turnstile_site_key,
                "error": "Too many login attempts. Please try again in 15 minutes."
            },
            status_code=429
        )

    # Capture user agent for security tracking
    user_agent = request.headers.get("user-agent", "unknown")

    admin = await authenticate_admin(db, username, password)

    if not admin:
        # Log failed login attempt
        login_attempt = LoginAttempt(
            username=username,
            ip_address=client_ip,
            user_agent=user_agent,
            success=False,
            failure_reason="invalid_credentials"
        )
        db.add(login_attempt)
        await db.commit()

        logger.warning(f"Failed login attempt for: {username} from {client_ip}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "session": {},
                "turnstile_enabled": settings.turnstile_enabled,
                "turnstile_site_key": settings.cf_turnstile_site_key,
                "error": "Invalid username or password"
            },
            status_code=400
        )

    # Log successful login attempt
    login_attempt = LoginAttempt(
        username=username,
        ip_address=client_ip,
        user_agent=user_agent,
        success=True,
        failure_reason=None
    )
    db.add(login_attempt)
    await db.commit()

    logger.info(f"Successful login for: {username} from {client_ip}")

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
        secure=settings.force_https,  # HTTPS only when force_https is enabled (MITM protection)
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
        logger.info(f"Password reset requested for {admin.email}")

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


@router.get("/admin/security-logs", response_class=HTMLResponse)
async def security_logs(
    request: Request,
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    days: int = 7
):
    """Display security logs and suspicious activity."""
    # Get recent login attempts (last N days)
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get login attempts
    result = await db.execute(
        select(LoginAttempt)
        .where(LoginAttempt.attempted_at >= cutoff_date)
        .order_by(LoginAttempt.attempted_at.desc())
        .limit(100)
    )
    login_attempts = result.scalars().all()

    # Get suspicious IPs (multiple failed login attempts)
    result = await db.execute(
        select(
            LoginAttempt.ip_address,
            LoginAttempt.country_code,
            func.count(LoginAttempt.id).label('total_attempts'),
            func.sum(case((LoginAttempt.success == False, 1), else_=0)).label('failed_attempts'),
            func.max(LoginAttempt.attempted_at).label('last_attempt')
        )
        .where(LoginAttempt.attempted_at >= cutoff_date)
        .group_by(LoginAttempt.ip_address, LoginAttempt.country_code)
        .having(func.sum(case((LoginAttempt.success == False, 1), else_=0)) >= 2)
        .order_by(func.sum(case((LoginAttempt.success == False, 1), else_=0)).desc())
    )
    suspicious_ips = result.all()

    # Get recent email sending IPs
    result = await db.execute(
        select(
            EmailLog.source_ip,
            EmailLog.country_code,
            func.count(EmailLog.id).label('email_count'),
            func.max(EmailLog.sent_at).label('last_sent'),
            Client.name.label('client_name')
        )
        .join(Client, EmailLog.client_id == Client.id)
        .where(EmailLog.sent_at >= cutoff_date, EmailLog.source_ip.isnot(None))
        .group_by(EmailLog.source_ip, EmailLog.country_code, Client.name)
        .order_by(func.max(EmailLog.sent_at).desc())
        .limit(50)
    )
    email_ips = result.all()

    # Get summary statistics
    total_login_attempts = len(login_attempts)
    failed_logins = sum(1 for attempt in login_attempts if not attempt.success)
    unique_ips_login = len(set(attempt.ip_address for attempt in login_attempts))
    suspicious_ip_count = len(suspicious_ips)

    stats = {
        "total_login_attempts": total_login_attempts,
        "failed_logins": failed_logins,
        "success_rate": ((total_login_attempts - failed_logins) / total_login_attempts * 100) if total_login_attempts > 0 else 0,
        "unique_ips_login": unique_ips_login,
        "suspicious_ip_count": suspicious_ip_count,
        "days": days
    }

    return templates.TemplateResponse(
        "security_logs.html",
        {
            "request": request,
            "session": session,
            "stats": stats,
            "login_attempts": login_attempts,
            "suspicious_ips": suspicious_ips,
            "email_ips": email_ips
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
    default_from_email: Optional[str] = Form(None),
    default_from_name: Optional[str] = Form(None),
    smtp_use_tls: bool = Form(False),
    smtp_use_ssl: bool = Form(False),
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
        default_from_email=default_from_email,
        default_from_name=default_from_name,
        smtp_use_tls=smtp_use_tls,
        smtp_use_ssl=smtp_use_ssl,
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
    default_from_email: Optional[str] = Form(None),
    default_from_name: Optional[str] = Form(None),
    smtp_use_tls: bool = Form(False),
    smtp_use_ssl: bool = Form(False),
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
    client.default_from_email = default_from_email
    client.default_from_name = default_from_name
    client.smtp_use_tls = smtp_use_tls
    client.smtp_use_ssl = smtp_use_ssl
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


@router.post("/admin/clients/{client_id}/test-email")
async def send_test_email(
    client_id: int,
    test_email: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send a test email to verify SMTP configuration with optional attachment."""
    import logging
    import io
    import base64
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    from pydantic import EmailStr, ValidationError

    # Collect logs
    logs = []
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    # Create a logger for this test
    test_logger = logging.getLogger(f'test_email_{client_id}')
    test_logger.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)

    try:
        # Validate email format using Pydantic (prevents SQL injection and validates format)
        try:
            validated_email = EmailStr._validate(test_email)
            test_logger.info(f"Email validation passed: {validated_email}")
        except (ValidationError, ValueError) as e:
            test_logger.error(f"Invalid email format: {test_email}")
            return JSONResponse(
                content={
                    "success": False,
                    "error": "Invalid email address format",
                    "logs": ["ERROR - Invalid email format provided"]
                },
                status_code=400
            )

        # Get client
        test_logger.info(f"Fetching client {client_id} from database")
        result = await db.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()

        if not client:
            test_logger.error(f"Client {client_id} not found")
            return JSONResponse(
                content={
                    "success": False,
                    "error": "Client not found",
                    "logs": log_stream.getvalue().split('\n')
                },
                status_code=404
            )

        test_logger.info(f"Client found: {client.name}")

        # Check if client is active
        if not client.is_active:
            test_logger.warning(f"Client {client.name} is inactive")
            return JSONResponse(
                content={
                    "success": False,
                    "error": "Client is inactive. Activate the client before testing.",
                    "logs": log_stream.getvalue().split('\n')
                },
                status_code=400
            )

        # Decrypt SMTP password
        test_logger.info("Decrypting SMTP password")
        encryption = get_encryption()
        try:
            smtp_password = encryption.decrypt(client.smtp_password)
            test_logger.info("SMTP password decrypted successfully")
        except Exception as e:
            test_logger.error(f"Failed to decrypt SMTP password: {str(e)}")
            return JSONResponse(
                content={
                    "success": False,
                    "error": "Failed to decrypt SMTP password. Check encryption configuration.",
                    "logs": log_stream.getvalue().split('\n')
                },
                status_code=500
            )

        # Prepare test email
        test_logger.info("Preparing test email message")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Test Email from {client.name} - SMTP Proxy"
        msg['From'] = client.default_from_email or client.smtp_username
        msg['To'] = validated_email

        html_content = f"""
        <html>
            <head></head>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #2563eb;">✅ SMTP Configuration Test</h2>
                <p>This is a test email sent from your SMTP Proxy configuration.</p>

                <div style="background-color: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #374151;">Configuration Details:</h3>
                    <ul style="color: #6b7280;">
                        <li><strong>Client:</strong> {client.name}</li>
                        <li><strong>SMTP Host:</strong> {client.smtp_host}:{client.smtp_port}</li>
                        <li><strong>SMTP Username:</strong> {client.smtp_username}</li>
                        <li><strong>TLS:</strong> {'Enabled' if client.smtp_use_tls else 'Disabled'}</li>
                        <li><strong>SSL:</strong> {'Enabled' if client.smtp_use_ssl else 'Disabled'}</li>
                    </ul>
                </div>

                <p style="color: #6b7280; font-size: 14px;">
                    If you received this email, your SMTP configuration is working correctly!
                </p>

                <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
                <p style="color: #9ca3af; font-size: 12px;">
                    Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}<br>
                    From: FastAPI SMTP Proxy
                </p>
            </body>
        </html>
        """

        text_content = f"""
SMTP Configuration Test

This is a test email sent from your SMTP Proxy configuration.

Configuration Details:
- Client: {client.name}
- SMTP Host: {client.smtp_host}:{client.smtp_port}
- SMTP Username: {client.smtp_username}
- TLS: {'Enabled' if client.smtp_use_tls else 'Disabled'}
- SSL: {'Enabled' if client.smtp_use_ssl else 'Disabled'}

If you received this email, your SMTP configuration is working correctly!

Sent at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
From: FastAPI SMTP Proxy
        """

        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        msg.attach(part1)
        msg.attach(part2)

        # Add attachment if provided
        if attachment and attachment.filename:
            test_logger.info(f"Processing attachment: {attachment.filename}")

            try:
                # Read file content
                file_content = await attachment.read()
                file_size_mb = len(file_content) / 1024 / 1024

                # Check size limit (25MB)
                if len(file_content) > 25 * 1024 * 1024:
                    test_logger.error(f"Attachment too large: {file_size_mb:.2f}MB (max 25MB)")
                    return JSONResponse(
                        content={
                            "success": False,
                            "error": f"Attachment too large: {file_size_mb:.2f}MB. Maximum size is 25MB.",
                            "logs": log_stream.getvalue().split('\n')
                        },
                        status_code=400
                    )

                test_logger.info(f"Attachment size: {file_size_mb:.2f}MB")

                # Create attachment part
                content_type = attachment.content_type or 'application/octet-stream'
                main_type, sub_type = content_type.split('/', 1) if '/' in content_type else ('application', 'octet-stream')

                part = MIMEBase(main_type, sub_type)
                part.set_payload(file_content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment.filename}"'
                )

                msg.attach(part)
                test_logger.info(f"Attachment added successfully: {attachment.filename}")

            except Exception as e:
                test_logger.error(f"Failed to process attachment: {str(e)}")
                return JSONResponse(
                    content={
                        "success": False,
                        "error": f"Failed to process attachment: {str(e)}",
                        "logs": log_stream.getvalue().split('\n')
                    },
                    status_code=400
                )

        # Send email using SMTP
        test_logger.info(f"Connecting to SMTP server: {client.smtp_host}:{client.smtp_port}")

        import aiosmtplib

        smtp_params = {
            'hostname': client.smtp_host,
            'port': client.smtp_port,
            'username': client.smtp_username,
            'password': smtp_password,
            'use_tls': client.smtp_use_ssl,  # SSL on connect
            'start_tls': client.smtp_use_tls,  # STARTTLS after connect
        }

        try:
            test_logger.info(f"Initiating SMTP connection (TLS: {client.smtp_use_tls}, SSL: {client.smtp_use_ssl})")

            async with aiosmtplib.SMTP(**smtp_params) as smtp:
                test_logger.info("SMTP connection established")
                test_logger.info(f"Sending email to {validated_email}")

                response = await smtp.send_message(msg)
                test_logger.info(f"Email sent successfully! Server response: {response}")

                logs_output = log_stream.getvalue().split('\n')
                logs_output = [log for log in logs_output if log.strip()]  # Remove empty lines

                return JSONResponse(
                    content={
                        "success": True,
                        "message": f"Test email sent successfully to {validated_email}",
                        "logs": logs_output
                    }
                )

        except aiosmtplib.SMTPAuthenticationError as e:
            test_logger.error(f"SMTP Authentication failed: {str(e)}")
            logs_output = log_stream.getvalue().split('\n')
            logs_output = [log for log in logs_output if log.strip()]

            return JSONResponse(
                content={
                    "success": False,
                    "error": "SMTP Authentication failed. Check username and password.",
                    "logs": logs_output
                },
                status_code=500
            )

        except aiosmtplib.SMTPException as e:
            test_logger.error(f"SMTP Error: {str(e)}")
            logs_output = log_stream.getvalue().split('\n')
            logs_output = [log for log in logs_output if log.strip()]

            return JSONResponse(
                content={
                    "success": False,
                    "error": f"SMTP Error: {str(e)}",
                    "logs": logs_output
                },
                status_code=500
            )

        except Exception as e:
            test_logger.error(f"Unexpected error: {str(e)}")
            logs_output = log_stream.getvalue().split('\n')
            logs_output = [log for log in logs_output if log.strip()]

            return JSONResponse(
                content={
                    "success": False,
                    "error": f"Failed to send email: {str(e)}",
                    "logs": logs_output
                },
                status_code=500
            )

    except Exception as e:
        test_logger.error(f"Fatal error: {str(e)}")
        logs_output = log_stream.getvalue().split('\n')
        logs_output = [log for log in logs_output if log.strip()]

        return JSONResponse(
            content={
                "success": False,
                "error": f"Internal error: {str(e)}",
                "logs": logs_output
            },
            status_code=500
        )
    finally:
        # Clean up logger
        test_logger.removeHandler(handler)
        handler.close()


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
        name=description,  # Use 'name' field instead of 'description'
        key_hash=api_key,  # In production, hash this
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


@router.get("/admin/debug/turnstile", response_class=HTMLResponse)
async def debug_turnstile(request: Request):
    """Debug endpoint to verify Turnstile configuration."""
    from fastapi.responses import HTMLResponse

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Turnstile Debug</title>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
    </head>
    <body style="font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px;">
        <h1>Cloudflare Turnstile Debug Page</h1>

        <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h2>Configuration Status:</h2>
            <ul>
                <li><strong>Turnstile Enabled:</strong> {settings.turnstile_enabled}</li>
                <li><strong>Site Key:</strong> {settings.cf_turnstile_site_key or '(not set)'}</li>
                <li><strong>Secret Key:</strong> {'(set)' if settings.cf_turnstile_secret_key else '(not set)'}</li>
            </ul>
        </div>

        <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h2>Turnstile Widget Test:</h2>
            <p>The widget should appear below:</p>
            <div class="cf-turnstile"
                 data-sitekey="{settings.cf_turnstile_site_key or 'NO-KEY-SET'}"
                 data-theme="light"
                 data-callback="onSuccess"></div>
        </div>

        <div style="background: #fff3cd; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h2>Debug Info:</h2>
            <div id="debug">Waiting for widget...</div>
        </div>

        <script>
            function onSuccess(token) {{
                document.getElementById('debug').innerHTML =
                    '<span style="color: green;">✓ Widget loaded successfully!</span><br>' +
                    '<strong>Token received:</strong> ' + token.substring(0, 50) + '...';
            }}

            // Check if script loaded
            setTimeout(function() {{
                const widget = document.querySelector('.cf-turnstile');
                const iframe = widget.querySelector('iframe');

                if (iframe) {{
                    document.getElementById('debug').innerHTML +=
                        '<br><span style="color: green;">✓ Turnstile SDK loaded</span>' +
                        '<br><span style="color: green;">✓ Widget iframe rendered</span>';
                }} else {{
                    document.getElementById('debug').innerHTML =
                        '<span style="color: red;">✗ Widget did not render</span>' +
                        '<br><strong>Possible issues:</strong>' +
                        '<ul>' +
                        '<li>Invalid site key</li>' +
                        '<li>Site key domain mismatch</li>' +
                        '<li>JavaScript error (check console)</li>' +
                        '</ul>';
                }}
            }}, 3000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)
