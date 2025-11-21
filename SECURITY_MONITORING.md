# Security Monitoring & IP Tracking

## Overview

The FastAPI SMTP Proxy includes comprehensive security monitoring features to track and analyze IP addresses, login attempts, and suspicious activity. This allows administrators to detect and respond to potential security threats, including unauthorized access attempts from unexpected geographic locations.

---

## Features

✅ **IP Address Tracking** - All email sends and login attempts tracked by source IP
✅ **Login Attempt Logging** - Complete audit trail of successful and failed logins
✅ **Suspicious IP Detection** - Automatic flagging of IPs with multiple failed attempts
✅ **Geographic Analysis** - Country-level tracking (with GeoIP integration)
✅ **User Agent Logging** - Browser/client identification for forensic analysis
✅ **Real-time Dashboard** - Visual security monitoring interface

---

## Dashboard Access

Navigate to **Security Logs** in the admin navigation menu or visit:

```
https://your-domain.com/admin/security-logs
```

### Time Range Filters

- Last 24 hours
- Last 7 days (default)
- Last 30 days
- Last 90 days

---

## Tracked Information

### Login Attempts

Every login attempt (successful and failed) is logged with:

- **Timestamp** - When the attempt occurred
- **Username** - Account being accessed
- **IP Address** - Source IP (IPv4 or IPv6)
- **User Agent** - Browser/client information
- **Status** - Success or failure
- **Failure Reason** - Why authentication failed
- **Country Code** - Geographic location (ISO 3166-1 alpha-2)
- **City** - City location (optional)

### Email Sending Activity

Every email sent through the API is tracked with:

- **Source IP** - IP address of the API client
- **User Agent** - Client application identifier
- **Country Code** - Geographic origin
- **Client Name** - Which SMTP client configuration was used
- **Timestamp** - When the email was sent

---

## Suspicious IP Detection

IPs are automatically flagged as suspicious when they have:

- **2+ failed login attempts** in the selected time range

### Threat Levels

| Level | Criteria | Badge Color |
|-------|----------|-------------|
| 🟡 **Low** | 2-4 failed attempts | Yellow |
| 🟠 **Medium** | 5-9 failed attempts | Orange |
| 🔴 **High** | 10+ failed attempts | Red |

---

## Security Dashboard Sections

### 1. Statistics Overview

Real-time metrics:
- Total login attempts
- Failed login count
- Success rate percentage
- Number of suspicious IPs

### 2. Suspicious IPs Table

Shows IPs with multiple failed login attempts:
- IP address (monospace font)
- Country code
- Total attempts vs failed attempts
- Last attempt timestamp
- Threat level indicator

### 3. Email Sending Activity

Recent API usage by IP address:
- IP addresses sending emails
- Country of origin
- Associated client configuration
- Email volume
- Last activity timestamp

### 4. Login Attempts Log

Complete audit trail (last 100 attempts):
- Chronological list of all login attempts
- Successful attempts shown with green checkmark
- Failed attempts highlighted in red
- Full details including IP, user agent, and location

### 5. Geographic Analysis

Country-level statistics:
- Login attempts grouped by country
- Visual grid display of top countries
- Useful for identifying unexpected geographic sources

---

## Database Schema

### `login_attempts` Table

```sql
CREATE TABLE login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NOT NULL,        -- IPv4 or IPv6
    user_agent VARCHAR(500),
    success BOOLEAN NOT NULL,
    failure_reason VARCHAR(100),           -- invalid_credentials, etc.
    attempted_at TIMESTAMP NOT NULL,
    country_code VARCHAR(2),               -- ISO 3166-1 alpha-2
    city VARCHAR(100)
);

-- Indexes for fast querying
CREATE INDEX idx_login_ip_address ON login_attempts(ip_address);
CREATE INDEX idx_login_username ON login_attempts(username);
CREATE INDEX idx_login_attempted_at ON login_attempts(attempted_at);
CREATE INDEX idx_ip_attempted_at ON login_attempts(ip_address, attempted_at);
```

### `email_logs` Table (New Columns)

```sql
ALTER TABLE email_logs ADD COLUMN source_ip VARCHAR(45);
ALTER TABLE email_logs ADD COLUMN user_agent VARCHAR(500);
ALTER TABLE email_logs ADD COLUMN country_code VARCHAR(2);

CREATE INDEX idx_source_ip_sent_at ON email_logs(source_ip, sent_at);
```

---

## Detecting Threats

### Example: Suspicious Activity from Russia/China

1. Navigate to **Security > Suspicious IPs** section
2. Look for country codes: `RU` (Russia), `CN` (China)
3. Check threat level and attempt count
4. Review user agents for bot-like patterns
5. Cross-reference with email sending activity

### Example: Brute Force Attack

Indicators:
- Single IP with 10+ failed attempts
- Short time span between attempts
- Same username repeatedly
- Generic or automated user agent

**Response Actions:**
- Note the IP address
- Implement IP blocking at firewall level
- Enable 2FA for the targeted account
- Review rate limiting settings

### Example: Distributed Attack

Indicators:
- Multiple IPs from same country
- Similar user agent strings
- Failed attempts on multiple accounts
- Coordinated timing pattern

**Response Actions:**
- Block country at firewall (if not legitimate traffic source)
- Enable stricter rate limiting
- Implement CAPTCHA on login page
- Alert security team

---

## Geographic Analysis with GeoIP

### Current Status

The system includes columns for country and city tracking, but requires GeoIP integration for automatic population.

### Without GeoIP

- `country_code` and `city` fields will be `NULL`
- Manual country identification via external IP lookup tools

### With GeoIP (Future Enhancement)

To enable automatic geographic detection:

1. **Install GeoIP2 library:**
   ```bash
   pip install geoip2
   ```

2. **Download MaxMind database:**
   - Sign up at https://www.maxmind.com
   - Download GeoLite2-City.mmdb

3. **Add to config:**
   ```python
   # app/config.py
   geoip_db_path = "/path/to/GeoLite2-City.mmdb"
   ```

4. **Implement lookup function:**
   ```python
   # app/geoip.py
   import geoip2.database

   def get_country_code(ip_address: str) -> str:
       try:
           reader = geoip2.database.Reader('GeoLite2-City.mmdb')
           response = reader.city(ip_address)
           return response.country.iso_code
       except:
           return None
   ```

5. **Update login/send handlers** to populate country fields

---

## API Endpoints

### Get Security Logs (Admin Only)

```
GET /admin/security-logs?days=7
```

**Query Parameters:**
- `days` (optional) - Time range: 1, 7, 30, or 90 days

**Response:** HTML page with security dashboard

---

## Security Best Practices

### 1. Regular Monitoring

- Check security logs daily
- Set up alerts for high threat levels
- Review weekly geographic patterns

### 2. Rate Limiting

Current implementation:
- 5 failed attempts allowed
- 15-minute lockout period
- Per-IP and per-username basis

Located in: `app/web.py:26-28`

### 3. IP Blocking

When suspicious activity detected:

**Option A: Application Level**
```python
# Add to app/web.py
BLOCKED_IPS = {'1.2.3.4', '5.6.7.8'}

@router.post("/admin/login")
async def login(request: Request, ...):
    client_ip = request.client.host
    if client_ip in BLOCKED_IPS:
        raise HTTPException(status_code=403)
```

**Option B: Firewall Level** (Recommended)
```bash
# Using UFW
sudo ufw deny from 1.2.3.4
sudo ufw deny from 5.6.7.8

# Using iptables
sudo iptables -A INPUT -s 1.2.3.4 -j DROP
sudo iptables -A INPUT -s 5.6.7.8 -j DROP
```

### 4. Country Blocking

Block entire countries if no legitimate traffic expected:

**Nginx Example:**
```nginx
# /etc/nginx/conf.d/geoip.conf
geo $block_country {
    default no;
    RU yes;  # Russia
    CN yes;  # China
    KP yes;  # North Korea
}

server {
    if ($block_country = yes) {
        return 403;
    }
}
```

### 5. Two-Factor Authentication

Consider implementing 2FA for admin accounts:
- TOTP (Time-based One-Time Password)
- SMS verification
- Email verification codes

---

## Querying Security Data

### SQL Examples

**Find all failed login attempts from specific IP:**
```sql
SELECT * FROM login_attempts
WHERE ip_address = '1.2.3.4' AND success = 0
ORDER BY attempted_at DESC;
```

**Count login attempts by country:**
```sql
SELECT country_code, COUNT(*) as attempts
FROM login_attempts
WHERE attempted_at >= datetime('now', '-7 days')
GROUP BY country_code
ORDER BY attempts DESC;
```

**Find emails sent from suspicious IPs:**
```sql
SELECT el.*, c.name as client_name
FROM email_logs el
JOIN clients c ON el.client_id = c.id
WHERE el.source_ip IN (
    SELECT DISTINCT ip_address
    FROM login_attempts
    WHERE success = 0
    GROUP BY ip_address
    HAVING COUNT(*) >= 3
)
ORDER BY el.sent_at DESC;
```

**Identify bot-like patterns:**
```sql
SELECT ip_address, user_agent, COUNT(*) as attempts
FROM login_attempts
WHERE attempted_at >= datetime('now', '-1 day')
  AND (user_agent LIKE '%bot%' OR user_agent LIKE '%crawler%')
GROUP BY ip_address, user_agent
ORDER BY attempts DESC;
```

---

## Troubleshooting

### Issue: No IPs showing in dashboard

**Cause:** Migration not run or columns not added

**Solution:**
```bash
python migrate_add_ip_tracking.py
```

### Issue: All IPs show as "unknown"

**Cause:** Running behind reverse proxy without proper headers

**Solution:** Configure proxy to forward real IP:

**Nginx:**
```nginx
location / {
    proxy_pass http://localhost:8000;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**FastAPI Middleware:**
```python
# app/main.py
from fastapi.middleware.trustedhost import TrustedHostMiddleware

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)
```

### Issue: Country codes all NULL

**Cause:** GeoIP not configured

**Solution:** See "Geographic Analysis with GeoIP" section above

---

## Migration Script

The migration script `migrate_add_ip_tracking.py` handles:

- Adding `source_ip`, `user_agent`, `country_code` to `email_logs`
- Creating `login_attempts` table
- Creating all necessary indexes

**Run migration:**
```bash
python migrate_add_ip_tracking.py
```

**Rollback (if needed):**
```bash
python migrate_add_ip_tracking.py rollback
```

---

## Privacy Considerations

### Data Retention

IP addresses are personal data under GDPR. Consider:

- **Retention Policy:** Delete logs older than 90 days
- **Purpose Limitation:** Only use for security monitoring
- **Access Control:** Restrict to authorized administrators

### Compliance

**GDPR Requirements:**
- Document legitimate interest for IP logging
- Provide data access/deletion on request
- Secure storage with encryption

**Implementation:**
```sql
-- Delete logs older than 90 days
DELETE FROM login_attempts
WHERE attempted_at < datetime('now', '-90 days');

DELETE FROM email_logs
WHERE sent_at < datetime('now', '-90 days')
  AND source_ip IS NOT NULL;
```

**Automated Cleanup (Cron):**
```bash
# /etc/cron.daily/cleanup-security-logs
#!/bin/bash
sqlite3 /path/to/smtp_proxy.db <<EOF
DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-90 days');
DELETE FROM email_logs WHERE sent_at < datetime('now', '-90 days');
VACUUM;
EOF
```

---

## Integration with SIEM

Export security logs to Security Information and Event Management (SIEM) systems:

### JSON Export Example

```python
import json
from app.database import get_db
from app.schemas import LoginAttempt

async def export_security_logs():
    async with get_db() as db:
        result = await db.execute(
            select(LoginAttempt)
            .where(LoginAttempt.attempted_at >= datetime.now() - timedelta(days=1))
        )
        attempts = result.scalars().all()

        logs = [{
            'timestamp': a.attempted_at.isoformat(),
            'ip': a.ip_address,
            'country': a.country_code,
            'username': a.username,
            'success': a.success,
            'user_agent': a.user_agent
        } for a in attempts]

        with open('security_logs.json', 'w') as f:
            json.dump(logs, f, indent=2)
```

### Syslog Integration

```python
import syslog

def log_to_syslog(attempt: LoginAttempt):
    status = "SUCCESS" if attempt.success else "FAILURE"
    message = f"Login {status}: {attempt.username} from {attempt.ip_address} ({attempt.country_code})"

    syslog.syslog(
        syslog.LOG_AUTH | syslog.LOG_INFO if attempt.success else syslog.LOG_WARNING,
        message
    )
```

---

## Support

For issues or questions about security monitoring:
- Review `SECURITY_ASSESSMENT_2025-11-21.md` for security audit results
- Check application logs for errors
- Verify database schema with `sqlite3 smtp_proxy.db ".schema"`

---

**Version**: 1.0
**Last Updated**: 2025-11-21
**Migration**: `migrate_add_ip_tracking.py`
