"""Widen the role snapshot on payout run steps.

The step now stores the seller's commercial role code, which can be longer
than the old career-level codes (e.g. DIRETTORE_COMMERCIALE).

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sn_payout_run_steps", "rank_at_calculation",
        type_=sa.String(32), existing_type=sa.String(16), existing_nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE sn_payout_run_steps SET rank_at_calculation = left(rank_at_calculation, 16) "
        "WHERE length(rank_at_calculation) > 16"
    )
    op.alter_column(
        "sn_payout_run_steps", "rank_at_calculation",
        type_=sa.String(16), existing_type=sa.String(32), existing_nullable=True,
    )
