"""SMTP email sending service."""
import base64
import logging
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List, Tuple, Dict
import aiosmtplib
from app.schemas import Client
from app.models import EmailRequest
from app.encryption import get_encryption

logger = logging.getLogger(__name__)


class SMTPService:
    """Service for sending emails via SMTP."""

    def __init__(self, client: Client):
        """
        Initialize SMTP service with client configuration.

        Args:
            client: Client database model containing SMTP configuration
        """
        self.client = client
        self.smtp_host = client.smtp_host
        self.smtp_port = client.smtp_port
        self.smtp_username = client.smtp_username

        # Decrypt SMTP password for use
        encryption = get_encryption()
        self.smtp_password = encryption.decrypt(client.smtp_password)

        self.use_tls = client.smtp_use_tls
        self.use_ssl = client.smtp_use_ssl

    async def send_email(self, email_request: EmailRequest) -> Tuple[bool, str, Optional[str], Dict]:
        """
        Send an email via SMTP.

        Args:
            email_request: EmailRequest model containing email details

        Returns:
            tuple: (success: bool, message: str, smtp_response: Optional[str], metrics: dict)
                metrics contains: processing_time_ms, smtp_connection_time_ms, error_type
        """
        start_time = time.time()
        metrics = {
            'processing_time_ms': 0.0,
            'smtp_connection_time_ms': 0.0,
            'error_type': None
        }

        try:
            # Create message
            message = self._create_message(email_request)

            # Connect and send (track SMTP time)
            smtp_start = time.time()
            smtp_response = await self._send_via_smtp(message, email_request.to)
            smtp_end = time.time()

            metrics['smtp_connection_time_ms'] = (smtp_end - smtp_start) * 1000

            logger.info(
                f"Email sent successfully to {', '.join(email_request.to)} "
                f"via {self.client.name}"
            )

            # Calculate total processing time
            end_time = time.time()
            metrics['processing_time_ms'] = (end_time - start_time) * 1000

            return True, "Email sent successfully", smtp_response, metrics

        except aiosmtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            error_type = type(e).__name__
            metrics['error_type'] = error_type
            logger.error(f"Failed to send email via {self.client.name}: {error_msg}")
            # Calculate total processing time
            end_time = time.time()
            metrics['processing_time_ms'] = (end_time - start_time) * 1000

            return False, error_msg, None, metrics

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            error_type = type(e).__name__
            metrics['error_type'] = error_type
            logger.error(f"Failed to send email via {self.client.name}: {error_msg}")

            # Calculate total processing time
            end_time = time.time()
            metrics['processing_time_ms'] = (end_time - start_time) * 1000

            return False, error_msg, None, metrics

    def _create_message(self, email_request: EmailRequest) -> MIMEMultipart:
        """
        Create MIME message from email request.

        Args:
            email_request: EmailRequest model

        Returns:
            MIMEMultipart: The constructed email message
        """
        # Determine if we have attachments
        has_attachments = email_request.attachments and len(email_request.attachments) > 0

        if has_attachments:
            message = MIMEMultipart('mixed')
            message_body = MIMEMultipart('alternative')
        else:
            message = MIMEMultipart('alternative')
            message_body = message

        # Set headers
        from_email = email_request.from_email or self.client.default_from_email or self.smtp_username
        from_name = email_request.from_name or self.client.default_from_name

        if from_name:
            message['From'] = f"{from_name} <{from_email}>"
        else:
            message['From'] = from_email

        message['To'] = ', '.join(email_request.to)
        message['Subject'] = email_request.subject

        # Optional headers
        if email_request.reply_to:
            message['Reply-To'] = email_request.reply_to

        if email_request.cc:
            message['Cc'] = ', '.join(email_request.cc)

        # Custom headers
        if email_request.headers:
            for header in email_request.headers:
                if ':' in header:
                    key, value = header.split(':', 1)
                    message[key.strip()] = value.strip()

        # Add body
        if email_request.content_type == 'text/plain':
            body_part = MIMEText(email_request.content, 'plain', 'utf-8')
        else:
            body_part = MIMEText(email_request.content, 'html', 'utf-8')

        message_body.attach(body_part)

        # Attach files if any
        if has_attachments:
            message.attach(message_body)
            for attachment in email_request.attachments:
                self._add_attachment(message, attachment)

        return message

    def _add_attachment(self, message: MIMEMultipart, attachment: dict):
        """
        Add an attachment to the email message.

        Args:
            message: The MIME message to attach to
            attachment: Dictionary containing attachment data
                Expected format:
                {
                    "filename": "file.pdf",
                    "content": "base64_encoded_content",
                    "content_type": "application/pdf"  # optional
                }
        """
        try:
            filename = attachment.get('filename', 'attachment')
            content = attachment.get('content', '')
            content_type = attachment.get('content_type', 'application/octet-stream')

            # Decode base64 content
            file_data = base64.b64decode(content)

            # Create attachment part
            part = MIMEBase(*content_type.split('/', 1))
            part.set_payload(file_data)
            encoders.encode_base64(part)

            # Add header
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )

            message.attach(part)
            logger.debug(f"Added attachment: {filename}")

        except Exception as e:
            logger.error(f"Failed to add attachment {attachment.get('filename')}: {str(e)}")
            # Continue without this attachment rather than failing completely

    async def _send_via_smtp(self, message: MIMEMultipart, recipients: List[str]) -> str:
        """
        Send the email message via SMTP.

        Args:
            message: The MIME message to send
            recipients: List of recipient email addresses

        Returns:
            str: SMTP server response

        Raises:
            aiosmtplib.SMTPException: If sending fails
        """
        # Determine connection parameters
        if self.use_ssl:
            use_tls = False
            start_tls = False
        elif self.use_tls:
            use_tls = False
            start_tls = True
        else:
            use_tls = False
            start_tls = False

        # Create SMTP client
        smtp = aiosmtplib.SMTP(
            hostname=self.smtp_host,
            port=self.smtp_port,
            use_tls=use_tls,
            start_tls=start_tls,
        )

        try:
            # Connect to server
            await smtp.connect()

            # Login if credentials provided
            if self.smtp_username and self.smtp_password:
                await smtp.login(self.smtp_username, self.smtp_password)

            # Send message
            response = await smtp.send_message(message)

            return str(response)

        finally:
            # Always close connection
            try:
                await smtp.quit()
            except:
                pass


async def send_email(client: Client, email_request: EmailRequest) -> Tuple[bool, str, Optional[str], Dict]:
    """
    Helper function to send an email.

    Args:
        client: Client model with SMTP configuration
        email_request: EmailRequest model

    Returns:
        tuple: (success: bool, message: str, smtp_response: Optional[str], metrics: dict)
    """
    service = SMTPService(client)
    return await service.send_email(email_request)
