# FastAPI SMTP Proxy - Setup Guide

## Initial Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

**Required Configuration:**

Generate an encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Update `.env` with:
```bash
# JWT Settings
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# Encryption Settings (for SMTP passwords)
ENCRYPTION_KEY=your-generated-fernet-key-here

# CORS (comma-separated list of allowed origins)
CORS_ORIGINS=http://localhost:8000,https://yourdomain.com

# Database
DATABASE_URL=sqlite+aiosqlite:///./smtp_proxy.db

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=false
```

### 3. Initialize Database

The database will be automatically initialized on first run. Alternatively, you can manually initialize it:

```bash
python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

### 4. Create Admin User

**IMPORTANT:** You must create an admin user before accessing the dashboard.

```bash
python manage.py create-admin
```

You'll be prompted for:
- Username
- Email
- Full Name (optional)
- Password
- Confirm Password
- Superuser status (y/N)

**Default Admin (for testing only):**
If you want a quick default admin for testing:
- Username: `admin`
- Password: `admin`

⚠️ **Security Warning:** Change the default password immediately after first login!

### 5. Start the Application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or for production:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Post-Setup

### Access the Dashboard

Navigate to: `http://localhost:8000/admin/login`

Login with your admin credentials.

### Create Clients

Clients represent SMTP configurations. You can create them via:

1. **Dashboard:** `/admin/clients/new`
2. **CLI:** `python manage.py create-client`
3. **API:** `POST /api/admin/clients` (requires HTTP Basic Auth)

### Generate API Keys

API keys allow clients to send emails through the proxy:

1. **Dashboard:** Navigate to client detail page → "Manage API Keys"
2. **CLI:** `python manage.py create-api-key`
3. **API:** `POST /api/admin/clients/{client_id}/api-keys` (requires HTTP Basic Auth)

⚠️ **Important:** API keys are only shown once during creation. Save them securely!

### Send Test Email

```bash
python example_test_email.py
```

Or use curl:

```bash
curl -X POST http://localhost:8000/send \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-jwt-token-here" \
  -d '{
    "to": ["recipient@example.com"],
    "subject": "Test Email",
    "content": "<h1>Hello World</h1>",
    "from": "sender@example.com",
    "from_name": "Test Sender",
    "timestamp": '$(date +%s)',
    "content_type": "text/html"
  }'
```

## Management CLI Commands

### Admin Management

```bash
# Create admin user
python manage.py create-admin

# List admin users
python manage.py list-admins
```

### Client Management

```bash
# Create client
python manage.py create-client

# List clients
python manage.py list-clients
```

### API Key Management

```bash
# Create API key
python manage.py create-api-key

# List API keys
python manage.py list-api-keys
```

### Analytics

```bash
# Create analytics snapshot
python manage.py create-snapshot

# Show analytics summary
python manage.py show-analytics

# Rotate old quarterly data
python manage.py rotate-data
```

## Security Features

### Password Encryption

SMTP passwords are encrypted at rest using Fernet (AES-128 CBC) encryption. They are only decrypted when needed for SMTP connections.

If upgrading from a version without encryption, run the migration:

```bash
python migrate_encrypt_passwords.py
```

### Authentication

- **Dashboard:** Session-based authentication with secure cookies
- **Admin API:** HTTP Basic Authentication
- **Client API:** JWT-based API key authentication

### Rate Limiting

Login attempts are limited to 5 attempts per 15 minutes per IP+username combination.

### Security Headers

All responses include comprehensive security headers:
- Content Security Policy (CSP)
- X-Frame-Options
- HSTS (in production)
- X-Content-Type-Options
- Referrer-Policy
- Permissions-Policy

### CORS

CORS is restricted to specific origins defined in `CORS_ORIGINS` environment variable.

## Production Deployment

### Prerequisites

1. Use a production-grade database (PostgreSQL recommended)
2. Set strong, unique secrets for JWT_SECRET_KEY and ENCRYPTION_KEY
3. Configure CORS for your domain(s)
4. Use HTTPS (required for secure cookies)
5. Set DEBUG=false
6. Use a reverse proxy (nginx, traefik) with rate limiting

### Environment Variables

```bash
# Production settings
DEBUG=false
JWT_SECRET_KEY=<64+ character random string>
ENCRYPTION_KEY=<Fernet key>
CORS_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com

# Database (PostgreSQL example)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/smtp_proxy

# Server
HOST=0.0.0.0
PORT=8000
```

### Running with Systemd

Create `/etc/systemd/system/smtp-proxy.service`:

```ini
[Unit]
Description=FastAPI SMTP Proxy
After=network.target

[Service]
Type=notify
User=smtp-proxy
Group=smtp-proxy
WorkingDirectory=/opt/smtp-proxy
Environment="PATH=/opt/smtp-proxy/venv/bin"
ExecStart=/opt/smtp-proxy/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable smtp-proxy
sudo systemctl start smtp-proxy
```

### Docker (Alternative)

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:

```bash
docker build -t smtp-proxy .
docker run -d -p 8000:8000 --env-file .env smtp-proxy
```

## Troubleshooting

### Login Error: "UnknownHashError"

**Cause:** No admin user exists in the database.

**Solution:**
```bash
python manage.py create-admin
```

### SMTP Connection Errors

**Cause:** Incorrect SMTP credentials or encryption issues.

**Check:**
1. Verify SMTP credentials in client configuration
2. Ensure ENCRYPTION_KEY is set in .env
3. Check if SMTP password was encrypted (should not be plaintext)
4. Test SMTP credentials directly with an SMTP client

### Database Locked Errors

**Cause:** SQLite doesn't handle high concurrency well.

**Solution:** Upgrade to PostgreSQL for production:

```bash
# Install PostgreSQL driver
pip install asyncpg

# Update DATABASE_URL
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/smtp_proxy
```

### CORS Errors

**Cause:** Frontend domain not in CORS_ORIGINS.

**Solution:** Add your domain to .env:
```bash
CORS_ORIGINS=https://yourdomain.com,https://admin.yourdomain.com
```

## Monitoring

### Log Levels

Set log level via environment:

```bash
export LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

### Analytics Dashboard

Access comprehensive analytics at `/admin/analytics`:
- Email volume trends
- Success rates
- Performance metrics
- Error analysis

## Support

For issues, bugs, or feature requests:
- Check documentation: `SECURITY_AUDIT.md`, `SECURITY_FIXES_APPLIED.md`
- Review logs for error details
- Ensure all environment variables are properly configured

## License

[Your License Here]
