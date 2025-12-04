"""Analytics endpoints."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AnalyticsSummary, AnalyticsSnapshotResponse, RotationSummary
from app.schemas import Client, AnalyticsSnapshot, AdminUser
from app.auth import get_current_client, get_admin_user
from app.analytics_service import (
    get_analytics_summary,
    calculate_analytics_snapshot,
    rotate_old_quarters,
    get_current_quarter,
)

logger = logging.getLogger(__name__)

# Client-facing analytics endpoints
client_router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Admin analytics endpoints
admin_router = APIRouter(prefix="/api/admin/analytics", tags=["admin", "analytics"])


# ============================================================================
# Client Analytics Endpoints
# ============================================================================


@client_router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Get analytics summary",
    description="Get comprehensive analytics summary for a period",
)
async def get_analytics_summary_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get analytics summary for the authenticated client.

    Args:
        days: Number of days to include in the summary (default: 30)
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db, client_id=client.id, start_date=start_date, end_date=end_date
    )

    return summary


@client_router.get(
    "/snapshots",
    response_model=list[AnalyticsSnapshotResponse],
    summary="Get analytics snapshots",
    description="Get quarterly analytics snapshots for a client",
)
async def get_snapshots_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
    limit: int = 10,
):
    """
    Get analytics snapshots for the authenticated client.

    Returns the most recent quarterly/monthly snapshots.
    """
    result = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.client_id == client.id)
        .order_by(AnalyticsSnapshot.year.desc(), AnalyticsSnapshot.quarter.desc())
        .limit(limit)
    )
    snapshots = result.scalars().all()

    return [AnalyticsSnapshotResponse.model_validate(s) for s in snapshots]


@client_router.post(
    "/snapshot/create",
    response_model=AnalyticsSnapshotResponse,
    summary="Create analytics snapshot",
    description="Manually create an analytics snapshot for the current quarter",
)
async def create_snapshot_endpoint(
    client: Client = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
):
    """
    Create an analytics snapshot for the authenticated client's current quarter.
    """
    year, quarter = get_current_quarter()
    snapshot = await calculate_analytics_snapshot(
        db=db, client_id=client.id, year=year, quarter=quarter
    )

    return AnalyticsSnapshotResponse.model_validate(snapshot)


# ============================================================================
# Admin Analytics Endpoints
# ============================================================================


@admin_router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Get global analytics summary",
    description="Get analytics summary across all clients (admin only)",
)
async def get_global_analytics_endpoint(
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get global analytics summary across all clients.

    Requires admin authentication via HTTP Basic Auth.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db, start_date=start_date, end_date=end_date
    )

    return summary


@admin_router.post(
    "/rotate",
    response_model=list[RotationSummary],
    summary="Rotate old quarters",
    description="Manually trigger quarterly data rotation (admin only)",
)
async def rotate_quarters_endpoint(
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    keep_quarters: int = 2,
):
    """
    Manually trigger quarterly data rotation.

    This will archive email logs older than the specified number of quarters
    and create analytics snapshots.

    Requires admin authentication via HTTP Basic Auth.

    Args:
        keep_quarters: Number of recent quarters to keep (default: 2)
    """
    summaries = await rotate_old_quarters(db, keep_quarters)
    return summaries


@admin_router.get(
    "/client/{client_id}",
    response_model=AnalyticsSummary,
    summary="Get client analytics",
    description="Get analytics for a specific client (admin only)",
)
async def get_client_analytics_endpoint(
    client_id: int,
    admin: AdminUser = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    days: int = 30,
):
    """
    Get analytics for a specific client.

    Requires admin authentication via HTTP Basic Auth.
    """
    # Verify client exists
    result = await db.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Client with ID {client_id} not found",
        )

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await get_analytics_summary(
        db=db, client_id=client_id, start_date=start_date, end_date=end_date
    )

    return summary
