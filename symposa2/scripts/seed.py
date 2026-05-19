"""Seed demo users and profiles for local Symposa2 development."""

from __future__ import annotations

import argparse
import sys

from symposa.auth.passwords import hash_password
from symposa.db.models import Company, User
from symposa.db.session import session_scope
from symposa.services.identity import link_channel_identity
from symposa2.services.profile import upsert_profile


DEMO_USERS = [
    {
        "company_name": "Acme Corp",
        "email": "alice@acme.example",
        "password": "password123",
        "display_name": "Aria",
        "soul_md": (
            "You are warm and concise. Prefer bullet points for lists. "
            "Always greet the user by name when they ask who you are."
        ),
        "role": "admin",
    },
    {
        "company_name": "Acme Corp",
        "email": "bob@acme.example",
        "password": "password123",
        "display_name": "Hermes",
        "soul_md": (
            "You help with everyday workplace tasks. Explain things simply for "
            "non-technical colleagues."
        ),
        "role": "member",
    },
]


def seed(*, reset: bool = False) -> None:
    with session_scope() as session:
        company = session.query(Company).filter(Company.name == "Acme Corp").first()
        if company is None:
            company = Company(name="Acme Corp")
            session.add(company)
            session.flush()

        for spec in DEMO_USERS:
            user = (
                session.query(User)
                .filter(User.company_id == company.id, User.email == spec["email"])
                .first()
            )
            if user is None:
                user = User(
                    company_id=company.id,
                    email=spec["email"],
                    password_hash=hash_password(spec["password"]),
                    role=spec["role"],
                )
                session.add(user)
                session.flush()
                link_channel_identity(session, company.id, user.id, "web", str(user.id))
            elif reset:
                user.password_hash = hash_password(spec["password"])

            upsert_profile(
                session,
                company.id,
                user.id,
                display_name=spec["display_name"],
                soul_md=spec["soul_md"],
            )
            print(f"Seeded {spec['email']} ({spec['display_name']}) company={company.id} user={user.id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Symposa2 demo data")
    parser.add_argument("--reset-passwords", action="store_true")
    args = parser.parse_args()
    try:
        seed(reset=args.reset_passwords)
    except Exception as exc:
        print(f"Seed failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
