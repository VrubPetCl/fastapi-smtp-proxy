"""Client management routes."""
import logging
import io
import base64
from datetime import datetime
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from pydantic import EmailStr, ValidationError
from app.database import get_db
from app.schemas import Client, APIKey, EmailLog
from app.encryption import get_encryption
from app.web.utils import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/new", response_class=HTMLResponse)
async def new_client_page(
    request: Request,
    session: dict = Depends(require_admin),
):
    """Display new client form."""
    return templates.TemplateResponse(
        "client_form.html",
        {"request": request, "session": session, "client": None}
    )


@router.post("/new")
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


@router.get("/{client_id}", response_class=HTMLResponse)
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


@router.get("/{client_id}/edit", response_class=HTMLResponse)
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


@router.post("/{client_id}/edit")
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


@router.post("/{client_id}/delete")
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


@router.post("/{client_id}/test-email")
async def send_test_email(
    client_id: int,
    test_email: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    session: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send a test email to verify SMTP configuration with optional attachment."""
    import logging
    import aiosmtplib

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
