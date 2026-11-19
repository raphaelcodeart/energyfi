"""SOSNET career level names.

Renames stored career levels to the SOSNET ladder (SosPromoter 1-3,
SosLeader 1-4, SosManager 1-5). Data only; downgrade restores the previous
codes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEVELS = [
    ("S1", "SP1", "SosPromoter 1"),
    ("S2", "SP2", "SosPromoter 2"),
    ("S3", "SP3", "SosPromoter 3"),
    ("TL1", "SL1", "SosLeader 1"),
    ("TL2", "SL2", "SosLeader 2"),
    ("TL3", "SL3", "SosLeader 3"),
    ("TL4", "SL4", "SosLeader 4"),
    ("MD1", "SM1", "SosManager 1"),
    ("MD2", "SM2", "SosManager 2"),
    ("MD3", "SM3", "SosManager 3"),
    ("MD4", "SM4", "SosManager 4"),
    ("MD5", "SM5", "SosManager 5"),
]


def _rename(pairs) -> None:
    for old, new, name in pairs:
        op.execute(
            sa.text("UPDATE sn_career_levels SET code = :new, name = :name WHERE code = :old")
            .bindparams(old=old, new=new, name=name)
        )
        op.execute(
            sa.text("UPDATE sn_payout_run_steps SET rank_at_calculation = :new WHERE rank_at_calculation = :old")
            .bindparams(old=old, new=new)
        )


def upgrade() -> None:
    _rename(LEVELS)


PREVIOUS_NAMES = {
    "S1": "Seller 1", "S2": "Seller 2", "S3": "Seller 3",
    "TL1": "Team Leader 1", "TL2": "Team Leader 2", "TL3": "Team Leader 3", "TL4": "Team Leader 4",
    "MD1": "Manager Director 1", "MD2": "Manager Director 2", "MD3": "Manager Director 3",
    "MD4": "Manager Director 4", "MD5": "Manager Director 5",
}


def downgrade() -> None:
    _rename([(new, old, PREVIOUS_NAMES[old]) for old, new, _ in LEVELS])
