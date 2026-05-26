"""add sms_opt_out to users

Adds the sms_opt_out boolean preference column.  Existing rows default to
False (SMS enabled), matching the column server_default.

Revision ID: a1b2c3d4e5f6
Revises: 790a144d444d
Create Date: 2026-05-26 00:01:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "790a144d444d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "sms_opt_out",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="When True, skip full-answer SMS even if response exceeds char limit",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "sms_opt_out")
