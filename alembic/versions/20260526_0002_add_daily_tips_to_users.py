"""add daily_tips_enabled and daily_tip_category to users

Adds opt-in daily tip subscription columns.
  daily_tips_enabled  — boolean, default false
  daily_tip_category  — varchar(50), nullable (NULL = derive from profession)

Existing rows remain unaffected (opted-out by default).

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-26 00:02:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "daily_tips_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="User opted in to receive one tip per day via SMS",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "daily_tip_category",
            sa.String(50),
            nullable=True,
            comment="Preferred tip category (NULL = derived from profession)",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "daily_tip_category")
    op.drop_column("users", "daily_tips_enabled")
