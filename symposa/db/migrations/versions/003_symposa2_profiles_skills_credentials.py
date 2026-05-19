"""Symposa2 profiles, skills, and tenant credentials.

Revision ID: 003
Revises: 002
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "s2_user_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False, server_default="Hermes"),
        sa.Column("soul_md", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_s2_user_profile"),
    )
    op.create_table(
        "s2_user_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("skill_name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_id", "skill_name", name="uq_s2_user_skill"),
    )
    op.create_table(
        "s2_company_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("credential_type", sa.String(32), nullable=False, server_default="oauth2"),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "provider", name="uq_s2_company_credential"),
    )
    op.create_table(
        "s2_user_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("credential_type", sa.String(32), nullable=False, server_default="oauth2"),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_id", "provider", name="uq_s2_user_credential"),
    )

    op.execute("ALTER TABLE s2_user_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE s2_user_skills ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE s2_user_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE s2_company_credentials ENABLE ROW LEVEL SECURITY")

    for table in ("s2_user_profiles", "s2_user_skills", "s2_user_credentials"):
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                company_id::text = current_setting('app.company_id', true)
                AND user_id::text = current_setting('app.user_id', true)
            )
            """
        )
    op.execute(
        """
        CREATE POLICY company_isolation ON s2_company_credentials
        USING (company_id::text = current_setting('app.company_id', true))
        """
    )


def downgrade() -> None:
    for table in (
        "s2_user_credentials",
        "s2_company_credentials",
        "s2_user_skills",
        "s2_user_profiles",
    ):
        op.drop_table(table)
