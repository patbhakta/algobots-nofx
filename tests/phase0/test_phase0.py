from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_inventory_covers_live_snapshot():
    text = (ROOT / "INVENTORY.md").read_text()
    for container in (
        "nofx-frontend", "nofx-trading", "nautilus-marimo", "algobots-api-1",
        "jkp-api", "algobots-postgres-1", "algobots-redis-1", "tdai-memory-hub",
        "tdai-proxy", "tdai-memory-core",
    ):
        assert f"`{container}`" in text


def test_single_compose_shared_network_and_named_state():
    model = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services = model["services"]
    assert {"postgres", "redis", "api", "nofx", "nofx-frontend", "nautilus"} <= services.keys()
    assert all("algobots" in service["networks"] for service in services.values())
    assert {"postgres_data", "redis_data", "nautilus_catalog"} <= model["volumes"].keys()
    assert services["nofx"]["environment"]["DB_TYPE"] == "postgres"


def test_message_bus_is_json_and_filters_quotes(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "redis-test")
    from algobots.engine.redis_message_bus import redis_message_bus_config
    from nautilus_trader.model.data import QuoteTick

    config = redis_message_bus_config()
    assert config.encoding == "json"
    assert config.database.host == "redis-test"
    assert config.stream_per_topic is True
    assert QuoteTick in config.types_filter


def test_migration_requires_explicit_copy_guard():
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert "CONFIRM_TEST_COPY" in script
    assert "pat@bhakta.us" in script
    assert "destination public schema is not empty" in script
