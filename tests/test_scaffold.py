"""Scaffold smoke tests: package layout imports and API health endpoint."""

import importlib

import pytest
from fastapi.testclient import TestClient

from algobots.api.main import app

EXPECTED_PACKAGES = [
    "contracts",
    "risk",
    "execution",
    "models",
    "evals",
    "engine",
    "api",
    "dashboard",
]

client = TestClient(app)


@pytest.mark.parametrize("package", EXPECTED_PACKAGES)
def test_package_stub_importable(package: str) -> None:
    mod = importlib.import_module(f"algobots.{package}")
    assert mod.__doc__, f"algobots.{package} must carry a docstring"


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
