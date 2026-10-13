"""Encrypted secret store and resolution service (A04).

Public surface:

- :func:`build_secret_ref` / :func:`parse_secret_ref` — canonical
  ``secret://tenant/<tenant-id>/account/<account-id>`` references.
- :class:`SecretKeyService` — seals/opens blobs with an active key plus
  retired keys, so a master-key rotation can still read (and re-seal) old
  blobs. Key ids only; key material never leaves the process.
- :class:`SecretStore` — the only component that resolves credentials:
  tenant scope and principal identity must both match the grant, the grant
  must be resolvable, and every allow/deny is audited without secret
  material. Rotation bumps the version in place; revocation freezes the
  account for reconciliation.
"""

from algobots.secrets.keyservice import SecretKeyService
from algobots.secrets.models import SecretGrant
from algobots.secrets.refs import SecretRefError, build_secret_ref, parse_secret_ref
from algobots.secrets.service import Resolution, ResolutionDenied, SecretStore

__all__ = [
    "Resolution",
    "ResolutionDenied",
    "SecretGrant",
    "SecretKeyService",
    "SecretRefError",
    "SecretStore",
    "build_secret_ref",
    "parse_secret_ref",
]
