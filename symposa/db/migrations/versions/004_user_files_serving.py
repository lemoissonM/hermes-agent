"""User file serving: workspace source, RLS policy.

Revision ID: 004
Revises: 003
Create Date: 2026-05-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_files",
        sa.Column("source", sa.String(32), nullable=False, server_default="s3"),
    )
    op.add_column(
        "user_files",
        sa.Column("workspace_rel_path", sa.String(1024), nullable=True),
    )
    op.execute("""
        CREATE POLICY user_files_owner ON user_files
        USING (
            company_id::text = current_setting('app.company_id', true)
            AND user_id::text = current_setting('app.user_id', true)
        )
        WITH CHECK (
            company_id::text = current_setting('app.company_id', true)
            AND user_id::text = current_setting('app.user_id', true)
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_files_owner ON user_files")
    op.drop_column("user_files", "workspace_rel_path")
    op.drop_column("user_files", "source")
