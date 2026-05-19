"""Dialect-aware column types (JSONB on Postgres, JSON elsewhere for tests)."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class JSONBCompat(TypeDecorator):
    """JSONB on PostgreSQL; plain JSON on SQLite and other dialects."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
