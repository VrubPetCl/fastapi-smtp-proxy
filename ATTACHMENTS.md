# Email Attachments Guide

## Overview

The FastAPI SMTP Proxy supports email attachments with comprehensive validation, security checks, and size limits. Attachments can be sent via the API or tested through the dashboard.

---

## Features

✅ **Base64 encoding** for safe transmission
✅ **Size validation** (25MB per file, 50MB total)
✅ **Content type validation** with whitelist
✅ **Filename sanitization** to prevent path traversal
✅ **Automatic MIME encoding** and headers
✅ **Test email support** with file upload UI

---

## API Usage

### Sending Emails with Attachments

**Endpoint**: `POST /api/send`

**Authentication**: X-API-Key (JWT token)

#### Request Format

```json
{
  "to": ["recipient@example.com"],
  "subject": "Invoice #12345",
  "content": "<p>Please find attached your invoice.</p>",
  "from": "billing@company.com",
  "from_name": "Company Billing",
  "timestamp": 1700000000,
  "content_type": "text/html",
  "attachments": [
    {
      "filename": "invoice-12345.pdf",
      "content": "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PAovVHlwZSAvQ2F0YW...",
      "content_type": "application/pdf"
    },
    {
      "filename": "receipt.png",
      "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADU...",
      "content_type": "image/png"
    }
  ]
}
```

#### Attachment Object Structure

```python
{
    "filename": str,        # Required: Max 255 chars, no path separators
    "content": str,         # Required: Base64 encoded file content
    "content_type": str     # Optional: MIME type (default: application/octet-stream)
}
```

---

## Size Limits

| Limit | Value | Notes |
|-------|-------|-------|
| **Per attachment** | 25 MB | Maximum size for a single file |
| **Total attachments** | 50 MB | Sum of all attachments in one email |
| **Filename length** | 255 chars | Maximum filename length |

---

## Supported File Types

### Documents
- **PDF**: `application/pdf`
- **Word**: `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- **Excel**: `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- **PowerPoint**: `application/vnd.ms-powerpoint`

### Images
- **JPEG/JPG**: `image/jpeg`
- **PNG**: `image/png`
- **GIF**: `image/gif`
- **SVG**: `image/svg+xml`
- **WebP**: `image/webp`

### Archives
- **ZIP**: `application/zip`, `application/x-zip-compressed`
- **RAR**: `application/x-rar-compressed`
- **7-Zip**: `application/x-7z-compressed`

### Text
- **Plain text**: `text/plain`
- **CSV**: `text/csv`
- **HTML**: `text/html`
- **JSON**: `application/json`
- **XML**: `application/xml`

### Media
- **Audio**: `audio/*` (any audio type)
- **Video**: `video/*` (any video type)

---

## Base64 Encoding

### Python Example

```python
import base64

# Read file
with open('invoice.pdf', 'rb') as f:
    file_content = f.read()

# Encode to base64
base64_content = base64.b64encode(file_content).decode('utf-8')

# Create attachment
attachment = {
    "filename": "invoice.pdf",
    "content": base64_content,
    "content_type": "application/pdf"
}
```

### JavaScript Example

```javascript
// File input element
const fileInput = document.getElementById('file');
const file = fileInput.files[0];

// Read and encode
const reader = new FileReader();
reader.onload = function(e) {
    const base64Content = btoa(e.target.result);

    const attachment = {
        filename: file.name,
        content: base64Content,
        content_type: file.type || 'application/octet-stream'
    };

    // Send email with attachment...
};
reader.readAsBinaryString(file);
```

### Command Line (Linux/Mac)

```bash
# Encode file to base64
base64 -w 0 invoice.pdf > invoice_base64.txt

# Or inline
base64_content=$(base64 -w 0 invoice.pdf)
```

---

## Complete API Example

### Python with Requests

```python
import requests
import base64
import time

# Configuration
API_URL = "https://your-smtp-proxy.com/api/send"
API_KEY = "your-jwt-token-here"

# Read and encode file
with open('invoice.pdf', 'rb') as f:
    pdf_content = base64.b64encode(f.read()).decode('utf-8')

with open('company_logo.png', 'rb') as f:
    logo_content = base64.b64encode(f.read()).decode('utf-8')

# Prepare email
email_data = {
    "to": ["customer@example.com"],
    "subject": "Your Invoice - November 2025",
    "content": """
        <html>
            <body>
                <h2>Thank you for your business!</h2>
                <p>Please find attached your invoice for November 2025.</p>
                <p>If you have any questions, please don't hesitate to contact us.</p>
                <br>
                <p>Best regards,<br>The Billing Team</p>
            </body>
        </html>
    """,
    "from": "billing@company.com",
    "from_name": "Company Billing Department",
    "timestamp": int(time.time()),
    "content_type": "text/html",
    "attachments": [
        {
            "filename": "invoice-2025-11.pdf",
            "content": pdf_content,
            "content_type": "application/pdf"
        },
        {
            "filename": "logo.png",
            "content": logo_content,
            "content_type": "image/png"
        }
    ]
}

# Send email
headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

response = requests.post(API_URL, json=email_data, headers=headers)

if response.status_code == 200:
    result = response.json()
    print(f"✅ Email sent successfully!")
    print(f"   Email ID: {result['email_id']}")
else:
    print(f"❌ Failed to send email: {response.text}")
```

### Node.js Example

```javascript
const fs = require('fs');
const axios = require('axios');

const API_URL = 'https://your-smtp-proxy.com/api/send';
const API_KEY = 'your-jwt-token-here';

// Read and encode file
const pdfContent = fs.readFileSync('invoice.pdf').toString('base64');

// Prepare email
const emailData = {
    to: ['customer@example.com'],
    subject: 'Your Invoice - November 2025',
    content: '<h2>Please find attached your invoice.</h2>',
    from: 'billing@company.com',
    from_name: 'Company Billing',
    timestamp: Math.floor(Date.now() / 1000),
    content_type: 'text/html',
    attachments: [
        {
            filename: 'invoice-2025-11.pdf',
            content: pdfContent,
            content_type: 'application/pdf'
        }
    ]
};

// Send email
axios.post(API_URL, emailData, {
    headers: {
        'X-API-Key': API_KEY,
        'Content-Type': 'application/json'
    }
})
.then(response => {
    console.log('✅ Email sent successfully!');
    console.log('Email ID:', response.data.email_id);
})
.catch(error => {
    console.error('❌ Failed to send email:', error.response.data);
});
```

---

## Dashboard Test Email with Attachments

### Using the Test Email Feature

1. Navigate to a client detail page
2. Click **"Send Test Email"** button
3. Enter recipient email address
4. Click **"Choose File"** to select an attachment
5. Supported files: PDF, Word, Excel, Images, ZIP, Text
6. Maximum size: 25MB
7. Click **"Send Test Email"**
8. View logs to confirm attachment was sent

The test email will include:
- Configuration details
- The attached file
- Detailed logs showing attachment processing

---

## Security & Validation

### Filename Validation

**Blocked characters**:
- `/` (forward slash)
- `\` (backslash)
- `\0` (null byte)
- `..` (parent directory)

**Example violations**:
```python
# ❌ These filenames will be rejected
"../../../etc/passwd"
"folder/file.pdf"
"C:\\Windows\\system32\\file.exe"
"file\0.pdf"

# ✅ These filenames are valid
"invoice-2025-11.pdf"
"company_logo.png"
"report (final).docx"
"data-2025.csv"
```

### Content Type Validation

Only safe content types are allowed. Executable files and scripts are blocked:

**Blocked** (examples):
- `application/x-executable`
- `application/x-msdownload` (.exe)
- `application/x-sh` (shell scripts)
- `text/x-python` (Python scripts)

**Allowed**: Documents, images, archives, text, media files

### Base64 Validation

- Content must be valid base64
- Automatic validation on decode
- Invalid base64 returns error immediately

### Size Validation

```python
# Validation flow:
1. Check individual file size (max 25MB)
   └─> Reject if file > 25MB

2. Check total attachments size (max 50MB)
   └─> Reject if sum > 50MB

3. Decode base64 and attach to email
```

---

## Error Handling

### Common Errors

#### 1. File Too Large

```json
{
  "success": false,
  "error": "Attachment too large. Max size: 25MB, got: 30.5MB"
}
```

**Solution**: Compress or split the file

#### 2. Total Size Exceeded

```json
{
  "success": false,
  "error": "Total attachments too large. Max: 50MB, got: 65.2MB"
}
```

**Solution**: Remove some attachments or reduce file sizes

#### 3. Invalid Base64

```json
{
  "success": false,
  "error": "Invalid base64 content: Incorrect padding"
}
```

**Solution**: Verify base64 encoding is correct

#### 4. Invalid Filename

```json
{
  "success": false,
  "error": "Filename contains invalid character: /"
}
```

**Solution**: Remove path separators from filename

#### 5. Blocked Content Type

```json
{
  "success": false,
  "error": "Content type not allowed: application/x-executable"
}
```

**Solution**: Use allowed content types only

---

## Best Practices

### 1. Optimize File Size

```python
# ✅ Good: Compress before sending
from PIL import Image

img = Image.open('photo.jpg')
img.save('photo_compressed.jpg', quality=85, optimize=True)
```

### 2. Use Correct Content Types

```python
# ✅ Good: Specify accurate content type
{
    "filename": "invoice.pdf",
    "content": base64_content,
    "content_type": "application/pdf"  # Explicit type
}

# ⚠️ Okay: Let system detect
{
    "filename": "invoice.pdf",
    "content": base64_content,
    "content_type": "application/octet-stream"  # Generic
}
```

### 3. Handle Errors Gracefully

```python
try:
    response = requests.post(API_URL, json=email_data, headers=headers)
    response.raise_for_status()
    print("Email sent successfully!")
except requests.exceptions.HTTPError as e:
    error_data = e.response.json()
    if 'too large' in error_data.get('error', ''):
        print("File size too large. Please compress and try again.")
    else:
        print(f"Error: {error_data.get('error')}")
```

### 4. Batch Processing

For multiple attachments, process in batches:

```python
def send_email_with_attachments(files):
    attachments = []
    total_size = 0

    for file_path in files:
        # Check size before encoding
        file_size = os.path.getsize(file_path)

        if file_size > 25 * 1024 * 1024:
            print(f"Skipping {file_path}: too large")
            continue

        if total_size + file_size > 50 * 1024 * 1024:
            print(f"Batch full, sending current batch...")
            send_email(attachments)
            attachments = []
            total_size = 0

        # Read and encode
        with open(file_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode('utf-8')

        attachments.append({
            "filename": os.path.basename(file_path),
            "content": content,
            "content_type": mimetypes.guess_type(file_path)[0]
        })

        total_size += file_size

    if attachments:
        send_email(attachments)
```

### 5. Progress Indication

For large files, show progress:

```python
def read_and_encode_with_progress(file_path):
    file_size = os.path.getsize(file_path)
    chunk_size = 1024 * 1024  # 1MB chunks

    with open(file_path, 'rb') as f:
        content = b''
        bytes_read = 0

        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            content += chunk
            bytes_read += len(chunk)
            progress = (bytes_read / file_size) * 100
            print(f"Encoding: {progress:.1f}%", end='\r')

    print("\nEncoding complete!")
    return base64.b64encode(content).decode('utf-8')
```

---

## Troubleshooting

### Attachment Not Received

1. **Check email client spam folder**
2. **Verify attachment was added** - Check API response logs
3. **Check SMTP limits** - Some providers have size limits
4. **Test with smaller file** - Isolate size-related issues

### Attachment Corrupted

1. **Verify base64 encoding** - Test decode locally
2. **Check content type** - Ensure correct MIME type
3. **Test with different email client** - Compatibility check

### Slow Sending

1. **Reduce attachment size** - Compress files
2. **Use fewer attachments** - Split into multiple emails
3. **Check network speed** - Large files need good bandwidth

---

## Analytics

Attachment metrics are automatically tracked:

```python
# Database columns:
- attachment_count: int          # Number of attachments
- total_attachment_size: int     # Total bytes
- emails_with_attachments: int   # Count for statistics
```

View analytics:
- **Dashboard**: `/admin/analytics`
- **API**: `GET /api/admin/analytics`

---

## FAQ

**Q: Can I send multiple attachments?**
A: Yes, up to 50MB total across all attachments.

**Q: What's the maximum file size?**
A: 25MB per file, 50MB total per email.

**Q: Are attachments encrypted?**
A: Attachments are transmitted as base64 over HTTPS. SMTP transmission depends on TLS/SSL settings.

**Q: Can I send executables?**
A: No, executable content types are blocked for security.

**Q: Does it work with all email clients?**
A: Yes, standard MIME attachments work with all modern email clients.

**Q: How do I compress large PDFs?**
A: Use tools like Ghostscript, Adobe Acrobat, or online compressors.

**Q: Can I send password-protected files?**
A: Yes, the content is just bytes - password protection is transparent to the proxy.

---

## Support

For issues or questions:
- Check logs in dashboard test email feature
- Review `SECURITY_ASSESSMENT_2025-11-21.md` for security details
- See `TEST_EMAIL_FEATURE.md` for test email documentation

---

**Version**: 1.0
**Last Updated**: 2025-11-21
