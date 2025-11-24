#!/usr/bin/env python
"""Test script to verify JWT token generation and validation."""
import asyncio
from datetime import datetime, timedelta
from app.auth import create_api_key, verify_jwt_token
from app.config import settings

async def test_jwt_flow():
    """Test the complete JWT flow."""
    print("=" * 60)
    print("Testing JWT Token Generation and Validation")
    print("=" * 60)

    # Test 1: Create a JWT token
    print("\n1. Creating JWT API key...")
    client_id = 1
    key_name = "Test API Key"
    expires_at = datetime.utcnow() + timedelta(days=365)  # 1 year

    jwt_token, key_hash = create_api_key(
        client_id=client_id,
        key_name=key_name,
        expires_at=expires_at
    )

    print(f"   ✓ JWT Token generated: {jwt_token[:50]}...{jwt_token[-20:]}")
    print(f"   ✓ Key Hash (SHA256): {key_hash[:32]}...{key_hash[-16:]}")
    print(f"   ✓ Token length: {len(jwt_token)} characters")

    # Test 2: Verify the JWT token
    print("\n2. Verifying JWT token...")
    try:
        payload = verify_jwt_token(jwt_token)
        print(f"   ✓ Token verified successfully!")
        print(f"   ✓ Payload: {payload}")
        print(f"     - client_id: {payload.get('client_id')}")
        print(f"     - key_name: {payload.get('key_name')}")
        print(f"     - issued_at: {datetime.fromtimestamp(payload.get('iat'))}")
        print(f"     - expires_at: {datetime.fromtimestamp(payload.get('exp'))}")
    except Exception as e:
        print(f"   ✗ Token verification failed: {e}")
        return False

    # Test 3: Test with expired token
    print("\n3. Testing expired token...")
    expired_jwt, expired_hash = create_api_key(
        client_id=client_id,
        key_name="Expired Key",
        expires_at=datetime.utcnow() - timedelta(seconds=1)  # Already expired
    )

    try:
        verify_jwt_token(expired_jwt)
        print("   ✗ Expired token should have failed!")
        return False
    except Exception as e:
        print(f"   ✓ Expired token rejected correctly: {e}")

    # Test 4: Test with invalid token
    print("\n4. Testing invalid token...")
    invalid_token = "smtp_invalidtoken123"
    try:
        verify_jwt_token(invalid_token)
        print("   ✗ Invalid token should have failed!")
        return False
    except Exception as e:
        print(f"   ✓ Invalid token rejected correctly: {e}")

    # Test 5: Test hash comparison (simulating database lookup)
    print("\n5. Testing hash comparison...")
    import hashlib

    # Simulate what the API endpoint does
    token_hash_for_db = hashlib.sha256(jwt_token.encode()).hexdigest()

    if token_hash_for_db == key_hash:
        print(f"   ✓ Token hash matches stored hash!")
        print(f"   ✓ Database lookup would succeed")
    else:
        print(f"   ✗ Token hash mismatch!")
        return False

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print("\nSummary:")
    print("- JWT tokens are properly generated and signed")
    print("- JWT tokens can be verified and decoded")
    print("- Expired tokens are rejected")
    print("- Invalid tokens are rejected")
    print("- Token hashes match for database lookup")
    print("\n✓ The web interface will now generate valid JWT tokens")
    print("✓ The API endpoint will accept these tokens")

    return True

if __name__ == "__main__":
    success = asyncio.run(test_jwt_flow())
    exit(0 if success else 1)
