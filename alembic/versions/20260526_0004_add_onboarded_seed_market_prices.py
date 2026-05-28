"""add onboarded column and seed market prices

onboarded — Boolean flag set True once a user completes the initial
            language + profession setup screen.
            All existing users are back-filled to True so they don't
            see the onboarding screen after deploy.

market_prices seed — 5 Rwanda districts × 6 crops (30 rows).
                     Uses ON CONFLICT so re-running is safe.

Revision ID: d4e5f6a7b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-05-26 00:04:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b2c3"
down_revision: Union[str, None] = "c3d4e5f6a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── onboarded column ──────────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column(
            "onboarded",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # All existing users have already gone through (or skipped) setup
    op.execute("UPDATE users SET onboarded = true")

    # ── seed market prices ────────────────────────────────────────────────────
    op.execute(
        """
        INSERT INTO market_prices (district, crop, unit, price_rwf, updated_by)
        VALUES
          ('kigali',  'Maize',          'kg', 400, 'seed'),
          ('kigali',  'Beans',          'kg', 800, 'seed'),
          ('kigali',  'Irish Potatoes', 'kg', 300, 'seed'),
          ('kigali',  'Tomatoes',       'kg', 600, 'seed'),
          ('kigali',  'Cassava',        'kg', 200, 'seed'),
          ('kigali',  'Sweet Potatoes', 'kg', 300, 'seed'),

          ('musanze', 'Maize',          'kg', 350, 'seed'),
          ('musanze', 'Beans',          'kg', 700, 'seed'),
          ('musanze', 'Irish Potatoes', 'kg', 220, 'seed'),
          ('musanze', 'Tomatoes',       'kg', 500, 'seed'),
          ('musanze', 'Cassava',        'kg', 180, 'seed'),
          ('musanze', 'Sweet Potatoes', 'kg', 250, 'seed'),

          ('huye',    'Maize',          'kg', 330, 'seed'),
          ('huye',    'Beans',          'kg', 720, 'seed'),
          ('huye',    'Irish Potatoes', 'kg', 280, 'seed'),
          ('huye',    'Tomatoes',       'kg', 520, 'seed'),
          ('huye',    'Cassava',        'kg', 160, 'seed'),
          ('huye',    'Sweet Potatoes', 'kg', 230, 'seed'),

          ('rubavu',  'Maize',          'kg', 320, 'seed'),
          ('rubavu',  'Beans',          'kg', 680, 'seed'),
          ('rubavu',  'Irish Potatoes', 'kg', 270, 'seed'),
          ('rubavu',  'Tomatoes',       'kg', 490, 'seed'),
          ('rubavu',  'Cassava',        'kg', 150, 'seed'),
          ('rubavu',  'Sweet Potatoes', 'kg', 240, 'seed'),

          ('kayonza', 'Maize',          'kg', 310, 'seed'),
          ('kayonza', 'Beans',          'kg', 660, 'seed'),
          ('kayonza', 'Irish Potatoes', 'kg', 290, 'seed'),
          ('kayonza', 'Tomatoes',       'kg', 480, 'seed'),
          ('kayonza', 'Cassava',        'kg', 170, 'seed'),
          ('kayonza', 'Sweet Potatoes', 'kg', 220, 'seed')
        ON CONFLICT (district, crop)
        DO UPDATE SET
          price_rwf  = EXCLUDED.price_rwf,
          updated_by = EXCLUDED.updated_by,
          updated_at = now()
        """
    )


def downgrade() -> None:
    op.drop_column("users", "onboarded")
    # Seed data is not removed on downgrade — prices are operational data.
