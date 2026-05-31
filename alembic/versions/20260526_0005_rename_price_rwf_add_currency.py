"""rename price_rwf to price and add currency column

Makes market_prices currency-agnostic: any ISO 4217 code is supported.
Existing rows keep their values; currency defaults to 'RWF' for backcompat.

Revision ID: e5f6a7b8c3d4
Revises: d4e5f6a7b2c3
Create Date: 2026-05-26 00:05:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c3d4"
down_revision: Union[str, None] = "d4e5f6a7b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("market_prices", "price_rwf", new_column_name="price")
    op.add_column(
        "market_prices",
        sa.Column(
            "currency",
            sa.String(10),
            nullable=False,
            server_default="RWF",
        ),
    )


def downgrade() -> None:
    op.drop_column("market_prices", "currency")
    op.alter_column("market_prices", "price", new_column_name="price_rwf")
