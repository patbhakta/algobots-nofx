"""Key service over the sealed-credential blobs (A04).

Wraps :class:`algobots.api.accounts.crypto.CredentialCipher` with one active
key plus a table of retired keys keyed by ``key_id``. A master-key rotation
therefore never orphans stored blobs: opening succeeds under the retired key
and the blob is re-sealed under the active key. Key ids (a sha256 prefix)
are the only key-derived value that is ever stored, logged or returned.
"""

from __future__ import annotations

from typing import Any

from algobots.api.accounts.crypto import CredentialCipher


class KeyServiceError(RuntimeError):
    """The key service is misconfigured (no active key / unknown key id)."""


class SecretKeyService:
    """Active-plus-retired key ring for sealed secret blobs."""

    def __init__(self, active: CredentialCipher, retired: tuple[CredentialCipher, ...] = ()):
        self._active = active
        self._by_key_id: dict[str, CredentialCipher] = {active.key_id: active}
        for cipher in retired:
            self._by_key_id.setdefault(cipher.key_id, cipher)

    @property
    def active_key_id(self) -> str:
        return self._active.key_id

    def seal(self, secrets: dict[str, Any]) -> tuple[str, str]:
        """Return ``(blob, key_id)`` sealed under the active key."""
        return self._active.encrypt(secrets), self._active.key_id

    def open(self, blob: str, key_id: str) -> dict[str, Any]:
        """Open a blob with the key that sealed it.

        Raises :class:`KeyServiceError` when the sealing key is unknown (the
        blob predates the ring) or the blob fails authentication.
        """
        cipher = self._by_key_id.get(key_id)
        if cipher is None:
            raise KeyServiceError(f"no key {key_id} in the ring; blob cannot be opened")
        plain = cipher.try_decrypt(blob)
        if plain is None:
            raise KeyServiceError("blob failed authentication under its recorded key")
        return plain


_ring: SecretKeyService | None = None


def get_key_service() -> SecretKeyService:
    """Process-wide ring built from the configured credential key (single-key)."""
    global _ring
    if _ring is None:
        from algobots.api.accounts.crypto import get_credential_cipher

        _ring = SecretKeyService(get_credential_cipher())
    return _ring


def set_key_service(ring: SecretKeyService | None) -> None:
    """Install (or clear, with ``None``) the process ring — key-rotation/test hook."""
    global _ring
    _ring = ring
