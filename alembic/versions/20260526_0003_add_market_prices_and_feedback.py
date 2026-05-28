"""add market_prices and feedback tables

market_prices — admin-maintained crop price table per district (no AI cost)
feedback      — user ratings (helpful / not helpful) after AI responses

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-05-26 00:03:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a1b2"
down_revision: Union[str, None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_prices",
        sa.Column("id",         sa.Integer(),     nullable=False),
        sa.Column("district",   sa.String(50),    nullable=False),
        sa.Column("crop",       sa.String(100),   nullable=False),
        sa.Column("unit",       sa.String(30),    nullable=False, server_default="kg"),
        sa.Column("price_rwf",  sa.Integer(),     nullable=False),
        sa.Column("updated_by", sa.String(100),   nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("district", "crop", name="uq_market_price_district_crop"),
    )
    op.create_index("ix_market_prices_district", "market_prices", ["district"])
    op.create_index("ix_market_prices_id",       "market_prices", ["id"])

    op.create_table(
        "feedback",
        sa.Column("id",           sa.Integer(),     nullable=False),
        sa.Column("session_id",   sa.String(100),   nullable=False),
        sa.Column("phone_number", sa.String(20),    nullable=False),
        sa.Column("category",     sa.String(50),    nullable=False),
        sa.Column("rating",       sa.Integer(),     nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_id",           "feedback", ["id"])
    op.create_index("ix_feedback_phone_number", "feedback", ["phone_number"])
    op.create_index("ix_feedback_session_id",   "feedback", ["session_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("market_prices")
