# Security Audit Report
## FastAPI SMTP Proxy - Admin Dashboard & API Security Analysis

**Date**: 2025-11-21
**Status**: 🔴 **CRITICAL VULNERABILITIES FOUND**

---

## Executive Summary

The admin dashboard has **basic session authentication** but contains **multiple critical security vulnerabilities** that could allow unauthorized access, information disclosure, and abuse. The **API admin endpoints (`/api/admin/*`) have NO authentication at all**, making them completely exposed.

**Risk Level**: 🔴 **CRITICAL** - Not production-ready

---

## Critical Vulnerabilities

### 1. 🔴 **CRITICAL: Unprotected Admin API Endpoints**

**Location**: `app/main.py:196-607`

**Issue**: ALL `/api/admin/*` endpoints have NO authentication:
- `/api/admin/clients` (POST, GET)
- `/api/admin/clients/{id}` (GET)
- `/api/admin/api-keys` (POST, GET, DELETE)
- `/api/admin/analytics/*` (GET, POST)

**Code Evidence**:
```python
@app.post("/api/admin/clients", ...)
async def create_client(
    client_data: ClientCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    In production, this should be protected with admin authentication.
    """
    # NO AUTH CHECK!
```

**Impact**:
- Anyone can create/read/delete clients
- Anyone can create/revoke API keys
- Anyone can access analytics for all clients
- Complete system compromise possible

**Exploitation**:
```bash
# Anyone can do this without authentication:
curl -X POST http://yourserver/api/admin/clients \
  -H "Content-Type: application/json" \
  -d '{"name":"hacker","smtp_host":"evil.com", ...}'

curl http://yourserver/api/admin/clients  # List all clients
```

**Fix Priority**: 🔴 **IMMEDIATE**

---

### 2. 🔴 **CRITICAL: Insecure Session Cookies**

**Location**: `app/web.py:37-39, 67-107`

**Issues**:
- No `HttpOnly` flag (vulnerable to XSS)
- No `Secure` flag (vulnerable to MITM)
- No `SameSite` attribute (vulnerable to CSRF)
- Bare `except:` catches all exceptions (line 33)

**Code Evidence**:
```python
def create_session_cookie(data: dict) -> str:
    """Create a signed session cookie."""
    return serializer.dumps(data)  # Returns string, no cookie attributes

# In login POST:
response.set_cookie(
    key="session",
    value=session_cookie,
    # MISSING: httponly=True, secure=True, samesite='Lax'
)
```

**Impact**:
- JavaScript can read admin sessions (XSS → full compromise)
- Sessions transmitted over HTTP in plaintext
- CSRF attacks possible

**Fix Priority**: 🔴 **IMMEDIATE**

---

### 3. 🟠 **HIGH: No Brute Force Protection**

**Location**: `app/web.py:67-107`, `app/web_auth.py:24-57`

**Issues**:
- No rate limiting on login attempts
- No account lockout after failed logins
- No CAPTCHA or similar protection
- No failed login logging
- No IP-based blocking

**Impact**:
- Attackers can brute force admin passwords
- Credential stuffing attacks
- No visibility into attack attempts

**Exploitation**:
```bash
# Unlimited login attempts possible:
for password in wordlist; do
  curl -X POST http://yourserver/admin/login \
    -d "username=admin&password=$password"
done
```

**Fix Priority**: 🟠 **HIGH**

---

### 4. 🟠 **HIGH: Missing Security Headers**

**Location**: `app/main.py` (no security middleware)

**Missing Headers**:
- `Content-Security-Policy` (XSS protection)
- `X-Frame-Options` (clickjacking protection)
- `X-Content-Type-Options: nosniff` (MIME sniffing protection)
- `Strict-Transport-Security` (HTTPS enforcement)
- `Referrer-Policy` (info leakage)
- `Permissions-Policy` (feature restrictions)

**Impact**:
- XSS attacks more effective
- Clickjacking possible
- MIME confusion attacks
- No HTTPS enforcement

**Fix Priority**: 🟠 **HIGH**

---

### 5. 🟠 **HIGH: Plaintext SMTP Passwords**

**Location**: `app/schemas.py:15-32`, `app/main.py:228`

**Issue**: SMTP passwords stored in database in plaintext

**Code Evidence**:
```python
smtp_password = Column(String(255), nullable=False)  # Plaintext!

# Comment acknowledges the issue:
smtp_password=client_data.smtp_password,  # TODO: Encrypt in production
```

**Impact**:
- Database dump exposes all SMTP credentials
- Insider threat
- Compliance violations (PCI-DSS, GDPR)

**Fix Priority**: 🟠 **HIGH**

---

### 6. 🟡 **MEDIUM: Overly Permissive CORS**

**Location**: `app/main.py:62-68`

**Issue**: CORS allows all origins

**Code**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows ANY website!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Impact**:
- Any website can make authenticated requests
- CSRF attacks easier
- Credential theft

**Fix Priority**: 🟡 **MEDIUM**

---

### 7. 🟡 **MEDIUM: No CSRF Protection**

**Location**: `app/templates/*.html` (all forms), `app/web.py`

**Issues**:
- No CSRF tokens in forms
- No CSRF token validation
- Session cookies without `SameSite` attribute

**Affected Forms**:
- Login form
- Client creation/editing
- API key generation
- Password reset

**Impact**:
- Attackers can perform actions on behalf of logged-in admins
- Unauthorized client creation/deletion
- API key generation/revocation

**Fix Priority**: 🟡 **MEDIUM**

---

### 8. 🟡 **MEDIUM: Information Disclosure**

**Location**: Multiple locations

**Issues**:

**a) Error Messages** (`app/main.py:184-189`):
```python
except Exception as e:
    logger.error(f"Unexpected error: {str(e)}")
    raise HTTPException(
        detail={"error": str(e)}  # Leaks exception details
    )
```

**b) Debug Mode**:
- Stack traces exposed when `DEBUG=True`
- Detailed error pages

**c) Password Reset Tokens in URL** (`app/web.py:152-220`):
```python
@router.get("/admin/reset-password/{token}")  # Token in URL!
```

**Impact**:
- Internal paths, database structure exposed
- Tokens logged in server logs, proxy logs, browser history
- Information useful for further attacks

**Fix Priority**: 🟡 **MEDIUM**

---

### 9. 🟡 **MEDIUM: Long Session Timeouts**

**Location**: `app/web.py:32`

**Issue**: 7-day session timeout for admin sessions

**Code**:
```python
return serializer.loads(session_cookie, max_age=86400 * 7)  # 7 days!
```

**Impact**:
- Stolen sessions valid for a week
- Forgotten logouts on shared computers
- Larger attack window

**Recommendation**: Reduce to 1-2 hours with "remember me" option

**Fix Priority**: 🟡 **MEDIUM**

---

### 10. ⚪ **LOW: No HTTPS Enforcement**

**Location**: `app/main.py`, `app/config.py`

**Issue**: No redirect from HTTP to HTTPS, no HSTS header

**Impact**:
- Man-in-the-middle attacks
- Session hijacking
- Credential theft

**Note**: Should be handled at reverse proxy level (Nginx/Caddy)

**Fix Priority**: ⚪ **LOW** (if using reverse proxy)

---

## Security Best Practices Violations

### Authentication & Authorization
- ❌ No authentication on admin API endpoints
- ❌ No rate limiting
- ❌ No account lockout
- ❌ No multi-factor authentication (MFA)
- ❌ No password complexity requirements
- ✅ Strong password hashing (Argon2id)
- ✅ Session-based auth for web dashboard

### Session Management
- ❌ Missing HttpOnly, Secure, SameSite flags
- ❌ Long session timeouts
- ❌ Bare exception handling
- ✅ Signed cookies (itsdangerous)
- ✅ Session expiration

### Input Validation
- ⚠️ Basic validation via Pydantic
- ❌ No SQL injection protection on raw queries (none found, but...)
- ✅ Parameterized queries via SQLAlchemy

### Cryptography
- ✅ Argon2id for passwords
- ❌ SMTP passwords in plaintext
- ❌ API keys not hashed (stored as plaintext in web dashboard)

### Logging & Monitoring
- ⚠️ Basic logging present
- ❌ No failed login logging
- ❌ No security event logging
- ❌ No alerting

---

## Recommended Fixes (Priority Order)

### 🔴 IMMEDIATE (Critical - Fix before ANY production use)

1. **Add Authentication to Admin API Endpoints**
   ```python
   from app.auth import get_admin_user  # Create this

   @app.post("/api/admin/clients", ...)
   async def create_client(
       client_data: ClientCreate,
       admin: AdminUser = Depends(get_admin_user),  # ADD THIS
       db: AsyncSession = Depends(get_db),
   ):
   ```

2. **Secure Session Cookies**
   ```python
   response.set_cookie(
       key="session",
       value=session_cookie,
       httponly=True,      # Prevent JavaScript access
       secure=True,        # HTTPS only
       samesite='Lax',     # CSRF protection
       max_age=7200,       # 2 hours (not 7 days)
   )
   ```

3. **Fix Bare Exception Clause**
   ```python
   try:
       return serializer.loads(session_cookie, max_age=86400 * 7)
   except (BadSignature, SignatureExpired):  # Specific exceptions
       return {}
   ```

### 🟠 HIGH (Fix within days)

4. **Implement Rate Limiting**
   ```python
   from slowapi import Limiter, _rate_limit_exceeded_handler
   from slowapi.util import get_remote_address

   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter

   @router.post("/admin/login")
   @limiter.limit("5/minute")  # 5 attempts per minute
   async def login(...):
   ```

5. **Add Security Headers Middleware**
   ```python
   @app.middleware("http")
   async def security_headers(request: Request, call_next):
       response = await call_next(request)
       response.headers["X-Frame-Options"] = "DENY"
       response.headers["X-Content-Type-Options"] = "nosniff"
       response.headers["Content-Security-Policy"] = "default-src 'self'"
       response.headers["Strict-Transport-Security"] = "max-age=31536000"
       return response
   ```

6. **Encrypt SMTP Passwords**
   ```python
   from cryptography.fernet import Fernet

   # Encrypt before storing
   def encrypt_password(plaintext: str) -> str:
       f = Fernet(settings.encryption_key)
       return f.encrypt(plaintext.encode()).decode()
   ```

### 🟡 MEDIUM (Fix within weeks)

7. **Add CSRF Protection**
   ```python
   from starlette_csrf import CSRFMiddleware

   app.add_middleware(
       CSRFMiddleware,
       secret=settings.csrf_secret,
       cookie_name="csrf_token"
   )
   ```

8. **Restrict CORS**
   ```python
   allow_origins=[
       "https://yourdomain.com",
       "https://admin.yourdomain.com"
   ]
   ```

9. **Improve Error Handling**
   ```python
   except Exception as e:
       logger.error(f"Error: {type(e).__name__}")  # Don't leak details
       raise HTTPException(
           status_code=500,
           detail="An internal error occurred"  # Generic message
       )
   ```

10. **Security Logging**
    ```python
    # Log all authentication events
    logger.warning(
        f"Failed login attempt: {username} from {request.client.host}"
    )
    ```

---

## Testing Recommendations

### Manual Security Tests

1. **Try accessing admin API without auth**:
   ```bash
   curl http://localhost:8000/api/admin/clients
   # Should return 401, not data!
   ```

2. **Test session cookie attributes**:
   ```bash
   curl -v http://localhost:8000/admin/login | grep Set-Cookie
   # Should see: HttpOnly; Secure; SameSite=Lax
   ```

3. **Test rate limiting**:
   ```bash
   for i in {1..10}; do
     curl -X POST http://localhost:8000/admin/login \
       -d "username=test&password=wrong"
   done
   # Should get 429 Too Many Requests
   ```

### Automated Security Tools

1. **OWASP ZAP** - Web application security scanner
2. **Burp Suite** - Penetration testing
3. **sqlmap** - SQL injection testing
4. **nmap** - Port scanning
5. **SSL Labs** - TLS configuration testing

---

## Compliance Considerations

**Current Status**:
- ❌ PCI-DSS: Fails (plaintext passwords, no encryption)
- ❌ GDPR: Partial (no audit logs, weak security)
- ❌ SOC 2: Fails (insufficient access controls)
- ❌ ISO 27001: Fails (missing security controls)

---

## Summary

**Current Security Posture**: 🔴 **UNSAFE FOR PRODUCTION**

**Critical Issues**: 3
**High Issues**: 3
**Medium Issues**: 4
**Low Issues**: 1

**Primary Risks**:
1. Complete system compromise via unprotected admin API
2. Admin session hijacking via insecure cookies
3. Brute force attacks on login
4. Credential exposure via plaintext storage

**Minimum Required Fixes for Production**:
- Protect all admin API endpoints with authentication
- Secure session cookies (HttpOnly, Secure, SameSite)
- Implement rate limiting on login
- Add security headers
- Encrypt SMTP passwords

**Estimated Fix Time**: 2-3 days for critical issues
