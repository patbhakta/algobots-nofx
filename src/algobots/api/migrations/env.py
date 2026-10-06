"""Alembic environment: URL from app settings, metadata from ORM models."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from algobots.api import models  # noqa: F401 — register mappers on Base
from algobots.api.config import get_settings
from algobots.api.database import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolved_url() -> str:
    """Prefer an explicit `-x`/ini URL override; fall back to app settings."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return get_settings().sqlalchemy_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
