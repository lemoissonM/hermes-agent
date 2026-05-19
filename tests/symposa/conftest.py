"""Symposa test fixtures — isolated SQLite (no ~/.hermes writes)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from symposa.db.base import Base
from symposa.db import models as _models  # noqa: F401 — register all ORM tables
from symposa.db.models import Company, User
from symposa.auth.passwords import hash_password


@pytest.fixture
def symposa_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    company = Company(id=uuid4(), name="Test Co")
    session.add(company)
    user_a = User(
        id=uuid4(),
        company_id=company.id,
        email="a@test.com",
        password_hash=hash_password("password123"),
        role="member",
    )
    user_b = User(
        id=uuid4(),
        company_id=company.id,
        email="b@test.com",
        password_hash=hash_password("password123"),
        role="member",
    )
    session.add_all([user_a, user_b])
    session.commit()
    yield session, company, user_a, user_b
    session.close()


@pytest.fixture(autouse=True)
def _symposa_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    monkeypatch.setenv("SYMPOSA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SYMPOSA_JWT_SECRET", "test-secret")
    monkeypatch.setenv("SYMPOSA_DATABASE_URL", "sqlite:///:memory:")
