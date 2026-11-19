"""Bootstrapping a new organization on an empty database.

The command must create just enough to log in and nothing more, and must be
safe to re-run, so an interrupted first attempt can simply be repeated.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.modules.catalog.models import Product
from app.modules.catalog.models import ProductCategory
from app.modules.commercial.models import CommercialRole
from app.modules.commercial.service import DEFAULT_COMMERCIAL_ROLES
from app.modules.commissions.models import Rank, SplitPlan
from app.modules.contracts.models import Contract
from app.modules.customers.models import Customer
from app.modules.network.models import AgentProfile
from app.modules.rbac.models import SYSTEM_ROLES, Role, RolePermission, UserRole
from app.modules.users.models import User
from app.seed import bootstrap
from app.seed.ranks import RANK_SEED


def _unique_name() -> str:
    return f"Azienda Test {uuid.uuid4().hex[:8]}"


async def _count(db, model, **filters) -> int:
    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    return (await db.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_a_fresh_company_gets_exactly_what_it_needs_to_log_in(db):
    name = _unique_name()
    result = await bootstrap.bootstrap_organization(
        db,
        organization_name=name,
        legal_name=f"{name} S.r.l.",
        admin_email="Titolare@Azienda.IT",
        admin_password=None,
    )
    org_id = result.organization_id

    assert result.organization_created is True
    assert result.admin_created is True
    assert await _count(db, Role, organization_id=org_id) == len(SYSTEM_ROLES)
    assert await _count(db, Rank, organization_id=org_id) == len(RANK_SEED)
    # Starter roles and categories, but no Split Plan: shares are a business
    # decision, not a software default.
    assert await _count(db, CommercialRole, organization_id=org_id) == len(DEFAULT_COMMERCIAL_ROLES)
    assert await _count(db, CommercialRole, organization_id=org_id, is_default=True) == 1
    assert await _count(db, ProductCategory, organization_id=org_id) == 2
    assert await _count(db, SplitPlan, organization_id=org_id) == 0

    # Every system role must carry permissions; an admin without any could
    # log in but do nothing.
    role_ids = [r for (r,) in (await db.execute(select(Role.id).where(Role.organization_id == org_id))).all()]
    granted = (await db.execute(
        select(func.count()).select_from(RolePermission).where(RolePermission.role_id.in_(role_ids))
    )).scalar_one()
    assert granted > 0

    admin = (await db.execute(
        select(User).where(User.organization_id == org_id)
    )).scalars().one()
    assert admin.email == "titolare@azienda.it", "l'email va normalizzata, si fa login con quella"
    assert admin.status == "ACTIVE"
    assert admin.email_verified_at is not None, "l'SMTP al bootstrap di solito non esiste ancora"
    # Consents are given by the person at first login, not by the command.
    assert admin.privacy_accepted_at is None
    assert admin.fiscal_code is None

    admin_roles = (await db.execute(
        select(Role.code).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == admin.id)
    )).scalars().all()
    assert list(admin_roles) == ["SUPER_ADMIN"]


@pytest.mark.asyncio
async def test_nothing_of_the_demo_comes_along(db):
    """Demo seed data (fake promoters and customers) is never included."""
    name = _unique_name()
    result = await bootstrap.bootstrap_organization(
        db, organization_name=name, legal_name=name, admin_email="a@b.it", admin_password="password123"
    )
    org_id = result.organization_id

    assert await _count(db, AgentProfile, organization_id=org_id) == 0
    assert await _count(db, Customer, organization_id=org_id) == 0
    assert await _count(db, Product, organization_id=org_id) == 0
    assert await _count(db, Contract, organization_id=org_id) == 0
    assert await _count(db, User, organization_id=org_id) == 1


@pytest.mark.asyncio
async def test_running_it_twice_changes_nothing(db):
    name = _unique_name()
    first = await bootstrap.bootstrap_organization(
        db, organization_name=name, legal_name=name, admin_email="a@b.it", admin_password="password123"
    )
    second = await bootstrap.bootstrap_organization(
        db, organization_name=name, legal_name=name, admin_email="a@b.it", admin_password="password123"
    )

    assert second.organization_id == first.organization_id
    assert second.organization_created is False
    assert second.admin_created is False
    assert second.ranks_created == 0
    assert second.commercial_roles_created == 0
    assert second.categories_created == 0

    org_id = first.organization_id
    assert await _count(db, Role, organization_id=org_id) == len(SYSTEM_ROLES)
    assert await _count(db, Rank, organization_id=org_id) == len(RANK_SEED)
    assert await _count(db, CommercialRole, organization_id=org_id) == len(DEFAULT_COMMERCIAL_ROLES)
    assert await _count(db, User, organization_id=org_id) == 1


@pytest.mark.asyncio
async def test_an_existing_admin_password_is_never_silently_overwritten(db):
    """Re-running bootstrap never changes an existing admin's password."""
    name = _unique_name()
    await bootstrap.bootstrap_organization(
        db, organization_name=name, legal_name=name, admin_email="a@b.it", admin_password="password123"
    )
    admin = (await db.execute(select(User).where(User.email == "a@b.it"))).scalars().one()
    original_hash = admin.password_hash

    await bootstrap.bootstrap_organization(
        db, organization_name=name, legal_name=name, admin_email="a@b.it", admin_password="unaltrapassword"
    )
    await db.refresh(admin)
    assert admin.password_hash == original_hash


@pytest.mark.asyncio
async def test_two_companies_on_the_same_database_do_not_share_roles_or_ranks(db):
    """Each organization on a shared database gets its own roles and ranks."""
    first = await bootstrap.bootstrap_organization(
        db, organization_name=_unique_name(), legal_name="A", admin_email="a1@b.it", admin_password="password123"
    )
    second = await bootstrap.bootstrap_organization(
        db, organization_name=_unique_name(), legal_name="B", admin_email="b1@b.it", admin_password="password123"
    )

    assert first.organization_id != second.organization_id
    for org_id in (first.organization_id, second.organization_id):
        assert await _count(db, Role, organization_id=org_id) == len(SYSTEM_ROLES)
        assert await _count(db, Rank, organization_id=org_id) == len(RANK_SEED)


def test_the_generated_password_is_long_enough_to_be_worth_generating():
    password = bootstrap.generate_password()
    assert len(password) >= 16
    assert password != bootstrap.generate_password()
