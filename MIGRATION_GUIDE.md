# Migration Guide: Random String Tokens → JWT Tokens

## Overview

This guide helps you migrate from the old random string token system to the new JWT-based authentication system.

## Why This Migration is Necessary

**Problem:** The API endpoint expected JWT tokens, but the web interface was generating random strings, causing authentication failures (401 Unauthorized).

**Solution:** The web interface now generates proper JWT tokens that the API endpoint can validate.

## Breaking Change Warning

⚠️ **IMPORTANT:** This is a breaking change. All existing API keys generated before this fix will stop working.

## Migration Steps

### Step 1: Identify Affected Clients

Before starting, identify all clients that are currently using API keys:

```bash
# Log into your server and check the database
sqlite3 smtp_proxy.db "SELECT c.name, k.name, k.created_at
FROM api_keys k
JOIN clients c ON k.client_id = c.id
WHERE k.is_active = 1;"
```

### Step 2: Communicate with API Users

Notify all API users that:
1. Their current API keys will stop working after the migration
2. They need to update their applications with new JWT tokens
3. Provide them with a timeline for the migration

### Step 3: Deploy the Fix

1. **Backup your database:**
   ```bash
   cp smtp_proxy.db smtp_proxy.db.backup
   ```

2. **Pull the latest changes:**
   ```bash
   git pull
   ```

3. **Restart the application:**
   ```bash
   # If using systemd
   sudo systemctl restart fastapi-smtp-proxy

   # If using docker
   docker-compose restart

   # If running manually
   pkill -f uvicorn
   venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

### Step 4: Revoke Old API Keys

1. Log into the admin dashboard: `https://your-domain.com/admin/login`
2. For each client:
   - Navigate to "Clients" → Select client → "API Keys"
   - Revoke all existing API keys (click "Revoke" button)

Alternatively, revoke all keys via database:
```bash
sqlite3 smtp_proxy.db "UPDATE api_keys SET is_active = 0;"
```

### Step 5: Generate New JWT API Keys

For each client:

1. Navigate to client details: `/admin/clients/{client_id}`
2. Click "Generate API Key"
3. Fill in the form:
   - **Description**: e.g., "Production WordPress Site"
   - **Expiration Date**: Leave empty for 1-year default, or set custom date
4. Click "Generate API Key"
5. **Copy the JWT token immediately** - it will only be shown once
6. Securely send the token to the client

### Step 6: Update Client Applications

Each client needs to update their application to use the new JWT token:

**Old format (won't work anymore):**
```bash
curl -X POST https://your-domain.com/api/send \
  -H "X-API-Key: smtp_randomstring123..." \
  -H "Content-Type: application/json" \
  -d '...'
```

**New format (JWT with Bearer token):**
```bash
curl -X POST https://your-domain.com/api/send \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '...'
```

### Step 7: Verify New Tokens Work

Test each client's new token:

```bash
# Test sending an email
curl -X POST https://your-domain.com/api/send \
  -H "Authorization: Bearer YOUR_NEW_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["test@example.com"],
    "subject": "Test Email",
    "content": "Testing new JWT token",
    "timestamp": '$(date +%s)'
  }'
```

Expected response:
```json
{
  "success": true,
  "message": "Email sent successfully",
  "email_id": "123"
}
```

### Step 8: Monitor for Issues

After migration, monitor:
1. Email logs for failed authentications
2. Server logs for 401 errors
3. Client feedback

Check logs:
```bash
# If using systemd
journalctl -u fastapi-smtp-proxy -f

# If using docker
docker-compose logs -f

# If using file logs
tail -f /var/log/fastapi-smtp-proxy/app.log
```

## Rollback Plan (If Needed)

If you need to rollback:

1. **Restore the backup:**
   ```bash
   cp smtp_proxy.db.backup smtp_proxy.db
   ```

2. **Revert the code changes:**
   ```bash
   git revert HEAD
   ```

3. **Restart the application**

⚠️ **Note:** After rollback, JWT tokens generated during the migration will stop working, and old random string tokens will work again.

## Common Issues and Solutions

### Issue 1: 401 Unauthorized after migration

**Cause:** Client is still using old random string token

**Solution:**
1. Generate new JWT token for the client
2. Update client's application with new token
3. Ensure they're using `Authorization: Bearer` header

### Issue 2: Token has expired

**Cause:** JWT token has passed its expiration date

**Solution:**
1. Generate new JWT token with longer expiration
2. Update client's application

### Issue 3: Invalid token format

**Cause:** Token was truncated or modified

**Solution:**
1. Ensure the entire JWT token is copied (usually 150-200 characters)
2. Check for whitespace or newlines in the token
3. Generate new token if corrupted

## Code Examples for Client Updates

### Python (requests library)
```python
import requests
import time

API_URL = "https://your-domain.com/api/send"
JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

headers = {
    "Authorization": f"Bearer {JWT_TOKEN}",
    "Content-Type": "application/json"
}

data = {
    "to": ["recipient@example.com"],
    "subject": "Test Email",
    "content": "<p>Hello World</p>",
    "timestamp": int(time.time())
}

response = requests.post(API_URL, headers=headers, json=data)
print(response.json())
```

### PHP (cURL)
```php
<?php
$apiUrl = "https://your-domain.com/api/send";
$jwtToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

$data = [
    "to" => ["recipient@example.com"],
    "subject" => "Test Email",
    "content" => "<p>Hello World</p>",
    "timestamp" => time()
];

$ch = curl_init($apiUrl);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_HTTPHEADER, [
    "Authorization: Bearer $jwtToken",
    "Content-Type: application/json"
]);

$response = curl_exec($ch);
curl_close($ch);

echo $response;
?>
```

### JavaScript (fetch API)
```javascript
const API_URL = "https://your-domain.com/api/send";
const JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";

const data = {
    to: ["recipient@example.com"],
    subject: "Test Email",
    content: "<p>Hello World</p>",
    timestamp: Math.floor(Date.now() / 1000)
};

fetch(API_URL, {
    method: "POST",
    headers: {
        "Authorization": `Bearer ${JWT_TOKEN}`,
        "Content-Type": "application/json"
    },
    body: JSON.stringify(data)
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error("Error:", error));
```

## FAQ

**Q: Can I use both old and new tokens during migration?**
A: No, the system only supports one authentication method at a time. Plan for a short downtime window or quick migration.

**Q: How long are JWT tokens valid?**
A: By default, 1 year (365 days). You can set custom expiration when generating each key.

**Q: Can I regenerate an expired JWT?**
A: No, generate a new JWT token with a new expiration date.

**Q: Are JWT tokens more secure than random strings?**
A: Yes, JWT tokens are signed and tamper-proof, include metadata, and have built-in expiration.

**Q: What happens if the JWT_SECRET_KEY changes?**
A: All existing JWT tokens become invalid. Keep this secret secure and never change it unless absolutely necessary.

## Support

If you encounter issues during migration:

1. Check the logs for detailed error messages
2. Review the test script: `venv/bin/python test_jwt_fix.py`
3. Consult the summary: `JWT_TOKEN_FIX_SUMMARY.md`
4. Open an issue on GitHub with error details

## Post-Migration Checklist

- [ ] Database backed up
- [ ] Code deployed and application restarted
- [ ] Old API keys revoked
- [ ] New JWT tokens generated for all clients
- [ ] Tokens securely distributed to clients
- [ ] Client applications updated
- [ ] API endpoints tested with new tokens
- [ ] Monitoring in place for errors
- [ ] Clients notified of successful migration
- [ ] Documentation updated

---

**Migration completed?** Test everything works with: `venv/bin/python test_jwt_fix.py`
