"""Companies behind products.

Adds sn_suppliers (the company behind a product, with the maximum network
depth its products reach) and sn_offers.company_id.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sn_suppliers",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("logo_url", sa.String(length=1000), nullable=True),
        sa.Column("website_url", sa.String(length=1000), nullable=True),
        sa.Column("max_network_depth", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_network_depth IS NULL OR max_network_depth >= 1", name=op.f("ck_sn_suppliers_depth_positive")),
        sa.ForeignKeyConstraint(["organization_id"], ["sn_tenants.id"], name=op.f("fk_sn_suppliers_organization_id_sn_tenants")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sn_suppliers")),
        sa.UniqueConstraint("organization_id", "name", name="uq_sn_suppliers_org_name"),
    )
    op.create_index(op.f("ix_sn_suppliers_organization_id"), "sn_suppliers", ["organization_id"], unique=False)
    op.add_column("sn_offers", sa.Column("company_id", sa.UUID(), nullable=True))
    op.create_foreign_key(op.f("fk_sn_offers_company_id_sn_suppliers"), "sn_offers", "sn_suppliers", ["company_id"], ["id"])
    op.create_index(op.f("ix_sn_offers_company_id"), "sn_offers", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sn_offers_company_id", table_name="sn_offers")
    op.drop_constraint("fk_sn_offers_company_id_sn_suppliers", "sn_offers", type_="foreignkey")
    op.drop_column("sn_offers", "company_id")
    op.drop_index("ix_sn_suppliers_organization_id", table_name="sn_suppliers")
    op.drop_table("sn_suppliers")
