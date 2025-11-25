"""Authentication routes for admin dashboard."""
import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.schemas import AdminUser, LoginAttempt
from app.web_auth import authenticate_admin, create_password_reset_token, reset_password, verify_reset_token
from app.config import settings
from app.turnstile import verify_turnstile_token
from app.ip_utils import get_client_ip
from app.web.utils import get_session_data, create_session_cookie, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
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


@router.post("/login")
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
        client_ip = get_client_ip(request)
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
    client_ip = get_client_ip(request)
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
        samesite="lax",  # CSRF protection
        max_age=7200    # 2 hours (reduced from 7 days)
    )

    return response


@router.get("/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("session")
    return response


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Display forgot password page."""
    session = get_session_data(request)
    return templates.TemplateResponse("forgot_password.html", {"request": request, "session": session})


@router.post("/forgot-password")
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


@router.get("/reset-password/{token}", response_class=HTMLResponse)
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


@router.post("/reset-password/{token}")
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


@router.get("/debug/turnstile", response_class=HTMLResponse)
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
