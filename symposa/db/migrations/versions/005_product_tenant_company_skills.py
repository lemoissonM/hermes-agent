"""Product tenant metadata and company skills.

Revision ID: 005
Revises: 004
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("slug", sa.String(128), nullable=True))
    op.add_column("companies", sa.Column("environment", sa.String(32), nullable=False, server_default="live"))
    op.add_column("companies", sa.Column("region", sa.String(128), nullable=True))
    op.add_column("companies", sa.Column("timezone", sa.String(128), nullable=True))
    op.add_column("companies", sa.Column("currency", sa.String(16), nullable=True))
    op.add_column("companies", sa.Column("language", sa.String(64), nullable=True))
    op.add_column("companies", sa.Column("status", sa.String(32), nullable=False, server_default="active"))
    op.add_column("companies", sa.Column("overview_md", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("governance_md", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE companies
        SET slug = trim(both '-' from lower(regexp_replace(coalesce(name, 'tenant'), '[^a-zA-Z0-9]+', '-', 'g'))) || '-' || left(id::text, 8)
        WHERE slug IS NULL
        """
    )
    op.create_unique_constraint("uq_companies_slug", "companies", ["slug"])

    op.create_table(
        "s2_company_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("skill_name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "skill_name", name="uq_s2_company_skill"),
    )
    op.execute("ALTER TABLE s2_company_skills ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY company_isolation ON s2_company_skills
        USING (company_id::text = current_setting('app.company_id', true))
        WITH CHECK (company_id::text = current_setting('app.company_id', true))
        """
    )


def downgrade() -> None:
    op.drop_table("s2_company_skills")
    op.drop_constraint("uq_companies_slug", "companies", type_="unique")
    for column in (
        "governance_md",
        "overview_md",
        "status",
        "language",
        "currency",
        "timezone",
        "region",
        "environment",
        "slug",
    ):
        op.drop_column("companies", column)
