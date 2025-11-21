"""Analytics and quarterly rotation service."""
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, cast, String
from sqlalchemy.sql import extract
from app.schemas import EmailLog, ArchivedEmailLog, AnalyticsSnapshot, Client
from app.models import (
    AnalyticsSummary, DailyMetrics, HourlyDistribution,
    ErrorDistribution, RotationSummary
)

logger = logging.getLogger(__name__)


def get_quarter(dt: datetime) -> int:
    """Get quarter number (1-4) from datetime."""
    return (dt.month - 1) // 3 + 1


def get_quarter_start_end(year: int, quarter: int) -> Tuple[datetime, datetime]:
    """Get start and end dates for a quarter."""
    start_month = (quarter - 1) * 3 + 1
    start_date = datetime(year, start_month, 1)

    if quarter == 4:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, start_month + 3, 1)

    return start_date, end_date


def get_current_quarter() -> Tuple[int, int]:
    """Get current year and quarter."""
    now = datetime.utcnow()
    return now.year, get_quarter(now)


def get_previous_quarters(count: int = 2) -> List[Tuple[int, int]]:
    """Get list of previous quarters to keep (not archive)."""
    current_year, current_quarter = get_current_quarter()
    quarters = [(current_year, current_quarter)]

    year, quarter = current_year, current_quarter
    for _ in range(count):
        quarter -= 1
        if quarter < 1:
            quarter = 4
            year -= 1
        quarters.append((year, quarter))

    return quarters


async def calculate_analytics_snapshot(
    db: AsyncSession,
    client_id: int,
    year: int,
    quarter: int,
    month: Optional[int] = None
) -> AnalyticsSnapshot:
    """
    Calculate and create analytics snapshot for a specific period.

    Args:
        db: Database session
        client_id: Client ID
        year: Year
        quarter: Quarter (1-4)
        month: Optional month for monthly snapshots

    Returns:
        AnalyticsSnapshot: Created snapshot
    """
    logger.info(f"Calculating analytics for client {client_id}, {year}-Q{quarter}")

    # Build date filter
    start_date, end_date = get_quarter_start_end(year, quarter)

    if month:
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

    # Query email logs for the period
    base_query = select(EmailLog).where(
        and_(
            EmailLog.client_id == client_id,
            EmailLog.sent_at >= start_date,
            EmailLog.sent_at < end_date
        )
    )

    result = await db.execute(base_query)
    email_logs = result.scalars().all()

    if not email_logs:
        logger.warning(f"No email logs found for client {client_id}, {year}-Q{quarter}")
        # Return empty snapshot
        return AnalyticsSnapshot(
            client_id=client_id,
            year=year,
            quarter=quarter,
            month=month
        )

    # Calculate metrics
    total_emails = len(email_logs)
    total_sent = sum(1 for log in email_logs if log.status == 'sent')
    total_failed = total_emails - total_sent
    success_rate = (total_sent / total_emails * 100) if total_emails > 0 else 0.0

    # Recipient metrics
    total_recipients = sum(log.to_count for log in email_logs)
    total_cc = sum(log.cc_count for log in email_logs)
    total_bcc = sum(log.bcc_count for log in email_logs)

    # Attachment metrics
    emails_with_attachments = sum(1 for log in email_logs if log.attachment_count > 0)
    total_attachments = sum(log.attachment_count for log in email_logs)
    total_attachment_bytes = sum(log.total_attachment_size for log in email_logs)
    avg_attachment_size = (
        total_attachment_bytes / total_attachments if total_attachments > 0 else 0.0
    )

    # Performance metrics
    processing_times = [log.processing_time_ms for log in email_logs if log.processing_time_ms]
    smtp_times = [log.smtp_connection_time_ms for log in email_logs if log.smtp_connection_time_ms]

    avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
    avg_smtp_time = sum(smtp_times) / len(smtp_times) if smtp_times else 0.0
    max_processing_time = max(processing_times) if processing_times else 0.0
    min_processing_time = min(processing_times) if processing_times else 0.0

    # Content type distribution
    html_emails = sum(1 for log in email_logs if log.content_type == 'text/html')
    plain_text_emails = sum(1 for log in email_logs if log.content_type == 'text/plain')

    # Peak usage analysis
    hour_counts: Dict[int, int] = {}
    day_counts: Dict[int, int] = {}

    for log in email_logs:
        hour_counts[log.hour] = hour_counts.get(log.hour, 0) + 1
        day_counts[log.day_of_week] = day_counts.get(log.day_of_week, 0) + 1

    peak_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else None
    peak_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else None
    peak_emails_in_hour = hour_counts[peak_hour] if peak_hour is not None else 0

    # Error analytics
    error_types: Dict[str, int] = {}
    for log in email_logs:
        if log.error_type:
            error_types[log.error_type] = error_types.get(log.error_type, 0) + 1

    error_types_json = json.dumps(error_types) if error_types else None

    # Create or update snapshot
    result = await db.execute(
        select(AnalyticsSnapshot).where(
            and_(
                AnalyticsSnapshot.client_id == client_id,
                AnalyticsSnapshot.year == year,
                AnalyticsSnapshot.quarter == quarter,
                AnalyticsSnapshot.month == month
            )
        )
    )
    snapshot = result.scalar_one_or_none()

    if snapshot:
        # Update existing snapshot
        snapshot.total_emails = total_emails
        snapshot.total_sent = total_sent
        snapshot.total_failed = total_failed
        snapshot.success_rate = success_rate
        snapshot.total_recipients = total_recipients
        snapshot.total_cc = total_cc
        snapshot.total_bcc = total_bcc
        snapshot.emails_with_attachments = emails_with_attachments
        snapshot.total_attachments = total_attachments
        snapshot.total_attachment_bytes = total_attachment_bytes
        snapshot.avg_attachment_size = avg_attachment_size
        snapshot.avg_processing_time_ms = avg_processing_time
        snapshot.avg_smtp_connection_time_ms = avg_smtp_time
        snapshot.max_processing_time_ms = max_processing_time
        snapshot.min_processing_time_ms = min_processing_time
        snapshot.html_emails = html_emails
        snapshot.plain_text_emails = plain_text_emails
        snapshot.peak_hour = peak_hour
        snapshot.peak_day = peak_day
        snapshot.peak_emails_in_hour = peak_emails_in_hour
        snapshot.error_types_json = error_types_json
    else:
        # Create new snapshot
        snapshot = AnalyticsSnapshot(
            client_id=client_id,
            year=year,
            quarter=quarter,
            month=month,
            total_emails=total_emails,
            total_sent=total_sent,
            total_failed=total_failed,
            success_rate=success_rate,
            total_recipients=total_recipients,
            total_cc=total_cc,
            total_bcc=total_bcc,
            emails_with_attachments=emails_with_attachments,
            total_attachments=total_attachments,
            total_attachment_bytes=total_attachment_bytes,
            avg_attachment_size=avg_attachment_size,
            avg_processing_time_ms=avg_processing_time,
            avg_smtp_connection_time_ms=avg_smtp_time,
            max_processing_time_ms=max_processing_time,
            min_processing_time_ms=min_processing_time,
            html_emails=html_emails,
            plain_text_emails=plain_text_emails,
            peak_hour=peak_hour,
            peak_day=peak_day,
            peak_emails_in_hour=peak_emails_in_hour,
            error_types_json=error_types_json,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(snapshot)

    logger.info(f"Analytics snapshot created/updated: {snapshot.id}")
    return snapshot


async def archive_quarter(
    db: AsyncSession,
    year: int,
    quarter: int,
    keep_quarters: int = 2
) -> RotationSummary:
    """
    Archive a specific quarter's email logs.

    This function:
    1. Creates analytics snapshots for all clients
    2. Archives email logs to the archived table
    3. Deletes email logs from the main table

    Args:
        db: Database session
        year: Year to archive
        quarter: Quarter to archive (1-4)
        keep_quarters: Number of recent quarters to keep (default: 2)

    Returns:
        RotationSummary: Summary of the rotation operation
    """
    logger.info(f"Starting archive process for {year}-Q{quarter}")

    # Check if this quarter should be kept
    quarters_to_keep = get_previous_quarters(keep_quarters)
    if (year, quarter) in quarters_to_keep:
        logger.warning(f"Attempted to archive {year}-Q{quarter}, but it's within keep window")
        return RotationSummary(
            quarter=f"{year}-Q{quarter}",
            emails_archived=0,
            emails_deleted=0,
            snapshot_created=False,
            archived_at=datetime.utcnow()
        )

    # Get all clients
    result = await db.execute(select(Client))
    clients = result.scalars().all()

    total_archived = 0
    total_deleted = 0
    snapshots_created = 0

    for client in clients:
        # Create analytics snapshot
        try:
            await calculate_analytics_snapshot(db, client.id, year, quarter)
            snapshots_created += 1
        except Exception as e:
            logger.error(f"Failed to create snapshot for client {client.id}: {str(e)}")

        # Get email logs for this quarter
        result = await db.execute(
            select(EmailLog).where(
                and_(
                    EmailLog.client_id == client.id,
                    EmailLog.year == year,
                    EmailLog.quarter == quarter
                )
            )
        )
        email_logs = result.scalars().all()

        # Archive each email log
        for log in email_logs:
            # Hash subject for privacy
            subject_hash = hashlib.sha256(log.subject.encode()).hexdigest()

            archived_log = ArchivedEmailLog(
                original_id=log.id,
                client_id=log.client_id,
                api_key_id=log.api_key_id,
                to_count=log.to_count,
                cc_count=log.cc_count,
                bcc_count=log.bcc_count,
                subject_hash=subject_hash,
                content_type=log.content_type,
                status=log.status,
                error_type=log.error_type,
                attachment_count=log.attachment_count,
                total_attachment_size=log.total_attachment_size,
                processing_time_ms=log.processing_time_ms,
                smtp_connection_time_ms=log.smtp_connection_time_ms,
                sent_at=log.sent_at,
                year=log.year,
                quarter=log.quarter,
                month=log.month,
                day_of_week=log.day_of_week,
                hour=log.hour,
            )

            db.add(archived_log)
            total_archived += 1

        # Delete original email logs
        for log in email_logs:
            await db.delete(log)
            total_deleted += 1

    await db.commit()

    logger.info(
        f"Archive completed for {year}-Q{quarter}: "
        f"{total_archived} archived, {total_deleted} deleted, "
        f"{snapshots_created} snapshots created"
    )

    return RotationSummary(
        quarter=f"{year}-Q{quarter}",
        emails_archived=total_archived,
        emails_deleted=total_deleted,
        snapshot_created=snapshots_created > 0,
        archived_at=datetime.utcnow()
    )


async def rotate_old_quarters(db: AsyncSession, keep_quarters: int = 2) -> List[RotationSummary]:
    """
    Automatically rotate all quarters older than the keep window.

    Args:
        db: Database session
        keep_quarters: Number of recent quarters to keep

    Returns:
        List[RotationSummary]: Summary for each rotated quarter
    """
    logger.info(f"Starting automatic rotation (keeping {keep_quarters} recent quarters)")

    # Get quarters to keep
    quarters_to_keep = get_previous_quarters(keep_quarters)
    current_year, current_quarter = quarters_to_keep[0]

    # Find all unique year/quarter combinations in email_logs
    result = await db.execute(
        select(EmailLog.year, EmailLog.quarter)
        .group_by(EmailLog.year, EmailLog.quarter)
        .order_by(EmailLog.year, EmailLog.quarter)
    )
    existing_quarters = result.all()

    summaries = []
    for year, quarter in existing_quarters:
        if (year, quarter) not in quarters_to_keep:
            logger.info(f"Rotating {year}-Q{quarter}")
            summary = await archive_quarter(db, year, quarter, keep_quarters)
            summaries.append(summary)

    logger.info(f"Rotation completed: {len(summaries)} quarters rotated")
    return summaries


async def get_analytics_summary(
    db: AsyncSession,
    client_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> AnalyticsSummary:
    """
    Get comprehensive analytics summary for a period.

    Args:
        db: Database session
        client_id: Optional client ID filter
        start_date: Start date (default: 30 days ago)
        end_date: End date (default: now)

    Returns:
        AnalyticsSummary: Comprehensive analytics
    """
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Build query
    query = select(EmailLog).where(
        and_(
            EmailLog.sent_at >= start_date,
            EmailLog.sent_at < end_date
        )
    )

    if client_id:
        query = query.where(EmailLog.client_id == client_id)

    result = await db.execute(query)
    email_logs = result.scalars().all()

    # Calculate overall metrics
    total_emails = len(email_logs)
    total_sent = sum(1 for log in email_logs if log.status == 'sent')
    total_failed = total_emails - total_sent
    success_rate = (total_sent / total_emails * 100) if total_emails > 0 else 0.0

    # Daily metrics
    daily_data: Dict[str, Dict] = {}
    for log in email_logs:
        date_str = log.sent_at.strftime('%Y-%m-%d')
        if date_str not in daily_data:
            daily_data[date_str] = {'total': 0, 'sent': 0, 'failed': 0}
        daily_data[date_str]['total'] += 1
        if log.status == 'sent':
            daily_data[date_str]['sent'] += 1
        else:
            daily_data[date_str]['failed'] += 1

    daily_metrics = [
        DailyMetrics(
            date=date,
            total_emails=data['total'],
            total_sent=data['sent'],
            total_failed=data['failed'],
            success_rate=(data['sent'] / data['total'] * 100) if data['total'] > 0 else 0.0
        )
        for date, data in sorted(daily_data.items())
    ]

    # Hourly distribution
    hourly_data: Dict[int, int] = {}
    for log in email_logs:
        hourly_data[log.hour] = hourly_data.get(log.hour, 0) + 1

    hourly_distribution = [
        HourlyDistribution(hour=hour, email_count=count)
        for hour, count in sorted(hourly_data.items())
    ]

    # Performance metrics
    processing_times = [log.processing_time_ms for log in email_logs if log.processing_time_ms]
    processing_times.sort()

    avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0

    p95_idx = int(len(processing_times) * 0.95)
    p99_idx = int(len(processing_times) * 0.99)
    p95_processing_time = processing_times[p95_idx] if p95_idx < len(processing_times) else None
    p99_processing_time = processing_times[p99_idx] if p99_idx < len(processing_times) else None

    # Error distribution
    error_counts: Dict[str, int] = {}
    for log in email_logs:
        if log.error_type:
            error_counts[log.error_type] = error_counts.get(log.error_type, 0) + 1

    failed_count = sum(error_counts.values())
    top_errors = [
        ErrorDistribution(
            error_type=error_type,
            count=count,
            percentage=(count / failed_count * 100) if failed_count > 0 else 0.0
        )
        for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

    # Attachment metrics
    total_attachments = sum(log.attachment_count for log in email_logs)
    total_attachment_bytes = sum(log.total_attachment_size for log in email_logs)
    emails_with_attachments = sum(1 for log in email_logs if log.attachment_count > 0)

    return AnalyticsSummary(
        period=f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        start_date=start_date,
        end_date=end_date,
        total_emails=total_emails,
        total_sent=total_sent,
        total_failed=total_failed,
        success_rate=success_rate,
        daily_metrics=daily_metrics,
        hourly_distribution=hourly_distribution,
        avg_processing_time_ms=avg_processing_time,
        p95_processing_time_ms=p95_processing_time,
        p99_processing_time_ms=p99_processing_time,
        top_errors=top_errors,
        total_attachments=total_attachments,
        total_attachment_bytes=total_attachment_bytes,
        emails_with_attachments=emails_with_attachments,
    )
