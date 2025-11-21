# FastAPI SMTP Proxy

A high-performance, FastAPI-based SMTP proxy that allows clients to send emails through preconfigured SMTP connections using JWT-based API authentication. Compatible with [wp-smtp-api](https://github.com/VrubPetCl/wp-smtp-api) request format.

## Features

- **JWT-based Authentication**: Secure API key management using JWT tokens
- **Multi-tenant**: Each client has their own SMTP configuration
- **Multiple API Keys**: One client can have multiple API keys for different applications
- **Email Attachments**: Support for base64-encoded file attachments
- **Async/Await**: Built with async Python for high performance
- **Request Validation**: Comprehensive validation with Pydantic models
- **Email Logging**: Track all sent emails in the database
- **Timestamp Validation**: Prevent replay attacks with timestamp checking
- **Compatible**: Works with wp-smtp-api WordPress plugin format

## Architecture

```
Client (WordPress Plugin)
    ↓ (HTTPS + JWT Bearer Token)
FastAPI SMTP Proxy
    ↓ (Client-specific SMTP configuration)
SMTP Server (Gmail, SendGrid, etc.)
    ↓
Email Recipients
```

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd fastapi-smtp-proxy

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and set your configuration:

```env
# IMPORTANT: Change this to a strong secret key in production!
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# Optional: Adjust other settings
DEBUG=false
DATABASE_URL=sqlite+aiosqlite:///./smtp_proxy.db
HOST=0.0.0.0
PORT=8000
```

### 3. Initialize Database and Create First Client

```bash
# Create a client with SMTP configuration
python manage.py create-client

# Example inputs:
# Client name: My WordPress Site
# SMTP host: smtp.gmail.com
# SMTP port: 587
# SMTP username: your-email@gmail.com
# SMTP password: your-app-password
# Use TLS? [Y/n]: Y
# Use SSL? [y/N]: N
```

### 4. Generate API Key

```bash
# Create an API key for the client
python manage.py create-api-key

# Select the client ID and provide a name
# The JWT token will be displayed - SAVE IT! It won't be shown again.
```

### 5. Start the Server

```bash
# Development mode with auto-reload
python -m uvicorn app.main:app --reload

# Production mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

API Documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Usage

### Sending an Email

**Endpoint:** `POST /api/send`

**Authentication:** Bearer Token (JWT)

**Request Body:**

```json
{
  "to": ["recipient@example.com"],
  "subject": "Test Email",
  "content": "<h1>Hello World</h1><p>This is a test email.</p>",
  "from": "sender@example.com",
  "from_name": "Sender Name",
  "timestamp": 1700000000,
  "content_type": "text/html",
  "reply_to": "reply@example.com",
  "cc": ["cc@example.com"],
  "bcc": ["bcc@example.com"]
}
```

**cURL Example:**

```bash
curl -X POST "http://localhost:8000/api/send" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["recipient@example.com"],
    "subject": "Test Email",
    "content": "<h1>Hello</h1><p>Test email body</p>",
    "timestamp": '$(date +%s)',
    "content_type": "text/html"
  }'
```

**Python Example:**

```python
import requests
import time

url = "http://localhost:8000/api/send"
headers = {
    "Authorization": "Bearer YOUR_JWT_TOKEN",
    "Content-Type": "application/json"
}

data = {
    "to": ["recipient@example.com"],
    "subject": "Test Email from Python",
    "content": "<h1>Hello from Python!</h1>",
    "timestamp": int(time.time()),
    "content_type": "text/html",
    "from": "sender@example.com",
    "from_name": "Python Script"
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

**Response (Success):**

```json
{
  "success": true,
  "message": "Email sent successfully",
  "email_id": "123"
}
```

**Response (Error):**

```json
{
  "success": false,
  "error": "SMTP error: Connection refused",
  "message": "Failed to send email"
}
```

### Sending Email with Attachments

```json
{
  "to": ["recipient@example.com"],
  "subject": "Email with Attachment",
  "content": "Please find the attached file.",
  "timestamp": 1700000000,
  "attachments": [
    {
      "filename": "document.pdf",
      "content": "base64_encoded_file_content_here",
      "content_type": "application/pdf"
    }
  ]
}
```

## Management CLI

The `manage.py` script provides commands for managing clients and API keys:

### List All Clients

```bash
python manage.py list-clients
```

### Create a New Client

```bash
python manage.py create-client
```

### List All API Keys

```bash
python manage.py list-api-keys
```

### Create a New API Key

```bash
python manage.py create-api-key
```

### Analytics Commands

```bash
# View analytics summary for a client
python manage.py show-analytics

# Create analytics snapshot for current quarter
python manage.py create-snapshot

# Rotate old quarterly data (archive and cleanup)
python manage.py rotate-data
```

## Analytics & Data Retention

### Overview

The SMTP Proxy includes comprehensive analytics tracking with automatic quarterly data rotation. This ensures you have detailed insights while managing database growth.

### Tracked Metrics

#### Email Volume Metrics
- Total emails sent/failed
- Success/failure rates
- Emails per hour/day/month
- Peak usage times

#### Performance Metrics
- Average processing time
- SMTP connection time
- P95/P99 latency percentiles
- Performance trends over time

#### Recipient Analytics
- Number of recipients (TO, CC, BCC)
- Distribution patterns
- Peak recipient counts

#### Attachment Metrics
- Total attachments sent
- Attachment sizes
- Emails with attachments
- Storage usage

#### Error Analytics
- Error types and frequencies
- Error distribution by time
- Most common failure reasons
- Error trends

### Quarterly Data Rotation

The system automatically manages data using a **quarterly rotation** strategy:

#### How It Works

1. **Active Data**: Current quarter + 2 previous quarters (configurable)
2. **Archival**: Older quarters are archived with anonymized data
3. **Snapshots**: Aggregated analytics are saved before archival
4. **Cleanup**: Detailed logs are removed after archiving

#### Rotation Process

```
Q1 2024 (Active)  → Detailed logs in email_logs table
Q4 2023 (Active)  → Detailed logs in email_logs table
Q3 2023 (Active)  → Detailed logs in email_logs table
Q2 2023 (Archive) → Anonymized data in archived_email_logs
Q1 2023 (Archive) → Anonymized data in archived_email_logs
```

#### Archived Data

Archived data includes:
- Statistical summaries (counts, averages, percentages)
- Temporal patterns (hour/day distributions)
- Performance metrics
- Error distributions
- **Excludes**: Email addresses, subjects, content

#### Manual Rotation

```bash
# Rotate data keeping only last 2 quarters
python manage.py rotate-data

# Specify number of quarters to keep
# (script will prompt)
```

#### Automated Rotation

You can set up a cron job for automatic rotation:

```bash
# Run quarterly rotation on the first day of each quarter
0 0 1 1,4,7,10 * cd /path/to/app && python manage.py rotate-data
```

### Analytics Endpoints

#### Client Analytics (Authenticated)

```bash
# Get analytics summary for your client (last 30 days)
GET /api/analytics/summary?days=30

# Get quarterly snapshots
GET /api/analytics/snapshots?limit=10

# Create snapshot for current quarter
POST /api/analytics/snapshot/create
```

**Example Response:**

```json
{
  "period": "2024-01-01 to 2024-01-31",
  "total_emails": 1500,
  "total_sent": 1485,
  "total_failed": 15,
  "success_rate": 99.0,
  "avg_processing_time_ms": 245.5,
  "daily_metrics": [
    {
      "date": "2024-01-01",
      "total_emails": 50,
      "success_rate": 98.0
    }
  ],
  "hourly_distribution": [
    {"hour": 9, "email_count": 150},
    {"hour": 14, "email_count": 200}
  ],
  "top_errors": [
    {
      "error_type": "SMTPAuthenticationError",
      "count": 10,
      "percentage": 66.7
    }
  ]
}
```

#### Admin Analytics Endpoints

```bash
# Global analytics across all clients
GET /api/admin/analytics/summary?days=30

# Analytics for specific client
GET /api/admin/analytics/client/{client_id}?days=30

# Trigger manual rotation
POST /api/admin/analytics/rotate?keep_quarters=2
```

### Database Schema

#### email_logs (Active Data)
- Full email details with analytics
- Current quarter + 2 previous quarters
- Indexed for fast queries

#### archived_email_logs (Historical Data)
- Anonymized email data
- Quarters older than retention window
- Statistical data only

#### analytics_snapshots (Aggregated Metrics)
- Quarterly/monthly summaries
- Pre-calculated metrics
- Long-term trend analysis

### Data Privacy

The rotation process ensures privacy:
- Email subjects are hashed (SHA256)
- Email addresses are removed
- Content is not archived
- Only statistical data is retained

### Performance Optimization

Analytics are optimized through:
- Database indexes on temporal fields
- Quarterly partitioning strategy
- Aggregated snapshots for fast queries
- Automatic cleanup of old data

## API Endpoints

### Public Endpoints

- `GET /` - Root endpoint with service info
- `GET /health` - Health check endpoint

### Email Endpoints (Requires Authentication)

- `POST /api/send` - Send an email via SMTP

### Admin Endpoints (Should be protected in production)

#### Client Management
- `POST /api/admin/clients` - Create a new client
- `GET /api/admin/clients` - List all clients
- `GET /api/admin/clients/{client_id}` - Get client details

#### API Key Management
- `POST /api/admin/api-keys` - Create a new API key
- `GET /api/admin/clients/{client_id}/api-keys` - List client's API keys
- `DELETE /api/admin/api-keys/{api_key_id}` - Deactivate an API key

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | - | **Required.** Secret key for JWT signing |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXPIRATION_HOURS` | `720` | JWT expiration (30 days) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./smtp_proxy.db` | Database connection URL |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `DEBUG` | `false` | Debug mode |

### SMTP Configuration

Each client has their own SMTP configuration:

- **SMTP Host**: The SMTP server hostname (e.g., `smtp.gmail.com`)
- **SMTP Port**: Usually 587 (TLS) or 465 (SSL)
- **Username/Password**: SMTP authentication credentials
- **TLS/SSL**: Connection encryption settings
- **Default From**: Optional default sender email and name

### Common SMTP Providers

#### Gmail
- Host: `smtp.gmail.com`
- Port: `587` (TLS) or `465` (SSL)
- Note: Use [App Passwords](https://support.google.com/accounts/answer/185833)

#### SendGrid
- Host: `smtp.sendgrid.net`
- Port: `587` (TLS)
- Username: `apikey`
- Password: Your SendGrid API key

#### Mailgun
- Host: `smtp.mailgun.org`
- Port: `587` (TLS)

#### Amazon SES
- Host: `email-smtp.{region}.amazonaws.com`
- Port: `587` (TLS)

## Security Considerations

### Production Deployment

1. **Change JWT Secret Key**: Use a strong, random secret key
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use HTTPS**: Always use HTTPS in production with a valid SSL certificate

3. **Protect Admin Endpoints**: Implement admin authentication for `/api/admin/*` endpoints

4. **Encrypt SMTP Passwords**: Consider encrypting SMTP passwords in the database

5. **Rate Limiting**: Implement rate limiting to prevent abuse

6. **Firewall**: Restrict database and SMTP server access

7. **Environment Variables**: Never commit `.env` file to version control

### Security Features

- **JWT Authentication**: Secure token-based authentication
- **Timestamp Validation**: Prevents replay attacks (1-hour window)
- **Password Hashing**: API keys are hashed before storage
- **Input Validation**: Comprehensive validation with Pydantic
- **SQL Injection Protection**: Using SQLAlchemy ORM
- **CORS**: Configurable CORS policy

## WordPress Integration

This proxy is compatible with the [wp-smtp-api](https://github.com/VrubPetCl/wp-smtp-api) WordPress plugin.

### Plugin Configuration

1. Install and activate the wp-smtp-api plugin
2. Configure the plugin settings:
   - **API Endpoint**: `https://your-domain.com/api/send`
   - **JWT Token**: The API key generated by `manage.py create-api-key`
   - **Method**: Bearer Token Authentication

## Database Schema

### Tables

#### clients
- Client configurations with SMTP settings
- One-to-many relationship with api_keys and email_logs

#### api_keys
- JWT token hashes for authentication
- Belongs to a client
- Tracks usage and expiration

#### email_logs
- Tracks all sent emails
- Stores status, recipients, and error messages

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

### Code Structure

```
fastapi-smtp-proxy/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration management
│   ├── models.py         # Pydantic models
│   ├── schemas.py        # SQLAlchemy models
│   ├── database.py       # Database setup
│   ├── auth.py           # Authentication
│   └── smtp_service.py   # SMTP email sending
├── manage.py             # Management CLI
├── requirements.txt      # Python dependencies
├── .env.example         # Example environment variables
└── README.md            # This file
```

## Troubleshooting

### Email Not Sending

1. **Check SMTP credentials**: Verify username/password are correct
2. **Check SMTP server**: Ensure the SMTP host and port are correct
3. **Check firewall**: Ensure outbound connections to SMTP port are allowed
4. **Check logs**: Look at application logs for detailed error messages
5. **Test SMTP**: Use a tool like `telnet` to test SMTP connectivity

### Authentication Errors

1. **JWT Token**: Ensure the token is valid and not expired
2. **Bearer Format**: Use `Authorization: Bearer YOUR_TOKEN`
3. **API Key Active**: Verify the API key is active in the database

### Timestamp Errors

1. **Server Time**: Ensure server time is synchronized (use NTP)
2. **Client Time**: Ensure client timestamp is current Unix timestamp
3. **Time Window**: Requests must be within 1 hour of current time

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[MIT License](LICENSE)

## Support

For issues, questions, or contributions, please open an issue on GitHub.

## Changelog

### Version 1.0.0 (Initial Release)

- JWT-based authentication
- Multi-tenant client management
- Email sending via SMTP
- Attachment support
- Email logging
- Management CLI
- WordPress wp-smtp-api compatibility
