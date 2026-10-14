import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]

# CI installs only the `dev` extra, so nautilus_trader is absent there; it
# ships in the `workers` extra. Config assertions skip rather than fail.
requires_nautilus = pytest.mark.skipif(
    importlib.util.find_spec("nautilus_trader") is None,
    reason="nautilus_trader ships in the `workers` extra, not `dev`",
)


def test_inventory_covers_live_snapshot():
    text = (ROOT / "INVENTORY.md").read_text()
    for container in (
        "nofx-frontend", "nofx-trading", "nautilus-marimo", "algobots-api-1",
        "jkp-api", "algobots-postgres-1", "algobots-redis-1", "tdai-memory-hub",
        "tdai-proxy", "tdai-memory-core",
    ):
        assert f"`{container}`" in text


def compose():
    return yaml.safe_load((ROOT / "compose.yaml").read_text())


def test_single_compose_shared_network_and_named_state():
    model = compose()
    services = model["services"]
    assert {"postgres", "redis", "api", "nofx", "nofx-frontend", "nautilus"} <= services.keys()
    assert all("algobots" in service["networks"] for service in services.values())
    assert {"postgres_data", "redis_data", "nautilus_catalog"} <= model["volumes"].keys()


def test_compose_does_not_flip_nofx_to_postgres_by_default():
    """The card's acceptance is that `pat@bhakta.us` survives.

    compose.yaml IS the deployment artifact, so a hardcoded `DB_TYPE: postgres`
    points the live NoFX at the freshly-created empty `nofx` database on the
    next `up` and the only member can no longer log in. The cutover is an env
    flip after scripts/migrate-nofx-sqlite.sh reports a verified migration.
    """
    nofx = compose()["services"]["nofx"]
    assert nofx["environment"]["DB_TYPE"] == "${NOFX_DB_TYPE:-sqlite}"
    mounts = " ".join(nofx["volumes"])
    assert ":/app/data" in mounts, "the live SQLite database must stay mounted"
    assert ":/app/bridge" in mounts, "ALG-3340's bridge channel must stay mounted"


def test_compose_keeps_the_live_api_and_nautilus_mounts():
    """INVENTORY.md records what the host runs; compose must not silently drop
    the bridge, the Kalshi feed or the demo state when it adopts the stack."""
    services = compose()["services"]
    api = " ".join(services["api"]["volumes"])
    assert "/bridge" in api and "/feeds/kalshi" in api and "/var/lib/algobots-demo" in api
    work = next(m for m in services["nautilus"]["volumes"] if m.endswith("/home/nautilus/work"))
    assert not work.startswith("./"), "work dir is a host path, not a path in this checkout"


def test_env_example_documents_every_required_variable():
    env = (ROOT / ".env.example").read_text()
    for required in ("POSTGRES_PASSWORD=", "NOFX_JWT_SECRET=", "NOFX_DB_TYPE=sqlite"):
        assert required in env
    assert "POSTGRES_PASSWORD=\n" in env, "no default password may ship in the repo"


@requires_nautilus
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


def test_migration_row_counts_resolve_the_downcased_relation():
    """pgloader downcases identifiers: quoting a mixed-case SQLite table name
    verbatim into Postgres reports a mismatch on a migration that worked."""
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert "lower(table_name)=lower('$table')" in script
    assert 'FROM \\"$pg_table\\"' in script


def test_migration_publishes_report_only_after_all_checks_pass():
    """A failed run must not leave a report that looks like a pass."""
    script = (ROOT / "scripts/migrate-nofx-sqlite.sh").read_text()
    assert 'STAGED="$REPORT.partial"' in script
    assert 'mv "$STAGED" "$REPORT"' in script
