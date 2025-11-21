#!/usr/bin/env python3
"""Management CLI for FastAPI SMTP Proxy."""
import asyncio
import sys
from datetime import datetime
from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db
from app.schemas import Client, APIKey
from app.auth import create_api_key
from app.config import settings
from app.analytics_service import (
    get_current_quarter, calculate_analytics_snapshot,
    rotate_old_quarters, get_analytics_summary
)


async def create_client_cli():
    """Interactive CLI to create a new client."""
    print("\n=== Create New Client ===\n")

    name = input("Client name: ").strip()
    smtp_host = input("SMTP host: ").strip()
    smtp_port = int(input("SMTP port [587]: ").strip() or "587")
    smtp_username = input("SMTP username: ").strip()
    smtp_password = input("SMTP password: ").strip()

    use_tls = input("Use TLS? [Y/n]: ").strip().lower() != 'n'
    use_ssl = input("Use SSL? [y/N]: ").strip().lower() == 'y'

    default_from_email = input("Default FROM email (optional): ").strip() or None
    default_from_name = input("Default FROM name (optional): ").strip() or None

    async with AsyncSessionLocal() as db:
        # Check if client exists
        result = await db.execute(select(Client).where(Client.name == name))
        if result.scalar_one_or_none():
            print(f"\n❌ Error: Client '{name}' already exists!")
            return

        # Create client
        client = Client(
            name=name,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password,
            smtp_use_tls=use_tls,
            smtp_use_ssl=use_ssl,
            default_from_email=default_from_email,
            default_from_name=default_from_name,
        )

        db.add(client)
        await db.commit()
        await db.refresh(client)

        print(f"\n✅ Client created successfully!")
        print(f"   ID: {client.id}")
        print(f"   Name: {client.name}")


async def list_clients_cli():
    """List all clients."""
    print("\n=== Clients ===\n")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Client).order_by(Client.id))
        clients = result.scalars().all()

        if not clients:
            print("No clients found.")
            return

        for client in clients:
            status = "✓ Active" if client.is_active else "✗ Inactive"
            print(f"ID: {client.id}")
            print(f"  Name: {client.name}")
            print(f"  SMTP: {client.smtp_username}@{client.smtp_host}:{client.smtp_port}")
            print(f"  Status: {status}")
            print(f"  Created: {client.created_at}")
            print()


async def create_api_key_cli():
    """Interactive CLI to create a new API key."""
    print("\n=== Create New API Key ===\n")

    # List clients first
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Client).order_by(Client.id))
        clients = result.scalars().all()

        if not clients:
            print("❌ No clients found. Create a client first.")
            return

        print("Available clients:")
        for client in clients:
            print(f"  {client.id}: {client.name}")

        client_id = int(input("\nClient ID: ").strip())

        # Verify client exists
        result = await db.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()

        if not client:
            print(f"\n❌ Error: Client with ID {client_id} not found!")
            return

        key_name = input("API key name/description: ").strip()

        # Create JWT token
        jwt_token, key_hash = create_api_key(
            client_id=client_id,
            key_name=key_name,
        )

        # Save to database
        api_key = APIKey(
            client_id=client_id,
            name=key_name,
            key_hash=key_hash,
        )

        db.add(api_key)
        await db.commit()
        await db.refresh(api_key)

        print(f"\n✅ API Key created successfully!")
        print(f"   ID: {api_key.id}")
        print(f"   Name: {api_key.name}")
        print(f"   Client: {client.name}")
        print(f"\n🔑 JWT Token (save this, it won't be shown again!):")
        print(f"   {jwt_token}")
        print()


async def list_api_keys_cli():
    """List all API keys."""
    print("\n=== API Keys ===\n")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(APIKey, Client)
            .join(Client)
            .order_by(APIKey.client_id, APIKey.id)
        )
        rows = result.all()

        if not rows:
            print("No API keys found.")
            return

        current_client_id = None
        for api_key, client in rows:
            if current_client_id != client.id:
                print(f"\nClient: {client.name} (ID: {client.id})")
                current_client_id = client.id

            status = "✓ Active" if api_key.is_active else "✗ Inactive"
            print(f"  ID: {api_key.id}")
            print(f"    Name: {api_key.name}")
            print(f"    Status: {status}")
            print(f"    Created: {api_key.created_at}")
            if api_key.last_used_at:
                print(f"    Last used: {api_key.last_used_at}")
            if api_key.expires_at:
                print(f"    Expires: {api_key.expires_at}")


async def create_snapshot_cli():
    """Create analytics snapshot for a client."""
    print("\n=== Create Analytics Snapshot ===\n")

    async with AsyncSessionLocal() as db:
        # List clients
        result = await db.execute(select(Client).order_by(Client.id))
        clients = result.scalars().all()

        if not clients:
            print("❌ No clients found.")
            return

        print("Available clients:")
        for client in clients:
            print(f"  {client.id}: {client.name}")

        client_id = int(input("\nClient ID (or 0 for all): ").strip())

        year, quarter = get_current_quarter()
        print(f"\nCurrent quarter: {year}-Q{quarter}")

        if client_id == 0:
            # Create snapshots for all clients
            for client in clients:
                snapshot = await calculate_analytics_snapshot(db, client.id, year, quarter)
                print(f"✅ Snapshot created for {client.name}: {snapshot.total_emails} emails")
        else:
            # Create snapshot for specific client
            result = await db.execute(select(Client).where(Client.id == client_id))
            client = result.scalar_one_or_none()

            if not client:
                print(f"\n❌ Error: Client with ID {client_id} not found!")
                return

            snapshot = await calculate_analytics_snapshot(db, client_id, year, quarter)
            print(f"\n✅ Snapshot created!")
            print(f"   Total Emails: {snapshot.total_emails}")
            print(f"   Success Rate: {snapshot.success_rate:.2f}%")
            print(f"   Period: {year}-Q{quarter}")


async def rotate_data_cli():
    """Rotate old quarterly data."""
    print("\n=== Quarterly Data Rotation ===\n")

    keep_quarters = int(input("Number of recent quarters to keep [2]: ").strip() or "2")

    print(f"\nThis will archive all data older than {keep_quarters} quarters.")
    confirm = input("Continue? [y/N]: ").strip().lower()

    if confirm != 'y':
        print("Aborted.")
        return

    async with AsyncSessionLocal() as db:
        summaries = await rotate_old_quarters(db, keep_quarters)

        if not summaries:
            print("\n✅ No data to rotate. All quarters are within the keep window.")
        else:
            print(f"\n✅ Rotation completed!")
            for summary in summaries:
                print(f"\n  Quarter: {summary.quarter}")
                print(f"    Archived: {summary.emails_archived} emails")
                print(f"    Deleted: {summary.emails_deleted} emails")
                print(f"    Snapshot created: {'Yes' if summary.snapshot_created else 'No'}")


async def show_analytics_cli():
    """Show analytics summary for a client."""
    print("\n=== Analytics Summary ===\n")

    async with AsyncSessionLocal() as db:
        # List clients
        result = await db.execute(select(Client).order_by(Client.id))
        clients = result.scalars().all()

        if not clients:
            print("❌ No clients found.")
            return

        print("Available clients:")
        for client in clients:
            print(f"  {client.id}: {client.name}")

        client_id = int(input("\nClient ID: ").strip())

        result = await db.execute(select(Client).where(Client.id == client_id))
        client = result.scalar_one_or_none()

        if not client:
            print(f"\n❌ Error: Client with ID {client_id} not found!")
            return

        days = int(input("Number of days to analyze [30]: ").strip() or "30")

        from datetime import timedelta
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        summary = await get_analytics_summary(db, client_id, start_date, end_date)

        print(f"\n📊 Analytics for {client.name}")
        print(f"   Period: {summary.period}")
        print(f"\n   📧 Email Volume")
        print(f"      Total: {summary.total_emails}")
        print(f"      Sent: {summary.total_sent}")
        print(f"      Failed: {summary.total_failed}")
        print(f"      Success Rate: {summary.success_rate:.2f}%")

        print(f"\n   ⚡ Performance")
        print(f"      Avg Processing Time: {summary.avg_processing_time_ms:.2f}ms")
        if summary.p95_processing_time_ms:
            print(f"      P95 Processing Time: {summary.p95_processing_time_ms:.2f}ms")
        if summary.p99_processing_time_ms:
            print(f"      P99 Processing Time: {summary.p99_processing_time_ms:.2f}ms")

        print(f"\n   📎 Attachments")
        print(f"      Total Attachments: {summary.total_attachments}")
        print(f"      Emails with Attachments: {summary.emails_with_attachments}")
        print(f"      Total Size: {summary.total_attachment_bytes / 1024 / 1024:.2f} MB")

        if summary.top_errors:
            print(f"\n   ❌ Top Errors")
            for error in summary.top_errors[:5]:
                print(f"      {error.error_type}: {error.count} ({error.percentage:.1f}%)")

        print()


async def main():
    """Main CLI entry point."""
    # Initialize database
    await init_db()

    if len(sys.argv) < 2:
        print("\nFastAPI SMTP Proxy - Management CLI")
        print("\nUsage: python manage.py <command>")
        print("\nClient Management:")
        print("  create-client     Create a new client")
        print("  list-clients      List all clients")
        print("\nAPI Key Management:")
        print("  create-api-key    Create a new API key")
        print("  list-api-keys     List all API keys")
        print("\nAnalytics:")
        print("  create-snapshot   Create analytics snapshot")
        print("  show-analytics    Show analytics summary")
        print("  rotate-data       Rotate old quarterly data")
        print()
        sys.exit(1)

    command = sys.argv[1]

    if command == "create-client":
        await create_client_cli()
    elif command == "list-clients":
        await list_clients_cli()
    elif command == "create-api-key":
        await create_api_key_cli()
    elif command == "list-api-keys":
        await list_api_keys_cli()
    elif command == "create-snapshot":
        await create_snapshot_cli()
    elif command == "show-analytics":
        await show_analytics_cli()
    elif command == "rotate-data":
        await rotate_data_cli()
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
