"""Web authentication service for admin users."""
import secrets
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.schemas import AdminUser, PasswordResetToken

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


async def authenticate_admin(db: AsyncSession, username: str, password: str) -> Optional[AdminUser]:
    """
    Authenticate an admin user.

    Args:
        db: Database session
        username: Username or email
        password: Plain text password

    Returns:
        AdminUser if authentication successful, None otherwise
    """
    # Try to find by username or email
    result = await db.execute(
        select(AdminUser).where(
            (AdminUser.username == username) | (AdminUser.email == username)
        )
    )
    admin = result.scalar_one_or_none()

    if not admin:
        return None

    if not admin.is_active:
        return None

    if not verify_password(password, admin.password_hash):
        return None

    # Update last login
    admin.last_login_at = datetime.utcnow()
    await db.commit()

    return admin


async def create_password_reset_token(db: AsyncSession, admin_user_id: int) -> str:
    """
    Create a password reset token for an admin user.

    Args:
        db: Database session
        admin_user_id: Admin user ID

    Returns:
        str: Reset token
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=24)

    reset_token = PasswordResetToken(
        admin_user_id=admin_user_id,
        token=token,
        expires_at=expires_at
    )

    db.add(reset_token)
    await db.commit()

    return token


async def verify_reset_token(db: AsyncSession, token: str) -> Optional[AdminUser]:
    """
    Verify a password reset token.

    Args:
        db: Database session
        token: Reset token

    Returns:
        AdminUser if token is valid, None otherwise
    """
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token
        )
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        return None

    if reset_token.used_at:
        return None

    if reset_token.expires_at < datetime.utcnow():
        return None

    # Get admin user
    result = await db.execute(
        select(AdminUser).where(AdminUser.id == reset_token.admin_user_id)
    )
    admin = result.scalar_one_or_none()

    return admin


async def reset_password(db: AsyncSession, token: str, new_password: str) -> bool:
    """
    Reset password using a reset token.

    Args:
        db: Database session
        token: Reset token
        new_password: New plain text password

    Returns:
        bool: True if successful, False otherwise
    """
    admin = await verify_reset_token(db, token)

    if not admin:
        return False

    # Update password
    admin.password_hash = hash_password(new_password)

    # Mark token as used
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset_token = result.scalar_one_or_none()
    reset_token.used_at = datetime.utcnow()

    await db.commit()

    return True


async def create_admin_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    is_superuser: bool = False
) -> AdminUser:
    """
    Create a new admin user.

    Args:
        db: Database session
        username: Username
        email: Email address
        password: Plain text password
        full_name: Full name (optional)
        is_superuser: Is superuser flag

    Returns:
        AdminUser: Created admin user
    """
    admin = AdminUser(
        username=username,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        is_superuser=is_superuser
    )

    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    return admin
