"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Generator, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from symposa.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_rls_context(session: Session, company_id: str, user_id: str) -> None:
    """Apply Postgres RLS session variables (no-op on SQLite tests)."""
    bind = session.get_bind()
    if bind is not None and bind.dialect.name != "postgresql":
        return
    session.execute(
        text("SELECT set_config('app.company_id', :cid, true)"),
        {"cid": company_id},
    )
    session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"),
        {"uid": user_id},
    )
