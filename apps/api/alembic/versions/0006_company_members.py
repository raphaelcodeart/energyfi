"""Collaborators taking part in a company's plans.

Revision ID: 0006
Revises: 0005
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sn_supplier_members",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["sn_tenants.id"], name=op.f("fk_sn_supplier_members_organization_id_sn_tenants")),
        sa.ForeignKeyConstraint(["company_id"], ["sn_suppliers.id"], name=op.f("fk_sn_supplier_members_company_id_sn_suppliers")),
        sa.ForeignKeyConstraint(["agent_id"], ["sn_promoter_profiles.id"], name=op.f("fk_sn_supplier_members_agent_id_sn_promoter_profiles")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sn_supplier_members")),
    )
    op.create_index(op.f("ix_sn_supplier_members_organization_id"), "sn_supplier_members", ["organization_id"], unique=False)
    op.create_index(op.f("ix_sn_supplier_members_company_id"), "sn_supplier_members", ["company_id"], unique=False)
    op.create_index(op.f("ix_sn_supplier_members_agent_id"), "sn_supplier_members", ["agent_id"], unique=False)
    # One open membership per collaborator and company.
    op.create_index(
        "uq_sn_supplier_members_open", "sn_supplier_members", ["company_id", "agent_id"], unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sn_supplier_members_open", table_name="sn_supplier_members")
    op.drop_index(op.f("ix_sn_supplier_members_agent_id"), table_name="sn_supplier_members")
    op.drop_index(op.f("ix_sn_supplier_members_company_id"), table_name="sn_supplier_members")
    op.drop_index(op.f("ix_sn_supplier_members_organization_id"), table_name="sn_supplier_members")
    op.drop_table("sn_supplier_members")
