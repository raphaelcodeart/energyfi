"""Fake demo data: one organization with RBAC, a 20-agent, 6-level network in
two parallel branches (to show branch isolation), products, customers,
contracts in every status, and the commissions their activations generate."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.foundation.db import AsyncSessionLocal
from app.foundation.security import hash_password
from app.modules.catalog.models import Product, ProductVersion
from app.modules.commissions.models import Rank
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from app.modules.contracts import service as contract_service
from app.modules.customers.models import Address, Customer, CustomerProfile, SupplyPoint
from app.modules.network import service as network_service
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
from app.modules.referral.models import PromoterCode
from app.modules.users.models import User
from app.seed.ranks import RANK_SEED, RULE_VERSION

FIXED_NOW = datetime(2026, 7, 25, tzinfo=UTC)

#: Demo margins; in real use administration sets one per product version.
DEMO_MARGIN_CENTS = {"LUCE-STD": 15000, "LUCE-PLUS": 20000, "GAS-STD": 15000, "GAS-PLUS": 20000}


async def run() -> None:
    async with AsyncSessionLocal() as db:
        org = Organization(name="SOSNET Demo", legal_name="SOSNET S.r.l. (demo)", status="ACTIVE")
        db.add(org)
        await db.flush()
        org_id = org.id

        # permissions is a global catalog that may already hold some codes;
        # reuse them to avoid a UniqueViolation.
        existing_permissions = (
            await db.execute(select(Permission).where(Permission.code.in_(PERMISSIONS)))
        ).scalars().all()
        permissions_by_code: dict[str, Permission] = {p.code: p for p in existing_permissions}
        for code in PERMISSIONS:
            if code not in permissions_by_code:
                perm = Permission(code=code, description="")
                db.add(perm)
                permissions_by_code[code] = perm
        await db.flush()

        roles_by_code: dict[str, Role] = {}
        for code in SYSTEM_ROLES:
            role = Role(organization_id=org_id, code=code, name=code.replace("_", " ").title())
            db.add(role)
            roles_by_code[code] = role
        await db.flush()

        for role_code, granted_codes in DEFAULT_ROLE_PERMISSIONS.items():
            role = roles_by_code[role_code]
            for perm_code in granted_codes:
                db.add(RolePermission(role_id=role.id, permission_id=permissions_by_code[perm_code].id))
        await db.flush()

        ranks_by_code: dict[str, Rank] = {}
        for r in RANK_SEED:
            rank = Rank(
                organization_id=org_id,
                code=r["code"],
                name=r["name"],
                level=r["level"],
                personal_token_cents=r["personal_token_cents"],
                personal_volume_threshold_cents=r["personal_volume_threshold_cents"],
                group_volume_threshold_cents=r["group_volume_threshold_cents"],
                valid_from=FIXED_NOW,
                rule_version=RULE_VERSION,
            )
            db.add(rank)
            ranks_by_code[r["code"]] = rank
        await db.flush()

        # Same starting commercial roles and categories as a real bootstrap.
        from app.seed.bootstrap import _ensure_commercial_setup

        await _ensure_commercial_setup(db, org_id=org_id)
        await db.commit()

        def make_user(email: str, password: str, role_codes: list[str]) -> User:
            # Demo accounts start verified and complete so they skip the
            # email-verification and profile-completion gates.
            user = User(
                organization_id=org_id,
                email=email,
                password_hash=hash_password(password),
                status="ACTIVE",
                email_verified_at=FIXED_NOW,
                privacy_accepted_at=FIXED_NOW,
                fiscal_code="RSSMRA80A01H501U",
                residence_street="Via Roma 1",
                residence_city="Roma",
                residence_province="RM",
                residence_postal_code="00100",
                residence_country="IT",
            )
            db.add(user)
            return user

        super_admin = make_user("superadmin@sosnet.demo", "DemoPass123!", ["SUPER_ADMIN"])
        admin = make_user("admin@sosnet.demo", "DemoPass123!", ["ADMIN"])
        back_office = make_user("backoffice@sosnet.demo", "DemoPass123!", ["BACK_OFFICE_OPERATOR"])
        accounting = make_user("accounting@sosnet.demo", "DemoPass123!", ["ACCOUNTING_OPERATOR"])
        sales_manager = make_user("salesmanager@sosnet.demo", "DemoPass123!", ["SALES_MANAGER"])
        await db.flush()

        for user, role_code in [
            (super_admin, "SUPER_ADMIN"),
            (admin, "ADMIN"),
            (back_office, "BACK_OFFICE_OPERATOR"),
            (accounting, "ACCOUNTING_OPERATOR"),
            (sales_manager, "SALES_MANAGER"),
        ]:
            db.add(UserRole(user_id=user.id, organization_id=org_id, role_id=roles_by_code[role_code].id))
        await db.commit()

        # --- Commercial network: two parallel top-level branches, 6 levels deep ---
        promoter_names = [
            "Anna Bianchi", "Luca Ferrari", "Giulia Romano", "Marco Colombo", "Sara Ricci",
            "Davide Marino", "Elena Greco", "Paolo Bruno", "Chiara Gallo", "Fabio Conti",
            "Valentina Rossi", "Matteo De Luca", "Francesca Costa", "Simone Giordano",
            "Martina Mancini", "Riccardo Rizzo", "Federica Lombardi", "Andrea Moretti",
            "Silvia Barbieri", "Nicola Fontana",
        ]
        name_iter = iter(promoter_names)

        async def new_agent(
            rank_code: str, parent_id: uuid.UUID | None, promoter_code: str, login_email: str | None = None
        ) -> uuid.UUID:
            display_name = next(name_iter)
            first_name, _, last_name = display_name.partition(" ")
            promoter_user_id = None
            if login_email is not None:
                promoter_user = make_user(login_email, "DemoPass123!", ["PROMOTER"])
                await db.flush()
                db.add(
                    UserRole(
                        user_id=promoter_user.id, organization_id=org_id, role_id=roles_by_code["PROMOTER"].id
                    )
                )
                await db.flush()
                promoter_user_id = promoter_user.id

            agent = await network_service.create_agent(
                db,
                organization_id=org_id,
                first_name=first_name,
                last_name=last_name,
                promoter_code=promoter_code,
                parent_agent_id=parent_id,
                joined_at=FIXED_NOW - timedelta(days=180),
                actor_user_id=admin.id,
                current_rank_id=ranks_by_code[rank_code].id,
                user_id=promoter_user_id,
            )
            code_row = PromoterCode(
                organization_id=org_id,
                agent_id=agent.id,
                code=promoter_code,
                personal_link=f"https://sosnet.demo/r/{promoter_code}",
                status="ACTIVE",
                valid_from=FIXED_NOW - timedelta(days=180),
            )
            db.add(code_row)
            await db.commit()
            return agent.id

        # Branch A (depth 0..5). a0 can log in to show the promoter dashboard:
        # its own branch and commissions only, never Branch B.
        a0 = await new_agent("SM5", None, "SM5-ROSSI", login_email="promoter@sosnet.demo")
        a1 = await new_agent("SL4", a0, "SL4-A01")
        a2 = await new_agent("SL2", a1, "SL2-A02")
        a3 = await new_agent("SP3", a2, "SP3-A03")
        a4 = await new_agent("SP2", a3, "SP2-A04")
        a5_producer = await new_agent("SP1", a4, "SP1-A05")  # depth 5
        # Sub-branches off a1 and a2.
        a6 = await new_agent("SL1", a1, "SL1-A06")
        await new_agent("SP1", a6, "SP1-A07")
        a8 = await new_agent("SP2", a2, "SP2-A08")
        a9 = await new_agent("SP1", a8, "SP1-A09")

        # Branch B: separate root, unrelated to Branch A.
        b0 = await new_agent("SM3", None, "SM3-CONTI")
        b1 = await new_agent("SL3", b0, "SL3-B01")
        b2 = await new_agent("SP3", b1, "SP3-B02")
        b3_producer = await new_agent("SP1", b2, "SP1-B03")
        b4 = await new_agent("SL1", b1, "SL1-B04")
        b5 = await new_agent("SP2", b4, "SP2-B05")
        await new_agent("SP1", b5, "SP1-B06")
        b7 = await new_agent("SL2", b0, "SL2-B07")
        b8 = await new_agent("SP1", b7, "SP1-B08")
        b9 = await new_agent("SP1", b7, "SP1-B09")

        # --- Catalog: electricity and gas, each in two formulas ---
        luce_std_product = Product(organization_id=org_id, code="LUCE-STD", energy_type="ELECTRICITY", customer_type="PRIVATE")
        luce_plus_product = Product(organization_id=org_id, code="LUCE-PLUS", energy_type="ELECTRICITY", customer_type="PRIVATE")
        gas_std_product = Product(organization_id=org_id, code="GAS-STD", energy_type="GAS", customer_type="PRIVATE")
        gas_plus_product = Product(organization_id=org_id, code="GAS-PLUS", energy_type="GAS", customer_type="PRIVATE")
        from app.modules.catalog.models import ProductCategory

        energia = (
            await db.execute(select(ProductCategory).where(ProductCategory.organization_id == org_id, ProductCategory.code == "ENERGIA"))
        ).scalar_one()
        for product in (luce_std_product, luce_plus_product, gas_std_product, gas_plus_product):
            product.commercial_category_id = energia.id
        db.add_all([luce_std_product, luce_plus_product, gas_std_product, gas_plus_product])
        await db.flush()

        luce_std_version = ProductVersion(
            product_id=luce_std_product.id, version_label="1.0", name="Luce Standard",
            base_price_cents=1800, recurring_fee_cents=300,
            margin_type="FIXED", margin_amount_cents=DEMO_MARGIN_CENTS["LUCE-STD"], valid_from=FIXED_NOW,
        )
        luce_circ_version = ProductVersion(
            product_id=luce_plus_product.id, version_label="1.0", name="Luce Energia Plus",
            base_price_cents=2200, recurring_fee_cents=400,
            margin_type="FIXED", margin_amount_cents=DEMO_MARGIN_CENTS["LUCE-PLUS"], valid_from=FIXED_NOW,
        )
        gas_std_version = ProductVersion(
            product_id=gas_std_product.id, version_label="1.0", name="Gas Standard",
            base_price_cents=2000, recurring_fee_cents=300,
            margin_type="FIXED", margin_amount_cents=DEMO_MARGIN_CENTS["GAS-STD"], valid_from=FIXED_NOW,
        )
        gas_circ_version = ProductVersion(
            product_id=gas_plus_product.id, version_label="1.0", name="Gas Energia Plus",
            base_price_cents=2400, recurring_fee_cents=400,
            margin_type="FIXED", margin_amount_cents=DEMO_MARGIN_CENTS["GAS-PLUS"], valid_from=FIXED_NOW,
        )
        db.add_all([luce_std_version, luce_circ_version, gas_std_version, gas_circ_version])
        await db.commit()

        # Example Split Plan for a Networker selling energy: 50% to the seller,
        # 20/15/10% to the three upline levels, the rest to the company.
        # Demo values, not a recommended configuration.
        from app.modules.commercial.models import CommercialRole
        from app.modules.commissions.services import plans as plans_service

        networker = (
            await db.execute(select(CommercialRole).where(CommercialRole.organization_id == org_id, CommercialRole.code == "NETWORKER"))
        ).scalar_one()
        demo_plan = await plans_service.create_plan(
            db, organization_id=org_id, actor_user_id=admin.id,
            values={"name": "Energia - Networker (demo)", "category_id": energia.id, "seller_role_id": networker.id,
                    "valid_from": FIXED_NOW - timedelta(days=365), "fallback_strategy": "COMPANY",
                    "distribution_mode": "FULL", "accrual_trigger": "PER_INSTALMENT"},
            rules=[
                {"beneficiary_type": "SELLER", "calculation_type": "PERCENTAGE", "percentage": 50},
                {"beneficiary_type": "UPLINE_LEVEL", "network_level": 1, "calculation_type": "PERCENTAGE", "percentage": 20},
                {"beneficiary_type": "UPLINE_LEVEL", "network_level": 2, "calculation_type": "PERCENTAGE", "percentage": 15},
                {"beneficiary_type": "UPLINE_LEVEL", "network_level": 3, "calculation_type": "PERCENTAGE", "percentage": 10},
                {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"},
            ],
        )
        await plans_service.activate(db, organization_id=org_id, plan_id=demo_plan.id, actor_user_id=admin.id)

        # --- Customers, supply points, contracts ---
        async def new_customer(
            kind: str, first: str, last: str, email: str, login_email: str | None = None
        ) -> uuid.UUID:
            customer_user_id = None
            if login_email is not None:
                customer_user = make_user(login_email, "DemoPass123!", ["CUSTOMER"])
                await db.flush()
                db.add(
                    UserRole(
                        user_id=customer_user.id, organization_id=org_id, role_id=roles_by_code["CUSTOMER"].id
                    )
                )
                await db.flush()
                customer_user_id = customer_user.id

            customer = Customer(organization_id=org_id, kind=kind, email=email, user_id=customer_user_id)
            db.add(customer)
            await db.flush()
            db.add(CustomerProfile(customer_id=customer.id, first_name=first, last_name=last))
            await db.commit()
            return customer.id

        # cust1 can log in to show the customer dashboard (own contracts only).
        cust1 = await new_customer(
            "PRIVATE", "Roberto", "Villa", "roberto.villa@example.demo",
            login_email="customer@sosnet.demo",
        )
        cust2 = await new_customer("SOLE_PROPRIETOR", "Laura", "Ferri", "laura.ferri@example.demo")
        cust3 = await new_customer("COMPANY", "Officine", "Bianchi Srl", "info@officinebianchi.demo")

        async def new_supply_point(customer_id: uuid.UUID, energy_type: str) -> uuid.UUID:
            address = Address(
                organization_id=org_id, customer_id=customer_id, kind="SUPPLY",
                street="Via Roma 1", city="Milano", province="MI", postal_code="20100",
            )
            db.add(address)
            await db.flush()
            sp = SupplyPoint(
                organization_id=org_id, customer_id=customer_id, energy_type=energy_type,
                pod_code="IT001E00000001" if energy_type == "ELECTRICITY" else None,
                pdr_code="00000000000001" if energy_type == "GAS" else None,
                supply_address_id=address.id,
            )
            db.add(sp)
            await db.commit()
            return sp.id

        sp1 = await new_supply_point(cust1, "ELECTRICITY")
        sp2 = await new_supply_point(cust2, "GAS")
        sp3 = await new_supply_point(cust3, "ELECTRICITY")

        async def create_and_advance(
            customer_id: uuid.UUID, supply_point_id: uuid.UUID, product_version_id: uuid.UUID,
            producer_agent_id: uuid.UUID, target_status: str,
        ):
            contract = await contract_service.create_contract(
                db, organization_id=org_id, customer_id=customer_id, supply_point_id=supply_point_id,
                product_version_id=product_version_id, producer_agent_id=producer_agent_id,
                actor_user_id=back_office.id, correlation_id=str(uuid.uuid4()),
            )
            # Walk the happy path up to target_status; DRAFT means no transition.
            if target_status == "DRAFT":
                return contract

            full_path = [
                "SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING",
                "PAID", "ACTIVATION_PENDING", "ACTIVE",
            ]
            if target_status == "REJECTED":
                full_path = ["SUBMITTED", "REJECTED"]
            elif target_status == "CANCELLED":
                full_path = full_path + ["CANCELLED"]

            for step in full_path:
                # APPROVED and PAID advance automatically (AUTO_CASCADE_AFTER),
                # so skip states already reached.
                already_there = (
                    contract.status in full_path and full_path.index(step) <= full_path.index(contract.status)
                )
                if already_there:
                    if step == target_status:
                        break
                    continue
                contract = await contract_service.transition_contract(
                    db, organization_id=org_id, contract=contract, to_status=step,
                    actor_user_id=admin.id, reason="demo data", notes=None, correlation_id=str(uuid.uuid4()),
                )
                if step == target_status:
                    break
            return contract

        await create_and_advance(cust1, sp1, luce_std_version.id, a5_producer, "ACTIVE")
        await create_and_advance(cust2, sp2, gas_std_version.id, b3_producer, "ACTIVE")
        await create_and_advance(cust3, sp3, luce_circ_version.id, a9, "DRAFT")
        await create_and_advance(cust1, sp1, gas_std_version.id, b8, "REJECTED")
        await create_and_advance(cust2, sp2, luce_std_version.id, b9, "CANCELLED")

        processed = await process_pending_outbox_events(db)
        print(f"Seed complete. Processed {processed} outbox event(s) -> commissions generated.")
        print(f"Organization ID: {org_id}")
        print("Demo logins (password: DemoPass123!):")
        print("  superadmin@sosnet.demo (SUPER_ADMIN)")
        print("  admin@sosnet.demo (ADMIN)")
        print("  backoffice@sosnet.demo (BACK_OFFICE_OPERATOR)")
        print("  accounting@sosnet.demo (ACCOUNTING_OPERATOR)")
        print("  salesmanager@sosnet.demo (SALES_MANAGER)")
        print("  promoter@sosnet.demo (PROMOTER, agent SM5-ROSSI, branch A root)")
        print("  customer@sosnet.demo (CUSTOMER, linked to Roberto Villa)")
