"""Shared fixtures: Alembic-migrated SQLite DB, TestClient, tenant principals.

The DB is provisioned once per session with the REAL Alembic migration
(upgrade head), so every API test exercises the migrated schema, not
create_all. The bootstrap invite code only works for the very first user,
so the founder principal is session-scoped; per-test users register via
invites with unique emails.
"""

import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[2]

_DB_PATH = (REPO_ROOT / ".pytest_tmp" / f"control-plane-{uuid.uuid4().hex}.db").resolve()
_DB_URL = f"sqlite:///{_DB_PATH}"

# Must be set before any algobots.api import: cached settings resolve now.
os.environ["ALGOBOTS_DATABASE_URL"] = _DB_URL
os.environ["ALGOBOTS_JWT_SECRET"] = "test-jwt-secret-0123456789-0123456789"
os.environ["ALGOBOTS_BOOTSTRAP_INVITE_CODE"] = "TEST-BOOTSTRAP"
os.environ["ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from algobots.api.config import get_settings  # noqa: E402
from algobots.api.main import app  # noqa: E402

BOOTSTRAP_CODE = get_settings().bootstrap_invite_code
TEST_PASSWORD = "correct-horse-battery"


def _alembic_config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def migrated_db():
    """Provision the API test DB with the real Alembic migration."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(_DB_URL), "head")
    yield _DB_URL
    command.downgrade(_alembic_config(_DB_URL), "base")
    _DB_PATH.unlink(missing_ok=True)


@pytest.fixture()
def client(migrated_db) -> TestClient:
    return TestClient(app)


def _register(client: TestClient, email: str, invite_code: str):
    return client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": email.split("@")[0].title(),
            "invite_code": invite_code,
        },
    )


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def founder(migrated_db) -> dict:
    """First registered user (owner role via bootstrap invite code)."""
    email = "founder@example.com"
    boot = TestClient(app)
    response = _register(boot, email, BOOTSTRAP_CODE)
    assert response.status_code == 201, response.text
    token = _login(boot, email)
    return {"email": email, "token": token, "user": response.json()}


@pytest.fixture(scope="session")
def founder_headers(founder: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {founder['token']}"}


@pytest.fixture()
def member(client: TestClient, founder_headers: dict) -> dict:
    """A fresh per-test user registered via a founder invite."""
    invite = client.post("/api/auth/invites", headers=founder_headers)
    assert invite.status_code == 201, invite.text
    email = f"member-{uuid.uuid4().hex[:10]}@example.com"
    response = _register(client, email, invite.json()["code"])
    assert response.status_code == 201, response.text
    token = _login(client, email)
    return {"email": email, "token": token, "user": response.json()}


@pytest.fixture()
def member_headers(member: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {member['token']}"}
