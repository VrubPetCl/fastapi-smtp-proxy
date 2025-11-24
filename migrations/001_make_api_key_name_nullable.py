"""Migration: Make api_keys.name column nullable.

This migration allows the 'name' field in the api_keys table to be NULL,
supporting optional descriptions for API keys.

Run this script with: python migrations/001_make_api_key_name_nullable.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine
from sqlalchemy import text


async def migrate():
    """Apply the migration."""
    async with engine.begin() as conn:
        print("Making api_keys.name column nullable...")

        # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
        # This migration is designed for SQLite (the default database in this project)

        print("Applying SQLite migration...")
        # SQLite approach: rename table, create new one, copy data, drop old
        await conn.execute(text("""
            CREATE TABLE api_keys_new (
                id INTEGER PRIMARY KEY,
                client_id INTEGER NOT NULL,
                name VARCHAR(255),
                key_hash VARCHAR(255) UNIQUE NOT NULL,
                created_at DATETIME NOT NULL,
                last_used_at DATETIME,
                expires_at DATETIME,
                is_active BOOLEAN NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """))

        await conn.execute(text("""
            INSERT INTO api_keys_new (id, client_id, name, key_hash, created_at, last_used_at, expires_at, is_active)
            SELECT id, client_id, name, key_hash, created_at, last_used_at, expires_at, is_active
            FROM api_keys
        """))

        await conn.execute(text("DROP TABLE api_keys"))
        await conn.execute(text("ALTER TABLE api_keys_new RENAME TO api_keys"))

        # Recreate indexes
        await conn.execute(text("CREATE INDEX ix_api_keys_id ON api_keys (id)"))
        await conn.execute(text("CREATE INDEX ix_api_keys_key_hash ON api_keys (key_hash)"))

        print("Migration completed successfully!")


async def rollback():
    """Rollback the migration (make name NOT NULL again)."""
    async with engine.begin() as conn:
        print("Rolling back: Making api_keys.name column NOT NULL...")

        # First, update any NULL values to default value
        await conn.execute(text("""
            UPDATE api_keys
            SET name = 'Unnamed Key'
            WHERE name IS NULL
        """))

        # SQLite approach
        await conn.execute(text("""
            CREATE TABLE api_keys_new (
                id INTEGER PRIMARY KEY,
                client_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                key_hash VARCHAR(255) UNIQUE NOT NULL,
                created_at DATETIME NOT NULL,
                last_used_at DATETIME,
                expires_at DATETIME,
                is_active BOOLEAN NOT NULL,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """))

        await conn.execute(text("""
            INSERT INTO api_keys_new (id, client_id, name, key_hash, created_at, last_used_at, expires_at, is_active)
            SELECT id, client_id, name, key_hash, created_at, last_used_at, expires_at, is_active
            FROM api_keys
        """))

        await conn.execute(text("DROP TABLE api_keys"))
        await conn.execute(text("ALTER TABLE api_keys_new RENAME TO api_keys"))

        # Recreate indexes
        await conn.execute(text("CREATE INDEX ix_api_keys_id ON api_keys (id)"))
        await conn.execute(text("CREATE INDEX ix_api_keys_key_hash ON api_keys (key_hash)"))

        print("Rollback completed successfully!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback())
    else:
        asyncio.run(migrate())
