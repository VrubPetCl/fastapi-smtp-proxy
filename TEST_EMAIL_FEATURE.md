# Test Email Feature Documentation

## Overview

The Test Email feature allows administrators to verify SMTP configurations by sending a test email directly from the dashboard. This helps ensure that client SMTP settings are correct before using them in production.

## How to Use

### 1. Navigate to Client Detail Page

From the admin dashboard:
1. Go to **Clients** page
2. Click on a client to view its details

### 2. Send Test Email

1. Click the **"Send Test Email"** button (green button in the header)
2. A modal window will appear with:
   - Email input field (pre-populated with your admin email)
   - Send button
   - Close button

### 3. Enter Recipient Email

- The field is pre-populated with your admin user's email address
- You can change it to any valid email address
- Email format is validated before sending

### 4. Send and View Results

Click **"Send Test Email"** and the system will:
1. Validate the email format
2. Decrypt the client's SMTP password
3. Connect to the SMTP server
4. Send a test email with configuration details
5. Display comprehensive logs in the modal

### 5. Check Results

The modal will show:
- ✅ **Success**: Green banner with success message
- ❌ **Error**: Red banner with error details
- 📋 **Logs**: Terminal-style log output showing each step

## Test Email Content

The test email includes:
- Subject: "Test Email from [Client Name] - SMTP Proxy"
- Beautiful HTML formatting
- Configuration details:
  - Client name
  - SMTP host and port
  - SMTP username
  - TLS/SSL status
- Timestamp
- Both HTML and plain text versions

## Example Test Email

```
✅ SMTP Configuration Test

This is a test email sent from your SMTP Proxy configuration.

Configuration Details:
- Client: My Company
- SMTP Host: smtp.gmail.com:587
- SMTP Username: noreply@example.com
- TLS: Enabled
- SSL: Disabled

If you received this email, your SMTP configuration is working correctly!

Sent at: 2025-11-21 10:30:00 UTC
From: FastAPI SMTP Proxy
```

## Log Output Example

### Success Case:
```
2025-11-21 10:30:00 - INFO - Email validation passed: test@example.com
2025-11-21 10:30:00 - INFO - Fetching client 1 from database
2025-11-21 10:30:00 - INFO - Client found: My Company
2025-11-21 10:30:00 - INFO - Decrypting SMTP password
2025-11-21 10:30:00 - INFO - SMTP password decrypted successfully
2025-11-21 10:30:00 - INFO - Preparing test email message
2025-11-21 10:30:00 - INFO - Connecting to SMTP server: smtp.gmail.com:587
2025-11-21 10:30:00 - INFO - Initiating SMTP connection (TLS: True, SSL: False)
2025-11-21 10:30:01 - INFO - SMTP connection established
2025-11-21 10:30:01 - INFO - Sending email to test@example.com
2025-11-21 10:30:02 - INFO - Email sent successfully! Server response: {}
```

### Authentication Error Case:
```
2025-11-21 10:30:00 - INFO - Email validation passed: test@example.com
2025-11-21 10:30:00 - INFO - Fetching client 1 from database
2025-11-21 10:30:00 - INFO - Client found: My Company
2025-11-21 10:30:00 - INFO - Decrypting SMTP password
2025-11-21 10:30:00 - INFO - SMTP password decrypted successfully
2025-11-21 10:30:00 - INFO - Preparing test email message
2025-11-21 10:30:00 - INFO - Connecting to SMTP server: smtp.gmail.com:587
2025-11-21 10:30:00 - INFO - Initiating SMTP connection (TLS: True, SSL: False)
2025-11-21 10:30:02 - ERROR - SMTP Authentication failed: (535, b'5.7.8 Username and Password not accepted')
```

## Error Handling

The system handles various error scenarios:

### 1. Invalid Email Format
- **Error**: "Invalid email address format"
- **Solution**: Enter a valid email address (e.g., user@example.com)

### 2. Client Not Found
- **Error**: "Client not found"
- **Solution**: Verify the client exists and refresh the page

### 3. Client Inactive
- **Error**: "Client is inactive. Activate the client before testing."
- **Solution**: Edit the client and check the "Client is active" checkbox

### 4. Decryption Failed
- **Error**: "Failed to decrypt SMTP password. Check encryption configuration."
- **Solution**:
  - Ensure ENCRYPTION_KEY is set in .env
  - Run migration script if upgrading from plaintext passwords
  - Re-save the client with a new password

### 5. SMTP Authentication Failed
- **Error**: "SMTP Authentication failed. Check username and password."
- **Solution**:
  - Verify SMTP username is correct
  - Verify SMTP password is correct
  - Check if the SMTP provider requires app-specific passwords
  - Verify account is not locked or requires 2FA setup

### 6. SMTP Connection Failed
- **Error**: "SMTP Error: [details]"
- **Solution**:
  - Verify SMTP host and port are correct
  - Check if TLS/SSL settings match your SMTP provider
  - Ensure firewall allows outbound connections on the SMTP port
  - Verify network connectivity

### 7. Network Error
- **Error**: "Network error: [details]"
- **Solution**:
  - Check internet connectivity
  - Verify DNS resolution for SMTP host
  - Check if SMTP host is accessible from your server

## Security Features

### Email Validation
- Uses Pydantic `EmailStr` for strict email format validation
- Prevents SQL injection attacks
- Prevents XSS attacks
- Rejects invalid email formats

### Authentication
- Requires admin authentication (session-based)
- Only authenticated admin users can send test emails
- No public access to the endpoint

### Password Security
- SMTP passwords are decrypted only for the duration of sending
- Passwords are never exposed in logs or responses
- Uses Fernet encryption (AES-128 CBC)

### Error Sanitization
- Errors are sanitized to prevent sensitive data leakage
- Full error details shown only to admins in logs
- SMTP credentials never appear in error messages

## API Endpoint

### POST `/admin/clients/{client_id}/test-email`

**Authentication**: Required (Admin session)

**Parameters**:
- `client_id` (path): Client ID
- `test_email` (form): Recipient email address

**Request**:
```http
POST /admin/clients/1/test-email HTTP/1.1
Content-Type: application/x-www-form-urlencoded

test_email=admin@example.com
```

**Response (Success)**:
```json
{
  "success": true,
  "message": "Test email sent successfully to admin@example.com",
  "logs": [
    "2025-11-21 10:30:00 - INFO - Email validation passed: admin@example.com",
    "2025-11-21 10:30:00 - INFO - Fetching client 1 from database",
    "2025-11-21 10:30:00 - INFO - Client found: My Company",
    "2025-11-21 10:30:02 - INFO - Email sent successfully! Server response: {}"
  ]
}
```

**Response (Error)**:
```json
{
  "success": false,
  "error": "SMTP Authentication failed. Check username and password.",
  "logs": [
    "2025-11-21 10:30:00 - INFO - Email validation passed: admin@example.com",
    "2025-11-21 10:30:00 - INFO - Fetching client 1 from database",
    "2025-11-21 10:30:02 - ERROR - SMTP Authentication failed: (535, b'5.7.8 Username and Password not accepted')"
  ]
}
```

## Common SMTP Provider Settings

### Gmail
```
SMTP Host: smtp.gmail.com
SMTP Port: 587
Use TLS: ✓ Enabled
Use SSL: ✗ Disabled
Note: Use App Password, not regular password (requires 2FA)
```

### Outlook/Office 365
```
SMTP Host: smtp.office365.com
SMTP Port: 587
Use TLS: ✓ Enabled
Use SSL: ✗ Disabled
```

### SendGrid
```
SMTP Host: smtp.sendgrid.net
SMTP Port: 587
Use TLS: ✓ Enabled
Use SSL: ✗ Disabled
Username: apikey
Password: [Your API Key]
```

### Mailgun
```
SMTP Host: smtp.mailgun.org
SMTP Port: 587
Use TLS: ✓ Enabled
Use SSL: ✗ Disabled
```

### Amazon SES
```
SMTP Host: email-smtp.[region].amazonaws.com
SMTP Port: 587
Use TLS: ✓ Enabled
Use SSL: ✗ Disabled
Username: [SMTP Username]
Password: [SMTP Password]
```

## Troubleshooting

### Test Email Not Appearing in Inbox

1. **Check Spam Folder**: Test emails may be marked as spam
2. **Wait a Few Minutes**: SMTP delivery can take 1-5 minutes
3. **Check Logs**: Review logs in the modal for errors
4. **Verify Email Address**: Ensure the recipient email is correct

### "Connection Timeout" Error

1. **Firewall**: Ensure outbound SMTP ports are not blocked
2. **Network**: Verify internet connectivity
3. **Port**: Try alternative SMTP ports (587, 465, 25)
4. **DNS**: Verify SMTP host DNS resolution

### "TLS/SSL Handshake Failed"

1. **TLS vs SSL**: Try toggling between TLS and SSL options
2. **Port**: Ensure port matches encryption type:
   - Port 587: Use TLS (STARTTLS)
   - Port 465: Use SSL
   - Port 25: Usually no encryption
3. **Update Libraries**: Ensure aiosmtplib is up to date

## Best Practices

1. **Test After Creating**: Always test SMTP configuration immediately after creating a client
2. **Test After Changes**: Re-test whenever you update SMTP settings
3. **Use Your Email**: Start by sending test emails to your own address
4. **Check Logs**: Always review logs to understand what happened
5. **Document Settings**: Keep notes on working configurations for each provider
6. **App Passwords**: Use app-specific passwords for Gmail and similar providers
7. **Secure Credentials**: Never share SMTP credentials or log outputs publicly

## Feature Benefits

- ✅ **Instant Verification**: Know immediately if SMTP settings work
- ✅ **Detailed Logs**: See exactly what's happening at each step
- ✅ **No Storage**: Logs are not stored, only displayed temporarily
- ✅ **Beautiful UI**: Clean modal interface with visual feedback
- ✅ **Secure**: Email validation, encryption, authentication required
- ✅ **Production Ready**: Test before using in production
- ✅ **Time Saving**: No need to use external SMTP testing tools
- ✅ **Debugging**: Detailed error messages help troubleshoot issues

## Future Enhancements

Potential future improvements:
- Rate limiting on test emails
- Test email history/logging (optional)
- Bulk testing for multiple clients
- Advanced diagnostics (MX record checks, port scanning)
- Email deliverability testing
- SPF/DKIM/DMARC validation

---

**Version**: 1.0
**Last Updated**: 2025-11-21
**Author**: FastAPI SMTP Proxy Team
