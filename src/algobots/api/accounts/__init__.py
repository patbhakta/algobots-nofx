"""Account registry (S4.1): encrypted credentials, token health, sweeps.

Public surface:
- `crypto` — Fernet sealing + secret redaction
- `models` — `AccountCredential` (encrypted at rest)
- `schemas` — `CredentialSet` (write-only) / `CredentialHealthOut` / `TokenSweepReport`
- `refresh` — broker token-refresher registration
- `service` — credential CRUD + `sweep_token_health` (silent-refresh-or-expire)
- `router` — tenant-scoped credential + sweep routes
"""

from algobots.api.accounts.crypto import CredentialCipher, redact
from algobots.api.accounts.models import AccountCredential
from algobots.api.accounts.refresh import (
    REFRESHERS,
    RefreshOutcome,
    TokenRefresher,
    register_token_refresher,
)
from algobots.api.accounts.schemas import CredentialHealthOut, CredentialSet, TokenSweepReport
from algobots.api.accounts.service import (
    clear_credentials,
    get_decrypted_secrets,
    set_credentials,
    sweep_token_health,
)

__all__ = [
    "AccountCredential",
    "CredentialCipher",
    "CredentialHealthOut",
    "CredentialSet",
    "REFRESHERS",
    "RefreshOutcome",
    "TokenRefresher",
    "TokenSweepReport",
    "clear_credentials",
    "get_decrypted_secrets",
    "redact",
    "register_token_refresher",
    "set_credentials",
    "sweep_token_health",
]
