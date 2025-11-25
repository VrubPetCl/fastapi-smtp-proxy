"""Session management utilities."""
from datetime import datetime, timedelta
from typing import Dict
from collections import defaultdict
from fastapi import Request, HTTPException, status as http_status
from itsdangerous import URLSafeTimedSerializer
from app.config import settings

# Session serializer for secure cookies
serializer = URLSafeTimedSerializer(settings.jwt_secret_key)

# Rate limiting for login attempts
login_attempts: Dict[str, list] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_PERIOD = 900  # 15 minutes in seconds


def get_session_data(request: Request) -> dict:
    """Extract session data from request."""
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        return {}

    try:
        return serializer.loads(session_cookie, max_age=7200)  # 2 hours
    except (Exception,):
        return {}


def create_session_cookie(data: dict) -> str:
    """Create a signed session cookie."""
    return serializer.dumps(data)


def check_rate_limit(identifier: str) -> bool:
    """
    Check if the identifier (IP/username) has exceeded rate limit.

    Returns True if request is allowed, False if rate limited.
    """
    now = datetime.utcnow()
    cutoff_time = now - timedelta(seconds=LOCKOUT_PERIOD)

    # Remove old attempts
    login_attempts[identifier] = [
        attempt_time for attempt_time in login_attempts[identifier]
        if attempt_time > cutoff_time
    ]

    # Check if rate limited
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        return False

    # Record this attempt
    login_attempts[identifier].append(now)
    return True


def require_admin(request: Request):
    """Dependency to require admin authentication."""
    session = get_session_data(request)
    if not session.get("admin_id"):
        raise HTTPException(
            status_code=http_status.HTTP_302_FOUND,
            headers={"Location": "/admin/login"}
        )
    return session
