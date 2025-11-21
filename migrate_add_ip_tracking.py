"""
Database migration script to add IP tracking features.

This migration adds:
1. source_ip, user_agent, country_code columns to email_logs table
2. login_attempts table for tracking all login attempts

Run with: python migrate_add_ip_tracking.py
"""
import asyncio
import sys
from sqlalchemy import text
from app.database import engine, get_db
from app.config import settings

async def migrate():
    """Run the migration."""
    print("🔄 Starting IP tracking migration...")

    async with engine.begin() as conn:
        # Check if columns already exist (SQLite-compatible)
        print("\n📋 Checking email_logs table...")
        result = await conn.execute(text("PRAGMA table_info(email_logs)"))
        columns = result.fetchall()
        existing_columns = [col[1] for col in columns]  # col[1] is the column name

        # Add columns to email_logs if they don't exist
        if 'source_ip' not in existing_columns:
            print("  ✅ Adding source_ip column to email_logs...")
            await conn.execute(text("ALTER TABLE email_logs ADD COLUMN source_ip VARCHAR(45)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_source_ip_sent_at ON email_logs(source_ip, sent_at)"))
        else:
            print("  ⏭️  source_ip column already exists")

        if 'user_agent' not in existing_columns:
            print("  ✅ Adding user_agent column to email_logs...")
            await conn.execute(text("ALTER TABLE email_logs ADD COLUMN user_agent VARCHAR(500)"))
        else:
            print("  ⏭️  user_agent column already exists")

        if 'country_code' not in existing_columns:
            print("  ✅ Adding country_code column to email_logs...")
            await conn.execute(text("ALTER TABLE email_logs ADD COLUMN country_code VARCHAR(2)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_email_logs_country_code ON email_logs(country_code)"))
        else:
            print("  ⏭️  country_code column already exists")

        # Check if login_attempts table exists (SQLite-compatible)
        print("\n📋 Checking login_attempts table...")
        result = await conn.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='login_attempts'
        """))
        table_exists = result.fetchone() is not None

        if not table_exists:
            print("  ✅ Creating login_attempts table...")
            await conn.execute(text("""
                CREATE TABLE login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45) NOT NULL,
                    user_agent VARCHAR(500),
                    success BOOLEAN NOT NULL,
                    failure_reason VARCHAR(100),
                    attempted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    country_code VARCHAR(2),
                    city VARCHAR(100)
                )
            """))

            # Create indexes
            print("  ✅ Creating indexes for login_attempts...")
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_username ON login_attempts(username)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_ip_address ON login_attempts(ip_address)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_success ON login_attempts(success)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_attempted_at ON login_attempts(attempted_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_login_country_code ON login_attempts(country_code)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ip_attempted_at ON login_attempts(ip_address, attempted_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_username_attempted_at ON login_attempts(username, attempted_at)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_success_attempted_at ON login_attempts(success, attempted_at)"))
        else:
            print("  ⏭️  login_attempts table already exists")

    print("\n✅ Migration completed successfully!")
    print("\n📊 IP tracking features are now enabled:")
    print("   • Email logs now track source IP, user agent, and country")
    print("   • Login attempts are tracked in the login_attempts table")
    print("   • View security logs at: /admin/security-logs")
    print("\n💡 Note: Country code detection requires GeoIP integration")
    print("   For now, country_code fields will be NULL until GeoIP is configured")

async def rollback():
    """Rollback the migration."""
    print("🔄 Rolling back IP tracking migration...")

    async with engine.begin() as conn:
        # Drop columns from email_logs
        print("\n📋 Removing columns from email_logs...")
        try:
            await conn.execute(text("DROP INDEX IF EXISTS idx_source_ip_sent_at"))
            await conn.execute(text("DROP INDEX IF EXISTS idx_email_logs_country_code"))
            await conn.execute(text("ALTER TABLE email_logs DROP COLUMN IF EXISTS source_ip"))
            await conn.execute(text("ALTER TABLE email_logs DROP COLUMN IF EXISTS user_agent"))
            await conn.execute(text("ALTER TABLE email_logs DROP COLUMN IF EXISTS country_code"))
            print("  ✅ Columns removed from email_logs")
        except Exception as e:
            print(f"  ⚠️  Error removing columns: {e}")

        # Drop login_attempts table
        print("\n📋 Removing login_attempts table...")
        try:
            await conn.execute(text("DROP TABLE IF EXISTS login_attempts CASCADE"))
            print("  ✅ login_attempts table dropped")
        except Exception as e:
            print(f"  ⚠️  Error dropping table: {e}")

    print("\n✅ Rollback completed!")

async def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        await rollback()
    else:
        await migrate()

if __name__ == "__main__":
    asyncio.run(main())
