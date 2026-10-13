"""Password hashing (scrypt, stdlib) and JWT issuing/verification (PyJWT).

Auth contract (A03 owns `auth-contract`): an access token is an HS256 JWT with
`sub` (user id), `sid` (an `auth_sessions` row checked on every request),
`iat`, `exp` and `iss`. The token never carries a tenant: the active tenant is
server-side session state, re-validated against the membership each request.
"""

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from algobots.api.config import get_settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """Return `scrypt$N$r$p$salt_b64$dk_b64` (salted, memory-hard)."""
    salt = os.urandom(16)
    dk = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            base64.b64encode(salt).decode(),
            base64.b64encode(dk).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification against a stored scrypt hash."""
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(dk_b64)),
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    """Issue a signed HS256 access token bound to one server-side session."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_claims(token: str) -> dict | None:
    """Return verified claims with string `sub` and `sid`, or None if invalid/expired."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "sub", "sid", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("sid"), str):
        return None
    return claims


def decode_access_token(token: str) -> str | None:
    """Return the user id (`sub`) claim, or None for any invalid/expired token."""
    claims = decode_access_claims(token)
    return None if claims is None else claims["sub"]
