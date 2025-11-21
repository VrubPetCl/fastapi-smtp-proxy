# Claude Session Context - FastAPI SMTP Proxy

**Last Updated**: 2025-11-21
**Project Status**: ✅ Production Ready
**Security Rating**: A (Excellent)

---

## Quick Start for New Session

```bash
# Current working directory
cd /home/user/fastapi-smtp-proxy

# Active branch
git branch --show-current
# claude/smtp-proxy-fastapi-01YN4Vw1YuCA7xzhEZ68ibq3

# Start application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access dashboard
# http://localhost:8000/admin/login
# Default credentials: admin / admin

# Management CLI
python manage.py --help
```

---

## Project Overview

### Purpose
Enterprise-grade FastAPI SMTP Proxy that:
- Centralizes SMTP configuration for multiple clients
- Provides JWT-based API authentication
- Tracks comprehensive email analytics
- Offers web dashboard for administration
- Supports email attachments with validation
- Implements industry-standard security

### Tech Stack
- **Framework**: FastAPI 0.115.0 + Starlette 0.38.6
- **Database**: SQLite (async) via SQLAlchemy 2.0 + aiosqlite
- **Email**: aiosmtplib 3.0.2 (async SMTP)
- **Security**:
  - Password hashing: Argon2id (pwdlib 0.2.1)
  - SMTP encryption: Fernet (cryptography 41.0.7)
  - JWT tokens: HS256 algorithm
- **Validation**: Pydantic 2.9.2
- **Frontend**: Jinja2 templates + Tailwind CSS (CDN)

### Architecture
```
┌─────────────┐
│   Client    │──┐
│ Application │  │
└─────────────┘  │
                 ├──> JWT Auth ──> FastAPI SMTP Proxy ──> SMTP Server
┌─────────────┐  │                       │
│   Admin     │──┘                       │
│  Dashboard  │                          ▼
└─────────────┘                     Analytics DB
```

---

## Critical Files & Structure

### Core Application
```
app/
├── main.py              # FastAPI app, API endpoints, middleware
├── web.py               # Dashboard routes, admin UI endpoints
├── auth.py              # JWT authentication for API clients
├── web_auth.py          # Session auth for dashboard (Argon2id)
├── models.py            # Pydantic models (EmailRequest, AttachmentModel)
├── schemas.py           # SQLAlchemy ORM models (Client, APIKey, EmailLog)
├── smtp_service.py      # SMTP sending logic, attachment handling
├── encryption.py        # Fernet encryption for SMTP passwords
├── analytics_service.py # Analytics calculations, quarterly rotation
├── database.py          # Async database connection
└── config.py            # Pydantic settings (from .env)

templates/               # Jinja2 templates for dashboard
├── base.html           # Base template with Tailwind CDN
├── login.html          # Login page
├── dashboard.html      # Main dashboard
├── client_*.html       # Client management pages
├── analytics.html      # Analytics dashboard
└── ...

manage.py               # CLI for admin/client/key management
migrate_encrypt_passwords.py  # One-time password encryption migration
```

### Configuration Files
```
.env                    # Environment variables (NOT in git)
.env.example            # Template for environment setup
requirements.txt        # Python dependencies
```

### Documentation
```
README.md                            # Project README
SETUP_GUIDE.md                       # Complete setup instructions
SECURITY_ASSESSMENT_2025-11-21.md    # Comprehensive security audit
SECURITY_FIXES_APPLIED.md            # Previous security fixes
SECURITY_AUDIT.md                    # Initial vulnerability assessment
ATTACHMENTS.md                       # Attachment handling guide
TEST_EMAIL_FEATURE.md                # Test email documentation
FINAL_SECURITY_SUMMARY.md            # Security implementation summary
DASHBOARD_ROUTES_AUDIT.md            # Dashboard routes documentation
claude.md                            # This file (session context)
```

---

## Database Schema

### Key Tables

**clients** - SMTP client configurations
```sql
id, name, smtp_host, smtp_port, smtp_username,
smtp_password (encrypted), smtp_use_tls, smtp_use_ssl,
default_from_email, default_from_name, is_active, created_at
```

**api_keys** - JWT tokens for client authentication
```sql
id, client_id, name, key_hash, created_at,
last_used_at, expires_at, is_active
```

**email_logs** - Comprehensive email tracking
```sql
id, client_id, api_key_id, to_addresses, subject,
status, error_message, attachment_count,
total_attachment_size, processing_time_ms,
sent_at, year, quarter, month, hour
```

**admin_users** - Dashboard administrators
```sql
id, username, email, password_hash (Argon2id),
full_name, is_active, is_superuser, last_login_at
```

**analytics_snapshots** - Quarterly aggregated metrics
```sql
id, client_id, year, quarter, total_emails,
success_rate, avg_processing_time_ms, etc.
```

---

## Authentication & Authorization

### Dashboard (Session-Based)
- **Login**: `/admin/login` (POST username + password)
- **Session**: Cookie-based, 2-hour timeout
- **Security**: HttpOnly, Secure, SameSite=lax
- **Rate Limiting**: 5 attempts per 15 minutes
- **Protection**: All `/admin/*` routes require session

### API Clients (JWT)
- **Header**: `X-API-Key: <jwt-token>`
- **Generation**: Dashboard or `python manage.py create-api-key`
- **Expiration**: 720 hours (30 days)
- **Storage**: Hash stored in database
- **Validation**: On every API request

### Admin API (HTTP Basic Auth)
- **Header**: `Authorization: Basic <base64(username:password)>`
- **Routes**: `/api/admin/*` endpoints
- **Password**: Verified against Argon2id hash
- **Use Case**: External API access for admin operations

---

## API Endpoints

### Client Email Sending

```http
POST /api/send
X-API-Key: <jwt-token>
Content-Type: application/json

{
  "to": ["recipient@example.com"],
  "subject": "Test Email",
  "content": "<h1>Hello</h1>",
  "from": "sender@example.com",
  "timestamp": 1700000000,
  "attachments": [
    {
      "filename": "invoice.pdf",
      "content": "base64_encoded_content",
      "content_type": "application/pdf"
    }
  ]
}
```

### Admin API (all require HTTP Basic Auth)

```http
POST   /api/admin/clients              # Create client
GET    /api/admin/clients              # List clients
GET    /api/admin/clients/{id}         # Get client
PUT    /api/admin/clients/{id}         # Update client
DELETE /api/admin/clients/{id}         # Delete client
POST   /api/admin/clients/{id}/api-keys   # Create API key
GET    /api/admin/clients/{id}/api-keys   # List API keys
DELETE /api/admin/api-keys/{id}        # Revoke API key
GET    /api/admin/analytics            # Global analytics
GET    /api/admin/clients/{id}/analytics # Client analytics
```

### Dashboard Routes (all require session)

```http
GET  /admin/login                      # Login page
POST /admin/login                      # Login handler
GET  /admin/logout                     # Logout
GET  /admin/dashboard                  # Main dashboard
GET  /admin/clients                    # Client list
GET  /admin/clients/new                # New client form
POST /admin/clients/new                # Create client
GET  /admin/clients/{id}               # Client detail
GET  /admin/clients/{id}/edit          # Edit form
POST /admin/clients/{id}/edit          # Update client
POST /admin/clients/{id}/delete        # Delete client
POST /admin/clients/{id}/test-email    # Send test email
GET  /admin/clients/{id}/keys          # API key management
POST /admin/clients/{id}/keys/new      # Generate API key
POST /admin/clients/{id}/keys/{key_id}/revoke  # Revoke key
GET  /admin/analytics                  # Analytics dashboard
```

### Public Endpoints

```http
GET /           # API info
GET /health     # Health check
```

---

## Security Features (Rating: A)

### ✅ Implemented

1. **Authentication**
   - All sensitive endpoints protected
   - JWT for API, Sessions for dashboard, Basic Auth for admin API
   - Rate limiting: 5 login attempts per 15 minutes

2. **Encryption & Hashing**
   - Passwords: Argon2id (OWASP recommended)
   - SMTP passwords: Fernet (AES-128 CBC)
   - JWT tokens: HS256 signed

3. **Security Headers**
   - X-Frame-Options: DENY
   - Content-Security-Policy
   - Strict-Transport-Security (production)
   - X-Content-Type-Options: nosniff
   - X-XSS-Protection

4. **Session Security**
   - HttpOnly cookies (XSS protection)
   - Secure flag (HTTPS only)
   - SameSite=lax (CSRF protection)
   - 2-hour timeout

5. **Input Validation**
   - Pydantic models with strict typing
   - EmailStr for email validation
   - Length limits on all fields
   - Attachment size limits (25MB per file, 50MB total)
   - Filename sanitization (no path traversal)
   - Content type whitelist

6. **CORS**
   - Restricted to specific origins (env variable)
   - No wildcards
   - Limited methods and headers

7. **Error Handling**
   - Sanitized error messages
   - No stack traces in production
   - Detailed logging server-side only

### ⚠️ Production Checklist

```bash
# 1. Set strong secrets
JWT_SECRET_KEY=<64+ character random string>
ENCRYPTION_KEY=<Fernet key>

# 2. Disable debug
DEBUG=false

# 3. Configure CORS
CORS_ORIGINS=https://yourdomain.com

# 4. Use HTTPS (reverse proxy)

# 5. Change default admin password
python manage.py create-admin
```

---

## Key Features

### ✅ Implemented Features

1. **Email Sending**
   - Multiple recipients (to, cc, bcc)
   - HTML and plain text content
   - Custom headers
   - Reply-to support
   - Attachments (base64 encoded)
   - Size validation (25MB per file, 50MB total)
   - Content type validation

2. **Client Management**
   - CRUD operations via dashboard
   - SMTP configuration (TLS/SSL support)
   - API key generation
   - Active/inactive status
   - Default from email/name

3. **Analytics**
   - Email volume tracking
   - Success/failure rates
   - Performance metrics (processing time, SMTP connection time)
   - Hourly/daily distribution
   - Error analysis
   - Quarterly data rotation
   - Attachment statistics

4. **Dashboard**
   - Clean UI with Tailwind CSS
   - Real-time statistics
   - Client management
   - API key management
   - Analytics visualization
   - Test email feature (with attachments)

5. **Test Email Feature**
   - Modal UI for quick testing
   - Email input (pre-populated with admin email)
   - File attachment support
   - Real-time log display
   - Success/error indicators
   - Configuration details in email

6. **Management CLI**
   ```bash
   python manage.py create-admin     # Create admin user
   python manage.py list-admins      # List admins
   python manage.py create-client    # Create SMTP client
   python manage.py list-clients     # List clients
   python manage.py create-api-key   # Generate API key
   python manage.py list-api-keys    # List API keys
   python manage.py create-snapshot  # Create analytics snapshot
   python manage.py show-analytics   # View analytics
   python manage.py rotate-data      # Rotate quarterly data
   ```

---

## Recent Changes (Session History)

### Latest Session (2025-11-21)

1. **Security Assessment & Fix**
   - Conducted comprehensive security audit
   - Fixed: Password reset token logging (HIGH severity)
   - Rating: A (Excellent) - Production ready
   - Created: `SECURITY_ASSESSMENT_2025-11-21.md`

2. **Test Email Feature Enhancement**
   - Added file attachment support to test email modal
   - File size validation (25MB limit)
   - Supported file types: PDF, Word, Excel, Images, ZIP
   - Real-time file info display
   - Progress indication

3. **Attachment Validation Enhancement**
   - Created `AttachmentModel` with Pydantic validation
   - Base64 content validation
   - Filename sanitization (prevent path traversal)
   - Content type whitelist
   - Individual file size limit: 25MB
   - Total attachment size limit: 50MB
   - Created: `ATTACHMENTS.md` (comprehensive guide)

4. **Session Continuity**
   - Created: `claude.md` (this file)
   - Complete project context for future sessions

### Previous Sessions

1. **Dashboard Routes Implementation**
   - Fixed 7 missing dashboard routes
   - Created client management templates
   - Implemented API key management UI
   - Added client detail pages with statistics

2. **Analytics Dashboard**
   - Full analytics implementation
   - Date range filtering
   - Client filtering
   - Performance metrics
   - Error analysis
   - Quarterly data rotation

3. **Security Implementation**
   - HTTP Basic Auth on admin API endpoints
   - Secure session cookies
   - Rate limiting on login
   - Security headers middleware
   - SMTP password encryption (Fernet)
   - CORS restrictions

4. **Client Form Fixes**
   - Fixed TLS/SSL checkbox persistence
   - Fixed default from email/name fields
   - Added SSL option (in addition to TLS)
   - Field name alignment with database schema

---

## Known Issues & TODOs

### ✅ No Critical Issues

All critical security issues have been resolved.

### 🔵 Optional Enhancements (Future)

1. **Rate Limiting on API Endpoints**
   - Current: Login rate limiting only
   - Consider: Email sending rate limits per client
   - Tool: slowapi or similar

2. **Session Storage**
   - Current: In-memory dict (fine for small scale)
   - Consider: Redis for production scalability
   - Benefit: Session persistence across restarts

3. **Email Templates**
   - Current: HTML/text content in request
   - Consider: Template management system
   - Benefit: Reusable templates

4. **Webhook Support**
   - Current: Synchronous email sending
   - Consider: Webhook callbacks for delivery status
   - Benefit: Async status updates

5. **Multi-language Support**
   - Current: English only
   - Consider: i18n for dashboard
   - Benefit: International users

6. **Email Scheduling**
   - Current: Immediate sending only
   - Consider: Scheduled sending feature
   - Benefit: Timed campaigns

7. **Bounce Handling**
   - Current: No bounce tracking
   - Consider: Parse bounce emails
   - Benefit: Email list hygiene

---

## Environment Variables

### Required

```bash
# Core
JWT_SECRET_KEY=<64+ character random string>
ENCRYPTION_KEY=<Fernet key from setup>

# Database
DATABASE_URL=sqlite+aiosqlite:///./smtp_proxy.db

# Security
DEBUG=false
CORS_ORIGINS=http://localhost:8000,https://yourdomain.com
```

### Optional

```bash
# Application
APP_NAME="FastAPI SMTP Proxy"
APP_VERSION="1.0.0"

# JWT
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=720

# Server
HOST=0.0.0.0
PORT=8000
```

### Generating Secrets

```bash
# JWT Secret
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Encryption Key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Common Workflows

### Adding a New Feature

1. **Update models** (`app/models.py` or `app/schemas.py`)
2. **Create/update endpoints** (`app/main.py` or `app/web.py`)
3. **Add tests** (if implementing)
4. **Update documentation**
5. **Test thoroughly**
6. **Security review**
7. **Commit with clear message**

### Fixing a Bug

1. **Reproduce the issue**
2. **Check logs** (`logger.error()` statements)
3. **Identify root cause**
4. **Fix and test**
5. **Add validation to prevent recurrence**
6. **Document in commit message**

### Adding a Dashboard Page

1. **Create template** in `app/templates/`
2. **Add route** in `app/web.py`
3. **Use `@router.get()` or `@router.post()`**
4. **Add `session: dict = Depends(require_admin)`** for auth
5. **Return** `templates.TemplateResponse()`
6. **Link from navigation** in `base.html`

### Creating API Endpoint

1. **Add route** in `app/main.py`
2. **Define Pydantic models** in `app/models.py`
3. **Add authentication**:
   - Client API: `Depends(get_current_client)`
   - Admin API: `Depends(get_admin_user)`
4. **Implement logic**
5. **Return appropriate response**
6. **Document in `claude.md`**

---

## Testing Checklist

### Manual Testing

```bash
# 1. Start application
uvicorn app.main:app --reload

# 2. Test dashboard
# - Login: http://localhost:8000/admin/login
# - Create client
# - Generate API key
# - Send test email (with attachment)
# - View analytics

# 3. Test API
curl -X POST http://localhost:8000/api/send \
  -H "X-API-Key: your-jwt-token" \
  -H "Content-Type: application/json" \
  -d @test_email.json

# 4. Check logs
# - No errors in console
# - Email sent successfully
# - Analytics updated
```

### Security Testing

```bash
# 1. Verify authentication
curl http://localhost:8000/api/admin/clients
# Should return 401 Unauthorized

# 2. Test rate limiting
# Try logging in 6 times with wrong password
# 6th attempt should return 429 Too Many Requests

# 3. Check headers
curl -I http://localhost:8000/admin/dashboard
# Should include X-Frame-Options, CSP, etc.

# 4. Test CORS
curl -H "Origin: http://evil.com" http://localhost:8000/api/send
# Should be blocked
```

---

## Debugging Tips

### Common Issues

1. **"Module not found" error**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **"No admin users found"**
   ```bash
   # Create admin user
   python manage.py create-admin
   ```

3. **"Failed to decrypt SMTP password"**
   ```bash
   # Check ENCRYPTION_KEY in .env
   # Run migration if upgrading
   python migrate_encrypt_passwords.py
   ```

4. **SMTP authentication failed**
   - Check username/password
   - Verify TLS/SSL settings
   - Test with different port
   - Check SMTP provider requirements (app passwords?)

5. **Session expired immediately**
   - Check cookie settings
   - Verify HTTPS in production
   - Check system clock

### Logging

```python
# Add debug logging
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Variable value: {variable}")
logger.info(f"Action completed: {action}")
logger.warning(f"Potential issue: {issue}")
logger.error(f"Error occurred: {error}")
```

---

## Database Management

### Backup

```bash
# Backup database
cp smtp_proxy.db smtp_proxy_backup_$(date +%Y%m%d).db

# Or use SQLite command
sqlite3 smtp_proxy.db ".backup smtp_proxy_backup.db"
```

### Migrations

```bash
# Currently no migration system
# To add Alembic:
pip install alembic
alembic init migrations
# Configure alembic.ini and env.py
```

### Direct Database Access

```bash
# SQLite command line
sqlite3 smtp_proxy.db

# Useful queries
.tables                          # List tables
.schema clients                  # Show table schema
SELECT * FROM admin_users;       # Query data
.quit                            # Exit
```

---

## Git Workflow

### Current Branch

```bash
# Branch name
claude/smtp-proxy-fastapi-01YN4Vw1YuCA7xzhEZ68ibq3

# Check status
git status

# View history
git log --oneline -10
```

### Commit Guidelines

```bash
# Good commit message format:
git commit -m "Add feature: description

- Bullet point 1
- Bullet point 2
- Bullet point 3

Fixes #issue-number"

# Examples:
# - "Add test email attachment support"
# - "Fix client form field persistence"
# - "Security: Remove token from logs"
```

### Push Changes

```bash
# Push to branch
git push -u origin claude/smtp-proxy-fastapi-01YN4Vw1YuCA7xzhEZ68ibq3

# With retry on network errors
git push || sleep 2 && git push || sleep 4 && git push
```

---

## Project Context for AI Assistants

### When Starting New Session

1. **Read this file first** (`claude.md`)
2. **Check recent commits**: `git log --oneline -5`
3. **Review open files**: Check what user is viewing
4. **Understand current state**: Production ready, security reviewed
5. **Check for TODOs**: See "Known Issues & TODOs" section

### Communication Style

- **Be concise but complete**
- **Use code blocks** for examples
- **Provide file paths** with line numbers
- **Explain "why" not just "what"**
- **Security-conscious**: Always consider security implications
- **Production-ready mindset**: Write production-quality code

### Best Practices

1. **Always validate input** using Pydantic
2. **Use async/await** consistently
3. **Log important actions** with appropriate levels
4. **Handle errors gracefully** with try/except
5. **Document complex logic** with comments
6. **Write secure code** by default
7. **Test changes** before committing

---

## Quick Reference

### Important Commands

```bash
# Start app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Create admin
python manage.py create-admin

# List everything
python manage.py list-admins
python manage.py list-clients
python manage.py list-api-keys

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Database backup
cp smtp_proxy.db smtp_proxy_backup.db

# Check dependencies
pip list | grep -E "fastapi|pydantic|sqlalchemy"

# View logs (if using systemd)
journalctl -u smtp-proxy -f
```

### Important URLs

```
Dashboard:  http://localhost:8000/admin/login
API Docs:   http://localhost:8000/docs
Health:     http://localhost:8000/health
```

### File Locations

```
Database:       ./smtp_proxy.db
Logs:           stdout/stderr (or systemd journal)
Templates:      ./app/templates/
Static files:   None (using Tailwind CDN)
Config:         ./.env
```

---

## Resources & References

### Documentation Files
- `SETUP_GUIDE.md` - Complete setup and deployment guide
- `SECURITY_ASSESSMENT_2025-11-21.md` - Security audit report
- `ATTACHMENTS.md` - Attachment handling guide
- `TEST_EMAIL_FEATURE.md` - Test email feature documentation

### External Resources
- FastAPI docs: https://fastapi.tiangolo.com/
- Pydantic docs: https://docs.pydantic.dev/
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- Argon2 info: https://www.argon2.com/
- OWASP Top 10: https://owasp.org/Top10/

---

## Contact & Support

### For Issues
1. Check documentation in this repo
2. Review security assessment
3. Check logs for errors
4. Test with minimal configuration
5. Review recent commits for breaking changes

### For Enhancements
1. Review "Known Issues & TODOs" section
2. Check security implications
3. Update relevant documentation
4. Test thoroughly
5. Commit with clear description

---

**End of Claude Session Context**

*This file should be updated whenever significant changes are made to the project.*
*Last comprehensive update: 2025-11-21*
