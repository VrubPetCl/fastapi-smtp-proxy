"""Encryption utilities for sensitive data."""
from cryptography.fernet import Fernet
from app.config import settings
import base64
import os


class CredentialEncryption:
    """Handle encryption/decryption of sensitive credentials."""

    def __init__(self):
        """Initialize encryption with key from settings."""
        # Get encryption key from settings or generate one
        key = settings.encryption_key if hasattr(settings, 'encryption_key') else None

        if not key:
            raise ValueError(
                "ENCRYPTION_KEY not set in environment. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()

        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: The plaintext string to encrypt

        Returns:
            str: Base64-encoded encrypted string
        """
        if not plaintext:
            return ""

        encrypted = self.cipher.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted string.

        Args:
            encrypted: The encrypted string to decrypt

        Returns:
            str: Decrypted plaintext string
        """
        if not encrypted:
            return ""

        decrypted = self.cipher.decrypt(encrypted.encode())
        return decrypted.decode()


# Global encryption instance
_encryption = None


def get_encryption() -> CredentialEncryption:
    """Get or create global encryption instance."""
    global _encryption
    if _encryption is None:
        _encryption = CredentialEncryption()
    return _encryption
