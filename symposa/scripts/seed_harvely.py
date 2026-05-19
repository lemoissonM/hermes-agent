#!/usr/bin/env python3
"""Ensure harvely company has default Symposa workspace agent preset."""

from __future__ import annotations

from symposa.db.session import session_scope
from symposa.services.company_defaults import ensure_harvely_seed


def main() -> None:
    with session_scope() as session:
        ensure_harvely_seed(session)
        session.commit()
    print("harvely seed complete (no-op if company missing)")


if __name__ == "__main__":
    main()
