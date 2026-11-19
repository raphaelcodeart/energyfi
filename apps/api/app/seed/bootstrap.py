"""Bootstrap a new company on an empty database.

Unlike `python -m app.seed` (fake demo data, never for real customers), this
creates only what the application needs to start:

  - the global `permissions` catalog, shared by all organizations;
  - the `Organization`, its system roles and their permissions;
  - the starting commercial roles and categories (structure only; Split
    Plans are configured by administration);
  - the legacy `ranks` ladder, kept for compatibility and unused by the
    commission engine;
  - a single SUPER_ADMIN user, from which everything else is done in the UI.

Idempotent: re-running with the same organization name only adds what is
missing, so a partially failed server rebuild can be retried safely.

Usage:

    docker compose -f docker-compose.dev.yml exec api \\
      python -m app.seed.bootstrap \\
        --organization-name "Nome Azienda" \\
        --legal-name "Nome Azienda S.r.l." \\
        --admin-email "titolare@azienda.it"

Without `--admin-password`, a password is generated and printed once; it
cannot be recovered later, only reset. See docs/server-migration-guide.md §12.
"""

import argparse
import asyncio
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.foundation.db import AsyncSessionLocal
from app.foundation.security import hash_password
from app.modules.commissions.models import Rank
from app.modules.organizations.models import Organization
from app.modules.rbac.models import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSIONS,
    SYSTEM_ROLES,
    Permission,
    Role,
    RolePermission,
    UserRole,
)
from app.modules.users.models import User
from app.seed.ranks import RANK_SEED, RULE_VERSION

BOOTSTRAP_ROLE = "SUPER_ADMIN"


def generate_password() -> str:
    """URL-safe and well above the schema minimum, since it is copied and
    pasted rather than memorized."""
    return secrets.token_urlsafe(12)


async def _ensure_permissions(db) -> dict[str, Permission]:
    """`permissions` is a global catalog that may already contain codes, so
    only missing ones are inserted to avoid a UniqueViolation."""
    existing = (await db.execute(select(Permission).where(Permission.code.in_(PERMISSIONS)))).scalars().all()
    by_code = {p.code: p for p in existing}
    for code in PERMISSIONS:
        if code not in by_code:
            perm = Permission(code=code, description="")
            db.add(perm)
            by_code[code] = perm
    await db.flush()
    return by_code


async def _ensure_roles(db, *, org_id: uuid.UUID, permissions_by_code: dict[str, Permission]) -> dict[str, Role]:
    existing = (await db.execute(select(Role).where(Role.organization_id == org_id))).scalars().all()
    by_code = {r.code: r for r in existing}
    for code in SYSTEM_ROLES:
        if code not in by_code:
            role = Role(organization_id=org_id, code=code, name=code.replace("_", " ").title())
            db.add(role)
            by_code[code] = role
    await db.flush()

    granted = {
        (rp.role_id, rp.permission_id)
        for rp in (
            await db.execute(
                select(RolePermission).where(RolePermission.role_id.in_([r.id for r in by_code.values()]))
            )
        ).scalars().all()
    }
    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = by_code[role_code]
        for permission_code in permission_codes:
            permission = permissions_by_code[permission_code]
            if (role.id, permission.id) not in granted:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    await db.flush()
    return by_code


async def _ensure_ranks(db, *, org_id: uuid.UUID, now: datetime) -> int:
    existing_codes = {
        code
        for (code,) in (await db.execute(select(Rank.code).where(Rank.organization_id == org_id))).all()
    }
    created = 0
    for r in RANK_SEED:
        if r["code"] in existing_codes:
            continue
        db.add(
            Rank(
                organization_id=org_id,
                code=r["code"],
                name=r["name"],
                level=r["level"],
                personal_token_cents=r["personal_token_cents"],
                personal_volume_threshold_cents=r["personal_volume_threshold_cents"],
                group_volume_threshold_cents=r["group_volume_threshold_cents"],
                valid_from=now,
                rule_version=RULE_VERSION,
            )
        )
        created += 1

    await db.flush()
    return created


#: Starting commercial categories. Energy requires a supply point (POD/PDR).
DEFAULT_PRODUCT_CATEGORIES = [
    {"code": "ENERGIA", "name": "Energia", "requires_supply_point": True},
    {"code": "TLC", "name": "Telecomunicazioni", "requires_supply_point": False},
]


async def _ensure_commercial_setup(db, *, org_id: uuid.UUID) -> tuple[int, int]:
    """Idempotently create starting commercial roles and categories. No
    Split Plan: payout shares are an administrative decision."""
    from app.modules.catalog.models import ProductCategory
    from app.modules.commercial import service as commercial_service

    before = len(await commercial_service.list_roles(db, organization_id=org_id))
    roles = await commercial_service.ensure_default_roles(db, organization_id=org_id)
    existing = {
        c for (c,) in (await db.execute(select(ProductCategory.code).where(ProductCategory.organization_id == org_id))).all()
    }
    categories = 0
    for spec in DEFAULT_PRODUCT_CATEGORIES:
        if spec["code"] not in existing:
            db.add(ProductCategory(organization_id=org_id, **spec))
            categories += 1
    await db.flush()
    return len(roles) - before, categories


@dataclass
class BootstrapResult:
    organization_id: uuid.UUID
    organization_created: bool
    roles: int
    #: Ranks inserted by this run (0 on re-runs).
    ranks_created: int
    commercial_roles_created: int
    categories_created: int
    admin_created: bool
    #: Set only when this run created the admin with a generated password;
    #: printed once and never stored.
    generated_password: str | None


async def _ensure_promoters_are_customers(db, *, org_id: uuid.UUID) -> int:
    """Every active promoter with a login is also a customer, so both areas
    are open to them (network/service.py::ensure_customer_side)."""
    from app.modules.network import service as network_service
    from app.modules.network.models import AgentProfile

    agents = (await db.execute(select(AgentProfile).where(
        AgentProfile.organization_id == org_id, AgentProfile.user_id.is_not(None), AgentProfile.status == "ACTIVE",
    ))).scalars().all()
    added = 0
    for agent in agents:
        if await network_service.ensure_customer_side(db, organization_id=org_id, agent=agent):
            added += 1
    return added


async def bootstrap_organization(
    db,
    *,
    organization_name: str,
    legal_name: str,
    admin_email: str,
    admin_password: str | None,
    now: datetime | None = None,
) -> BootstrapResult:
    """Do the bootstrap on a caller-provided session, so tests can use their
    own database."""
    admin_email = admin_email.strip().lower()
    now = now or datetime.now(UTC)
    generated_password = None

    org = (
        await db.execute(select(Organization).where(Organization.name == organization_name))
    ).scalars().first()
    org_created = org is None
    if org is None:
        org = Organization(name=organization_name, legal_name=legal_name, status="ACTIVE")
        db.add(org)
        await db.flush()
    org_id = org.id

    permissions_by_code = await _ensure_permissions(db)
    roles_by_code = await _ensure_roles(db, org_id=org_id, permissions_by_code=permissions_by_code)
    ranks_created = await _ensure_ranks(db, org_id=org_id, now=now)
    commercial_roles_created, categories_created = await _ensure_commercial_setup(db, org_id=org_id)
    await _ensure_promoters_are_customers(db, org_id=org_id)

    user = (
        await db.execute(select(User).where(User.organization_id == org_id, User.email == admin_email))
    ).scalars().first()
    user_created = user is None
    if user is None:
        if admin_password is None:
            admin_password = generated_password = generate_password()
        user = User(
            organization_id=org_id,
            email=admin_email,
            password_hash=hash_password(admin_password),
            status="ACTIVE",
            # Pre-verified: running a command on the server is stronger proof
            # than a clicked link, and SMTP is usually not configured yet.
            email_verified_at=now,
            # Privacy consent and personal details stay NULL on purpose: the
            # real person provides them on first login.
        )
        db.add(user)
        await db.flush()
        db.add(UserRole(user_id=user.id, organization_id=org_id, role_id=roles_by_code[BOOTSTRAP_ROLE].id))

    await db.commit()
    return BootstrapResult(
        organization_id=org_id,
        organization_created=org_created,
        roles=len(roles_by_code),
        ranks_created=ranks_created,
        commercial_roles_created=commercial_roles_created,
        categories_created=categories_created,
        admin_created=user_created,
        generated_password=generated_password,
    )


async def run(
    *,
    organization_name: str,
    legal_name: str,
    admin_email: str,
    admin_password: str | None,
) -> int:
    async with AsyncSessionLocal() as db:
        result = await bootstrap_organization(
            db,
            organization_name=organization_name,
            legal_name=legal_name,
            admin_email=admin_email,
            admin_password=admin_password,
        )

    print()
    print("=" * 72)
    print("  Bootstrap completato")
    print("=" * 72)
    print(f"  Organizzazione    {organization_name}  ({'creata' if result.organization_created else 'già esistente'})")
    print(f"  Organization ID   {result.organization_id}")
    print(f"  Ruoli             {result.roles} ruoli di sistema, permessi allineati")
    print(f"  Ranks             {result.ranks_created} creati ({len(RANK_SEED)} attesi in totale)")
    print(f"  Ruoli commerciali {result.commercial_roles_created} creati (Networker, Agente, Direttore, ...)")
    print(f"  Categorie         {result.categories_created} create (Energia, Telecomunicazioni)")
    print(f"  Amministratore    {admin_email.strip().lower()}  "
          f"({'creato' if result.admin_created else 'già esistente, invariato'})")
    if result.generated_password is not None:
        print()
        print(f"  PASSWORD (mostrata una sola volta):  {result.generated_password}")
        print("  Salvala ora. Non è recuperabile: si può solo rifare un reset.")
    elif result.admin_created:
        print("  Password: quella che hai passato con --admin-password.")
    print()
    print("  Prossimi passi (docs/server-migration-guide.md §12):")
    print("   1. Accedi come amministratore e completa il tuo profilo quando te lo chiede.")
    print("   2. Impostazioni organizzazione: SMTP, Stripe, IBAN aziendale.")
    print("   3. Crea i prodotti reali con il loro margine, poi gli Split Plan, poi i primi collaboratori.")
    print("=" * 72)
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.seed.bootstrap",
        description="Crea una nuova organizzazione con il minimo indispensabile per partire.",
    )
    parser.add_argument("--organization-name", required=True, help='Nome visibile, es. "Nome Azienda"')
    parser.add_argument("--legal-name", required=True, help='Ragione sociale, es. "Nome Azienda S.r.l."')
    parser.add_argument("--admin-email", required=True, help="Email del primo SUPER_ADMIN")
    parser.add_argument(
        "--admin-password",
        default=None,
        help="Se omessa ne viene generata una e stampata una sola volta (consigliato)",
    )
    args = parser.parse_args(argv)

    if args.admin_password is not None and len(args.admin_password) < 8:
        parser.error("la password deve essere di almeno 8 caratteri (stesso minimo dell'app)")

    return asyncio.run(
        run(
            organization_name=args.organization_name,
            legal_name=args.legal_name,
            admin_email=args.admin_email,
            admin_password=args.admin_password,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
