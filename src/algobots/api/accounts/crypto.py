"""Credential encryption at rest for the account registry (ALG-3090, S4.1).

Secrets are sealed with Fernet (AES-128-CBC + HMAC-SHA256,encrypt-then-MAC)
before they touch the database; plaintext never reaches disk, logs, or API
responses. The master key is supplied via `ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY`
(urlsafe-base64, 32 bytes). Each stored blob records the `key_id` of the key
that sealed it (sha256 prefix) so key rotation and stale-key failures are
detectable without exposing key material.
"""

import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("algobots.api.accounts.crypto")

REDACTED = "***REDACTED***"
_MAX_ERROR_TEXT = 300


def redact(text: str, *secret_values: str) -> str:
    """Replace every occurrence of a known secret value, then truncate.

    Applied to any text that will be persisted or logged (e.g. refresh error
    messages raised by broker adapters that may echo request material).
    """
    out = text or ""
    for secret in secret_values:
        if secret:
            out = out.replace(secret, REDACTED)
    return out[:_MAX_ERROR_TEXT]


class CredentialCipher:
    """Fernet facade over JSON secret dicts. Never logs its contents."""

    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())
        self.key_id = hashlib.sha256(key.encode()).hexdigest()[:12]

    @classmethod
    def generate_key(cls) -> str:
        """Produce a fresh urlsafe-base64 Fernet key (ops helper)."""
        return Fernet.generate_key().decode()

    def encrypt(self, secrets: dict[str, Any]) -> str:
        payload = json.dumps(secrets, sort_keys=True, separators=(",", ":"))
        return self._fernet.encrypt(payload.encode()).decode()

    def decrypt(self, blob: str) -> dict[str, Any]:
        plain = self._fernet.decrypt(blob.encode())
        return json.loads(plain)

    def try_decrypt(self, blob: str) -> dict[str, Any] | None:
        """Decrypt, mapping a failed/tampered/foreign-key blob to None."""
        try:
            return self.decrypt(blob)
        except (InvalidToken, ValueError, TypeError):
            return None


_cipher: CredentialCipher | None = None


def get_credential_cipher() -> CredentialCipher:
    """Process-wide cipher built from cached settings (raises if unconfigured)."""
    global _cipher
    if _cipher is None:
        from algobots.api.config import get_settings

        key = get_settings().credential_encryption_key
        if not key:
            raise RuntimeError(
                "ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY is not set; generate one with "
                '`python -c "from algobots.api.accounts.crypto import '
                'CredentialCipher; print(CredentialCipher.generate_key())"`'
            )
        _cipher = CredentialCipher(key)
    return _cipher


def reset_credential_cipher() -> None:
    """Drop the cached cipher (test hook; also used after key rotation)."""
    global _cipher
    _cipher = None
