"""SQLAlchemy engine/session wiring for the control plane."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from algobots.api.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all control-plane ORM models."""


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # TestClient serves requests from worker threads; generous busy timeout
        # serializes the audit middleware's writes against request sessions.
        return {"connect_args": {"check_same_thread": False, "timeout": 30}}
    return {}


_engine = None
_session_factory: sessionmaker[Session] | None = None


def get_engine():
    """Lazily build the process-wide engine from cached settings."""
    global _engine, _session_factory
    if _engine is None:
        url = get_settings().sqlalchemy_url()
        _engine = create_engine(url, **_engine_kwargs(url))
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Session factory bound to the process engine."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a per-request session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
