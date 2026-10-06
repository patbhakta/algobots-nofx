"""Control-plane settings loaded from environment (12-factor).

Env vars use the `ALGOBOTS_` prefix. `DATABASE_URL` (used by deploy/docker-compose.yml)
is accepted as a fallback alias for `ALGOBOTS_DATABASE_URL`.
"""

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the AlgoBots control plane."""

    model_config = SettingsConfigDict(env_prefix="ALGOBOTS_", extra="ignore")

    database_url: str = Field(
        default="sqlite:///./algobots.db",
        validation_alias=AliasChoices("ALGOBOTS_DATABASE_URL", "DATABASE_URL"),
    )
    jwt_secret: str = Field(default="dev-secret-change-me-32-bytes-min!!")
    jwt_algorithm: str = Field(default="HS256")
    jwt_issuer: str = Field(default="algobots")
    access_token_expire_minutes: int = Field(default=60)
    bootstrap_invite_code: str = Field(default="ALGOBOTS-BOOTSTRAP")
    invite_expire_days: int = Field(default=7)
    # S4.1 account registry: urlsafe-base64 32-byte Fernet key. Generate with
    # `python -c "from algobots.api.accounts.crypto import CredentialCipher; \
    # print(CredentialCipher.generate_key())"`. Empty disables credential writes
    # (they fail loudly) so a missing key can never degrade to plaintext.
    credential_encryption_key: str = Field(default="")
    # A token expiring within this window is refreshed proactively.
    token_refresh_margin_seconds: int = Field(default=300)
    # ALG-3248 live paper demo: Laya forward-observer feed, kill-switch state
    # dir, and the UTC date the paper account opened.
    demo_feed_path: str = Field(default="/opt/laya/kalshi/observations.jsonl")
    demo_state_dir: str = Field(default="./.demo-state")
    demo_start: str = Field(default="2026-10-03")
    # Comma-separated UTC timestamps (YYYY-MM-DDTHH:MM) at which every demo
    # sleeve is topped back up to its starting capital. Empty = never.
    demo_sleeve_refills: str = Field(default="")

    def sqlalchemy_url(self) -> str:
        """Normalize the configured URL for SQLAlchemy drivers.

        `postgresql://` URLs (docker-compose default) are upgraded to the
        psycopg3 dialect; other URLs pass through unchanged.
        """
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor; reads env at first call."""
    return Settings()
