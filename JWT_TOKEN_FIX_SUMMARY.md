# JWT Token Implementation Fix - Summary

## Problem Identified

The API endpoint expected **JWT tokens** but the web interface was generating **random string tokens**, causing authentication failures.

### Technical Details

**Before:**
- Web interface (`app/web.py:1197`): Generated random strings like `smtp_{secrets.token_urlsafe(32)}`
- Stored raw string in database `APIKey.key_hash` field
- API endpoint (`app/auth.py:110`): Expected JWT tokens with signature verification
- Result: **401 Unauthorized** - JWT decode failed on random strings

## Solution Implemented

### 1. Updated Web Interface (`app/web.py`)

Modified `/admin/clients/{client_id}/keys/new` endpoint to:
- Use existing `create_api_key()` function from `app/auth.py`
- Generate proper JWT tokens instead of random strings
- Store SHA256 hash of JWT in database
- Support optional expiration dates

**Key Changes:**
```python
# OLD (lines 1196-1197)
api_key = f"smtp_{secrets.token_urlsafe(32)}"

# NEW (lines 1207-1211)
jwt_token, key_hash = create_jwt_api_key(
    client_id=client_id,
    key_name=description or f"API Key {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
    expires_at=expires_at_dt
)
```

### 2. Enhanced API Key Form (`app/templates/api_key_form.html`)

Added:
- **Expiration Date** field (optional)
- Date picker with minimum date validation
- Updated instructions for JWT usage
- Bearer token authorization example

### 3. Test Verification

Created `test_jwt_fix.py` to verify:
- ✅ JWT token generation and signing
- ✅ JWT token verification and decoding
- ✅ Expired token rejection
- ✅ Invalid token rejection
- ✅ Hash comparison for database lookup

**Test Results:**
```
All tests passed!
- JWT tokens are properly generated and signed
- JWT tokens can be verified and decoded
- Expired tokens are rejected
- Invalid tokens are rejected
- Token hashes match for database lookup
```

## Token Flow

### 1. Token Generation (Web Interface)
```
Admin creates API key
    ↓
create_api_key() generates JWT with:
  - client_id: 1
  - key_name: "Production Site"
  - exp: 1 year from now
  - iat: current timestamp
    ↓
JWT signed with JWT_SECRET_KEY
    ↓
SHA256 hash stored in database
    ↓
JWT shown to admin (one time only)
```

### 2. Token Validation (API Endpoint)
```
Client sends request with JWT
    ↓
verify_jwt_token() decodes and validates:
  - Signature verification
  - Expiration check
  - Payload extraction
    ↓
SHA256 hash of JWT computed
    ↓
Database lookup by hash
    ↓
Client authenticated ✓
```

## Benefits of JWT Approach

1. **Stateless Validation**: Token contains all necessary information
2. **Built-in Expiration**: Native JWT `exp` claim
3. **Tamper-Proof**: Signed with secret key
4. **Industry Standard**: Well-understood, widely used
5. **Metadata Support**: Can embed client_id, key_name, etc.
6. **Security**: Cannot be modified without invalidating signature

## Configuration

Default JWT expiration: **8760 hours (365 days / 1 year)**

Configure in `app/config.py`:
```python
jwt_expiration_hours: int = 8760  # 1 year default
```

Or set custom expiration per key in the web form.

## Usage Instructions

### For Administrators

1. Navigate to client details page
2. Click "Generate API Key"
3. Enter description (optional)
4. Set expiration date (optional, defaults to 1 year)
5. Click "Generate API Key"
6. **Copy the JWT token immediately** (shown only once)

### For API Clients

Use the JWT token in the Authorization header:

```bash
curl -X POST https://your-domain.com/api/send \
  -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["recipient@example.com"],
    "subject": "Test Email",
    "content": "Hello World",
    "timestamp": 1234567890
  }'
```

## Files Modified

1. **app/web.py**
   - Updated `create_api_key()` to use JWT generation
   - Added `expires_at` form parameter
   - Updated template context to include `now`

2. **app/templates/api_key_form.html**
   - Added expiration date field
   - Updated instructions for JWT usage
   - Added Bearer token example

3. **test_jwt_fix.py** (new)
   - Comprehensive JWT test suite

## Migration Notes

**Existing random string tokens will NOT work with this fix.**

If you have existing API keys in the database:
- They were generated as random strings
- They are NOT valid JWTs
- Clients using them will get 401 Unauthorized

**Action Required:**
1. Revoke all existing API keys
2. Generate new JWT-based API keys
3. Distribute new keys to clients

## Testing

Run the test suite:
```bash
venv/bin/python test_jwt_fix.py
```

Expected output: All tests passed ✓

## Summary

✅ Web interface now generates valid JWT tokens
✅ API endpoint accepts and validates JWT tokens
✅ Token expiration configurable per key
✅ Secure hash storage in database
✅ One-time token display for security
✅ All tests passing

**The token mismatch issue has been resolved.**
