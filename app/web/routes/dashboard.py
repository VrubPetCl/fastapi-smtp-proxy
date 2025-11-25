"""Dashboard routes for admin panel."""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from app.database import get_db
from app.schemas import Client, APIKey, EmailLog, LoginAttempt
from app.web.utils import get_session_data, require_admin

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
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


@router.get("/security-logs", response_class=HTMLResponse)
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


@router.get("/clients", response_class=HTMLResponse)
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


@router.get("/analytics", response_class=HTMLResponse)
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


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_root(request: Request):
    """Redirect /admin to /admin/dashboard or /admin/login."""
    session = get_session_data(request)
    if session.get("admin_id"):
        return RedirectResponse(url="/admin/dashboard", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)
