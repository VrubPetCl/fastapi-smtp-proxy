"""Email sending endpoints."""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import EmailRequest, EmailResponse, ErrorResponse
from app.schemas import EmailLog
from app.auth import get_current_client_and_key
from app.smtp_service import send_email
from app.analytics_service import get_quarter
from app.ip_utils import get_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["email"])


@router.post(
    "/send",
    response_model=EmailResponse,
    responses={
        200: {"model": EmailResponse},
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Send email via SMTP",
    description="Send an email using the authenticated client's SMTP configuration",
)
async def send_email_endpoint(
    request: Request,
    email_request: EmailRequest,
    client_and_key: tuple = Depends(get_current_client_and_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Send an email via SMTP using the authenticated client's configuration.

    This endpoint accepts email data in the format compatible with wp-smtp-api
    and sends it through the client's preconfigured SMTP server.
    """
    client, api_key_id = client_and_key

    print("\n ---------------------")
    json.dumps(email_request.model_dump(), indent="\t")
    print("---------------------")

    # Capture security tracking info
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "unknown")

    try:
        # Send email and get metrics
        success, message, smtp_response, metrics = await send_email(
            client, email_request
        )

        # Calculate temporal fields for analytics
        sent_at = datetime.utcnow()
        year = sent_at.year
        quarter = get_quarter(sent_at)
        month = sent_at.month
        day_of_week = sent_at.weekday()  # 0 = Monday
        hour = sent_at.hour

        # Calculate attachment metrics
        attachment_count = (
            len(email_request.attachments) if email_request.attachments else 0
        )
        total_attachment_size = 0
        if email_request.attachments:
            for attachment in email_request.attachments:
                # Estimate size from base64 content (approximate)
                content = attachment.get("content", "")
                # Base64 encoding increases size by ~33%, so decode size is len * 0.75
                total_attachment_size += int(len(content) * 0.75)

        # Log the email with full analytics
        email_log = EmailLog(
            client_id=client.id,
            api_key_id=api_key_id,
            to_addresses=json.dumps([str(email) for email in email_request.to]),
            to_count=len(email_request.to),
            cc_count=len(email_request.cc) if email_request.cc else 0,
            bcc_count=len(email_request.bcc) if email_request.bcc else 0,
            subject=email_request.subject,
            from_email=email_request.from_email
            or client.default_from_email
            or client.smtp_username,
            content_type=email_request.content_type,
            status="sent" if success else "failed",
            error_message=None if success else message,
            error_type=metrics.get("error_type"),
            attachment_count=attachment_count,
            total_attachment_size=total_attachment_size,
            processing_time_ms=metrics.get("processing_time_ms"),
            smtp_connection_time_ms=metrics.get("smtp_connection_time_ms"),
            sent_at=sent_at,
            year=year,
            quarter=quarter,
            month=month,
            day_of_week=day_of_week,
            hour=hour,
            smtp_response=smtp_response,
            source_ip=client_ip,
            user_agent=user_agent,
        )
        db.add(email_log)
        await db.commit()

        if success:
            return EmailResponse(
                success=True,
                message=message,
                email_id=str(email_log.id),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "success": False,
                    "error": message,
                    "message": "Failed to send email",
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in send_email_endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": str(e),
                "message": "Internal server error",
            },
        )
