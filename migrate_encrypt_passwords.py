"""
Migration script to encrypt existing SMTP passwords.

Run this once to encrypt all existing plaintext SMTP passwords in the database.
"""
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.schemas import Client
from app.encryption import get_encryption


async def migrate_passwords():
    """Encrypt all existing SMTP passwords."""
    encryption = get_encryption()

    async with AsyncSessionLocal() as db:
        # Get all clients
        result = await db.execute(select(Client))
        clients = result.scalars().all()

        if not clients:
            print("No clients found in database.")
            return

        print(f"Found {len(clients)} clients")

        encrypted_count = 0
        skipped_count = 0

        for client in clients:
            try:
                # Try to decrypt - if it works, it's already encrypted
                decrypted = encryption.decrypt(client.smtp_password)
                print(f"✓ Client '{client.name}' - password already encrypted, skipping")
                skipped_count += 1
            except Exception:
                # Decryption failed, so it's plaintext - encrypt it
                try:
                    encrypted = encryption.encrypt(client.smtp_password)
                    client.smtp_password = encrypted
                    encrypted_count += 1
                    print(f"✓ Client '{client.name}' - password encrypted")
                except Exception as e:
                    print(f"✗ Client '{client.name}' - error encrypting: {e}")

        # Commit all changes
        if encrypted_count > 0:
            await db.commit()
            print(f"\n✓ Migration complete!")
            print(f"  - Encrypted: {encrypted_count} passwords")
            print(f"  - Skipped (already encrypted): {skipped_count}")
        else:
            print(f"\n✓ No migration needed - all passwords already encrypted")


if __name__ == "__main__":
    print("="*60)
    print("SMTP Password Encryption Migration")
    print("="*60)
    print()
    asyncio.run(migrate_passwords())
