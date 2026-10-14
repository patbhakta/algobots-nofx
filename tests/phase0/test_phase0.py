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
    from nautilus_trader.model.data import QuoteTick

    from algobots.engine.redis_message_bus import redis_message_bus_config

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


def test_migration_casts_gorm_numeric_booleans():
    """NoFX declares booleans as `numeric DEFAULT false`; without the cast
    pgloader fails with `invalid input syntax for type numeric: "false"`."""
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert "CAST type numeric to boolean" in script


def test_migration_does_not_trust_pgloader_exit_status():
    """pgloader exits 0 even after logging `FATAL Failed to create the schema`."""
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert "PGLOADER_LOG" in script
    assert "grep -qE '(FATAL|ERROR) '" in script


def test_migration_publishes_report_only_after_all_checks_pass():
    """A failed run must not leave a report that looks like a pass."""
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert 'STAGED="$REPORT.partial"' in script
    assert 'mv "$STAGED" "$REPORT"' in script
