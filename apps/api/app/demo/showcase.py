"""Showcase data for exploring SOSNET end to end.

Populates an existing organization with a realistic, clearly fictitious
setup: a sponsorship network covering every commercial role, Energy and
Telco products with margins, active Split Plans (one versioned, one draft),
customers, contracts spread over the last three months, commissions in every
lifecycle state, a reversal and a few leads. Demo logins use @sosnet.demo.

It also resets the password of the organization's super admin, whose email
is passed on the command line. Every generated password is printed once.

Usage (inside the api container):
    python -m app.demo.showcase --organization-name SOSNET --superadmin-email admin@mamify.ai
"""

import argparse
import asyncio
import secrets
import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.foundation.config import get_settings
from app.foundation.db import AsyncSessionLocal, utcnow
from app.foundation.security import hash_password
from app.modules.catalog.models import Product, ProductCategory, ProductVersion
from app.modules.commercial import service as commercial_service
from app.modules.commercial.models import CommercialRole, Delegation
from app.modules.commissions.models import CommissionMovement, Rank
from app.modules.commissions.services import lifecycle
from app.modules.commissions.services import plans as plans_service
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract
from app.modules.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.modules.leads import service as leads_service
from app.modules.network import service as network_service
from app.modules.organizations.models import Organization
from app.modules.rbac import service as rbac_service
from app.modules.referral.models import CustomerAttribution, PromoterCode
from app.modules.users.models import User
from app.seed.bootstrap import bootstrap_organization

DEMO_DOMAIN = "sosnet.demo"
NOW = utcnow()
JOINED = NOW - timedelta(days=400)
PLANS_FROM = NOW - timedelta(days=420)


def _password() -> str:
    return secrets.token_urlsafe(9)


class Showcase:
    def __init__(self, db, org_id: uuid.UUID):
        self.db = db
        self.org_id = org_id
        self.roles: dict[str, CommercialRole] = {}
        self.categories: dict[str, ProductCategory] = {}
        self.ranks: dict[str, Rank] = {}
        self.agents: dict[str, object] = {}
        self.codes: dict[str, PromoterCode] = {}
        self.versions: dict[str, ProductVersion] = {}
        self.credentials: list[tuple[str, str, str]] = []
        self.actor_id: uuid.UUID | None = None

    # --- people -----------------------------------------------------------

    async def user(self, email: str, first: str, last: str, access_roles: list[str], label: str) -> User:
        password = _password()
        user = User(
            organization_id=self.org_id, email=email, password_hash=hash_password(password), status="ACTIVE",
            email_verified_at=NOW, privacy_accepted_at=NOW,
            fiscal_code="DMOUSR80A01H501X", residence_street="Via Demo 1", residence_city="Milano",
            residence_province="MI", residence_postal_code="20100", residence_country="IT",
        )
        self.db.add(user)
        await self.db.flush()
        for code in access_roles:
            await rbac_service.assign_role(self.db, user_id=user.id, organization_id=self.org_id, role_code=code)
        await self.db.commit()
        self.credentials.append((label, email, password))
        return user

    async def agent(self, key: str, first: str, last: str, role: str, parent: str | None, rank: str,
                    login_email: str | None = None):
        user_id = None
        if login_email:
            user = await self.user(login_email, first, last, ["PROMOTER"], f"Collaboratore – {self.roles[role].name}")
            user_id = user.id
        code = f"SOS-{first[:1]}{last}".upper().replace(" ", "").replace("'", "")[:20]
        agent = await network_service.create_agent(
            self.db, organization_id=self.org_id, first_name=first, last_name=last, promoter_code=code,
            parent_agent_id=self.agents[parent].id if parent else None, joined_at=JOINED,
            actor_user_id=self.actor_id, current_rank_id=self.ranks[rank].id if rank in self.ranks else None,
            user_id=user_id, commercial_role_id=self.roles[role].id,
        )
        promoter_code = PromoterCode(
            organization_id=self.org_id, agent_id=agent.id, code=code,
            personal_link=f"{get_settings().public_app_base_url}/r/{code}", status="ACTIVE", valid_from=JOINED,
        )
        self.db.add(promoter_code)
        await self.db.commit()
        self.agents[key] = agent
        self.codes[key] = promoter_code
        return agent

    async def customer(self, kind: str, name: tuple[str, str], email: str, referrer: str,
                       login_email: str | None = None, energy: str | None = None) -> tuple[Customer, SupplyPoint | None]:
        user_id = None
        if login_email:
            user = await self.user(login_email, name[0], name[1], ["CUSTOMER"], "Cliente")
            user_id = user.id
        customer = Customer(organization_id=self.org_id, kind=kind, email=email, user_id=user_id,
                            phone="+39 333 000 0000")
        self.db.add(customer)
        await self.db.flush()
        if kind == "COMPANY":
            self.db.add(Company(customer_id=customer.id, company_name=f"{name[0]} {name[1]}"))
            customer.vat_number = "IT01234567890"
        else:
            self.db.add(CustomerProfile(customer_id=customer.id, first_name=name[0], last_name=name[1]))
        self.db.add(CustomerAttribution(
            organization_id=self.org_id, customer_id=customer.id,
            promoter_code_id=self.codes[referrer].id, attributed_at=JOINED + timedelta(days=30),
        ))
        supply_point = None
        if energy:
            address = Address(organization_id=self.org_id, customer_id=customer.id, kind="SUPPLY",
                              street="Via Roma 10", city="Milano", province="MI", postal_code="20121")
            self.db.add(address)
            await self.db.flush()
            suffix = uuid.uuid4().hex[:8].upper()
            supply_point = SupplyPoint(
                organization_id=self.org_id, customer_id=customer.id, energy_type=energy,
                pod_code=f"IT001E{suffix}" if energy == "ELECTRICITY" else None,
                pdr_code=f"0000{suffix}" if energy == "GAS" else None,
                supply_address_id=address.id,
            )
            self.db.add(supply_point)
        await self.db.commit()
        return customer, supply_point

    # --- catalog and plans ------------------------------------------------------

    async def product(self, code: str, name: str, category: str, base_cents: int, margin: tuple,
                      energy: str | None = None, audience: str = "BOTH", vat: int = 22) -> None:
        product = Product(
            organization_id=self.org_id, code=code, product_type="ENERGY_CONTRACT" if energy else "SUBSCRIPTION",
            energy_type=energy, customer_type=audience, category="INTERNAL", status="ACTIVE",
            commercial_category_id=self.categories[category].id,
        )
        self.db.add(product)
        await self.db.flush()
        margin_type, value = margin
        version = ProductVersion(
            product_id=product.id, version_label="1.0", name=name, base_price_cents=base_cents,
            billing_period="MONTHLY", contract_duration_months=12, tax_configuration={"vat_percentage": vat},
            valid_from=PLANS_FROM, status="ACTIVE", margin_type=margin_type,
            margin_amount_cents=value if margin_type == "FIXED" else None,
            margin_percentage=value if margin_type == "PERCENTAGE" else None,
            description=f"{name} — offerta dimostrativa SOSNET.",
        )
        self.db.add(version)
        await self.db.commit()
        self.versions[code] = version

    async def plan(self, name: str, seller_role: str, rules: list[dict], *, category: str | None = None,
                   product: str | None = None, fallback: str = "COMPANY", valid_from: datetime = PLANS_FROM,
                   activate: bool = True):
        values = {
            "name": name, "seller_role_id": self.roles[seller_role].id, "valid_from": valid_from,
            "fallback_strategy": fallback, "distribution_mode": "FULL", "accrual_trigger": "PER_INSTALMENT",
            "category_id": self.categories[category].id if category else None,
            "product_id": self.versions[product].product_id if product else None,
        }
        plan = await plans_service.create_plan(
            self.db, organization_id=self.org_id, actor_user_id=self.actor_id, values=values, rules=rules,
        )
        if activate:
            plan = await plans_service.activate(
                self.db, organization_id=self.org_id, plan_id=plan.id, actor_user_id=self.actor_id,
            )
        return plan

    # --- sales ------------------------------------------------------------------

    async def sale(self, customer: Customer, supply_point, product: str, seller: str, days_ago: int,
                   target: str = "ACTIVE") -> Contract:
        contract = await contract_service.create_contract(
            self.db, organization_id=self.org_id, customer_id=customer.id,
            supply_point_id=supply_point.id if supply_point else None,
            product_version_id=self.versions[product].id, producer_agent_id=self.agents[seller].id,
            actor_user_id=self.actor_id, correlation_id=str(uuid.uuid4()), created_by_role="ADMIN",
        )
        contract.sold_at = NOW - timedelta(days=days_ago)
        await self.db.commit()
        path = {
            "DRAFT": [],
            "UNDER_REVIEW": ["SUBMITTED", "UNDER_REVIEW"],
            "REJECTED": ["SUBMITTED", "REJECTED"],
            "ACTIVE": ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "PAID"],
        }[target]
        for step in path:
            contract = await contract_service.transition_contract(
                self.db, organization_id=self.org_id, contract=contract, to_status=step,
                actor_user_id=self.actor_id, reason="Dati dimostrativi", notes=None,
                correlation_id=str(uuid.uuid4()),
            )
        if contract.activated_at is not None:
            contract.activated_at = contract.sold_at + timedelta(days=2)
            if contract.expires_at is not None:
                contract.expires_at = contract.activated_at + timedelta(days=365)
            await self.db.commit()
        return contract


# (name, description, levels reached, product codes)
DEMO_COMPANIES = [
    ("Energia Italiana S.p.A.", "Luce e gas per casa e imprese, su tutto il territorio.", 4,
     ["ENER-LUCE-STD", "ENER-GAS-STD", "ENER-BUSINESS"]),
    ("GreenPower Rinnovabili", "Energia da fonti 100% rinnovabili certificate.", 3, ["ENER-LUCE-GREEN"]),
    ("FibraNet Italia", "Connessioni in fibra ottica fino a 1 Giga.", 2, ["TLC-FIBRA-1000", "TLC-FIBRA-100"]),
    ("Mobile Plus", "Offerte mobili 5G per privati e aziende.", 2, ["TLC-MOBILE-5G"]),
]


async def seed_demo_companies(db, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID) -> int:
    """Create the demo companies and assign the demo products to them.
    Skips companies that already exist."""
    from app.modules.catalog import service as catalog_service
    from app.modules.catalog.models import Company

    created = 0
    for name, description, depth, codes in DEMO_COMPANIES:
        company = (await db.execute(select(Company).where(
            Company.organization_id == organization_id, Company.name == name))).scalars().first()
        if company is None:
            company = await catalog_service.save_company(
                db, organization_id=organization_id, actor_user_id=actor_user_id,
                values={"name": name, "description": description, "max_network_depth": depth, "is_active": True},
            )
            created += 1
        for product in (await db.execute(select(Product).where(
                Product.organization_id == organization_id, Product.code.in_(codes)))).scalars():
            product.company_id = company.id
        await db.commit()
    return created


async def run(organization_name: str, superadmin_email: str) -> int:
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.name == organization_name))).scalars().first()
        if org is None:
            print(f"Organizzazione «{organization_name}» non trovata.", file=sys.stderr)
            return 1
        admin = (
            await db.execute(select(User).where(User.organization_id == org.id, User.email == superadmin_email.lower()))
        ).scalars().first()
        if admin is None:
            print(f"Nessun account {superadmin_email} in «{organization_name}».", file=sys.stderr)
            return 1
        if (await db.execute(select(User.id).where(User.email == f"admin@{DEMO_DOMAIN}"))).first():
            print("I dati dimostrativi sono già presenti: niente da fare.", file=sys.stderr)
            return 1

        # Idempotent: permissions, access roles, commercial roles, categories, legacy levels.
        await bootstrap_organization(
            db, organization_name=organization_name, legal_name=org.legal_name or organization_name,
            admin_email=superadmin_email, admin_password=None,
        )

        s = Showcase(db, org.id)
        s.actor_id = admin.id
        superadmin_password = _password()
        admin.password_hash = hash_password(superadmin_password)
        admin.status = "ACTIVE"
        admin.failed_login_attempts = 0
        admin.locked_until = None
        await db.commit()
        s.credentials.append(("Super amministratore", admin.email, superadmin_password))

        s.roles = {r.code: r for r in await commercial_service.list_roles(db, organization_id=org.id)}
        s.categories = {c.code: c for c in (await db.execute(
            select(ProductCategory).where(ProductCategory.organization_id == org.id))).scalars()}
        s.ranks = {r.code: r for r in (await db.execute(select(Rank).where(Rank.organization_id == org.id))).scalars()}

        await s.user(f"admin@{DEMO_DOMAIN}", "Alessia", "Martini", ["ADMIN"], "Amministratore")
        await s.user(f"finanza@{DEMO_DOMAIN}", "Giorgio", "Pellegrini", ["FINANCE"], "Finanza (approva e paga)")

        # --- the network ------------------------------------------------------------
        await s.agent("marco", "Marco", "Bianchi", "NETWORKER", None, "SM3")
        await s.agent("sara", "Sara", "Conti", "NETWORKER", "marco", "SL2", login_email=f"promoter@{DEMO_DOMAIN}")
        await s.agent("paolo", "Paolo", "Greco", "NETWORKER", "marco", "SL1")
        await s.agent("luca", "Luca", "Ferri", "NETWORKER", "sara", "SP3")
        await s.agent("elisa", "Elisa", "Marini", "NETWORKER", "sara", "SP2")
        await s.agent("giulia", "Giulia", "Neri", "NETWORKER", "luca", "SP2")
        await s.agent("martina", "Martina", "Sala", "NETWORKER", "paolo", "SP1")
        await s.agent("andrea", "Andrea", "Riva", "NETWORKER", "giulia", "SP1")
        await s.agent("francesca", "Francesca", "Lodi", "PROMOTER", "luca", "SP1",
                      login_email=f"segnalatrice@{DEMO_DOMAIN}")
        await s.agent("chiara", "Chiara", "Moretti", "INFLUENCER", "marco", "SL3")
        await s.agent("davide", "Davide", "Costa", "DELEGATO_INFLUENCER", "chiara", "SP2")
        await s.agent("anna", "Anna", "Fontana", "DELEGATO_INFLUENCER", "chiara", "SP1")
        await s.agent("tommaso", "Tommaso", "Leone", "DELEGATO_INFLUENCER", "paolo", "SP1")
        await s.agent("roberto", "Roberto", "Galli", "DIRETTORE_COMMERCIALE", None, "SM1")
        await s.agent("simone", "Simone", "Russo", "AGENTE_PAP", "roberto", "SP3")
        await s.agent("elena", "Elena", "Villa", "AGENTE_PAP", "roberto", "SP2")
        await s.agent("fabio", "Fabio", "Caruso", "AGENTE_PAP", "roberto", "SP1")

        # Tommaso joined under Paolo but sells on behalf of Chiara: explicit delegation.
        await commercial_service.create_delegation(
            db, organization_id=org.id, influencer_agent_id=s.agents["chiara"].id,
            delegate_agent_id=s.agents["tommaso"].id, actor_user_id=admin.id,
            reason="Delegato in un altro ramo della rete",
        )
        delegation = (await db.execute(select(Delegation).where(
            Delegation.delegate_agent_id == s.agents["tommaso"].id))).scalars().first()
        delegation.valid_from = JOINED
        await db.commit()

        # --- products -------------------------------------------------------------
        await s.product("ENER-LUCE-STD", "Luce Casa Standard", "ENERGIA", 1800, ("FIXED", 15000), energy="ELECTRICITY", vat=10)
        await s.product("ENER-LUCE-GREEN", "Luce Green 100% rinnovabile", "ENERGIA", 2200, ("FIXED", 16000), energy="ELECTRICITY", vat=10)
        await s.product("ENER-GAS-STD", "Gas Casa Standard", "ENERGIA", 2000, ("FIXED", 12000), energy="GAS", vat=10)
        await s.product("ENER-BUSINESS", "Energia Business Pro", "ENERGIA", 6500, ("FIXED", 30000), energy="ELECTRICITY", audience="BUSINESS")
        await s.product("TLC-FIBRA-1000", "Fibra 1 Giga", "TLC", 2990, ("FIXED", 9000))
        await s.product("TLC-FIBRA-100", "Fibra 100 Mega", "TLC", 2290, ("FIXED", 6000))
        await s.product("TLC-MOBILE-5G", "Mobile 5G 150 GB", "TLC", 990, ("FIXED", 4000))

        await seed_demo_companies(db, organization_id=org.id, actor_user_id=admin.id)

        # --- split plans ------------------------------------------------------------
        pct = lambda who, value, **kw: {"beneficiary_type": who, "calculation_type": "PERCENTAGE", "percentage": value, **kw}  # noqa: E731
        rest = {"beneficiary_type": "COMPANY", "calculation_type": "REMAINDER"}
        await s.plan("Energia – Networker", "NETWORKER", category="ENERGIA", rules=[
            {"beneficiary_type": "PROMOTER", "calculation_type": "FIXED_AMOUNT", "amount_cents": 1500},
            pct("SELLER", 45), pct("UPLINE_LEVEL", 20, network_level=1), pct("UPLINE_LEVEL", 12, network_level=2),
            pct("UPLINE_LEVEL", 8, network_level=3), rest,
        ])
        await s.plan("TLC – Networker", "NETWORKER", category="TLC", rules=[
            {"beneficiary_type": "PROMOTER", "calculation_type": "FIXED_AMOUNT", "amount_cents": 1000},
            pct("SELLER", 45), pct("UPLINE_LEVEL", 20, network_level=1), pct("UPLINE_LEVEL", 10, network_level=2), rest,
        ])
        fibra_v1 = await s.plan("Fibra 1 Giga – Networker", "NETWORKER", product="TLC-FIBRA-1000", rules=[
            pct("SELLER", 40), pct("UPLINE_LEVEL", 20, network_level=1), pct("UPLINE_LEVEL", 15, network_level=2), rest,
        ])
        fibra_v2 = await plans_service.new_version(
            db, organization_id=org.id, plan_id=fibra_v1.id, actor_user_id=admin.id, valid_from=NOW - timedelta(days=30),
        )
        await plans_service.update_draft(
            db, organization_id=org.id, plan_id=fibra_v2.id, actor_user_id=admin.id,
            values={"notes": "Promozione autunno: più quota a chi vende."},
            rules=[pct("SELLER", 50), pct("UPLINE_LEVEL", 20, network_level=1), pct("UPLINE_LEVEL", 10, network_level=2), rest],
        )
        await plans_service.activate(db, organization_id=org.id, plan_id=fibra_v2.id, actor_user_id=admin.id)
        await s.plan("Energia – Porta a porta", "AGENTE_PAP", category="ENERGIA", rules=[
            pct("SELLER", 60), pct("ROLE_IN_UPLINE", 40, required_role_id=s.roles["DIRETTORE_COMMERCIALE"].id),
        ])
        await s.plan("TLC – Porta a porta", "AGENTE_PAP", category="TLC", rules=[
            pct("SELLER", 55), pct("ROLE_IN_UPLINE", 35, required_role_id=s.roles["DIRETTORE_COMMERCIALE"].id), rest,
        ])
        await s.plan("Energia – Direttore commerciale", "DIRETTORE_COMMERCIALE", category="ENERGIA", rules=[
            pct("SELLER", 70), rest,
        ])
        await s.plan("Energia – Delegati influencer", "DELEGATO_INFLUENCER", category="ENERGIA", rules=[
            pct("SELLER", 40), pct("INFLUENCER", 20), pct("UPLINE_LEVEL", 20, network_level=2, fallback_strategy="NEXT_AVAILABLE"), rest,
        ])
        await s.plan("TLC – Delegati influencer", "DELEGATO_INFLUENCER", category="TLC", rules=[
            pct("SELLER", 40), pct("INFLUENCER", 25), rest,
        ])
        await s.plan("Mobile 5G – Delegati (da completare)", "DELEGATO_INFLUENCER", product="TLC-MOBILE-5G",
                     activate=False, rules=[pct("SELLER", 50), pct("INFLUENCER", 30)])

        # --- customers and sales ---------------------------------------------------------
        customers = [
            ("PRIVATE", ("Roberto", "Villa"), "sara", "ELECTRICITY", f"cliente@{DEMO_DOMAIN}"),
            ("PRIVATE", ("Laura", "Ferrari"), "sara", "GAS", None),
            ("PRIVATE", ("Giovanni", "Esposito"), "luca", "ELECTRICITY", None),
            ("PRIVATE", ("Valentina", "Romano"), "giulia", None, None),
            ("PRIVATE", ("Matteo", "Colombo"), "andrea", "ELECTRICITY", None),
            ("SOLE_PROPRIETOR", ("Bar", "Centrale"), "elisa", "ELECTRICITY", None),
            ("PRIVATE", ("Federica", "Ricci"), "martina", None, None),
            ("COMPANY", ("Officine", "Lombarde Srl"), "simone", "ELECTRICITY", None),
            ("PRIVATE", ("Stefano", "Marino"), "elena", "GAS", None),
            ("PRIVATE", ("Chiara", "Gallo"), "fabio", None, None),
            ("PRIVATE", ("Alessio", "Barbieri"), "davide", "ELECTRICITY", None),
            ("PRIVATE", ("Silvia", "Testa"), "anna", None, None),
            ("PRIVATE", ("Riccardo", "Mancini"), "tommaso", "ELECTRICITY", None),
            ("PRIVATE", ("Giorgio", "Fabbri"), "francesca", "ELECTRICITY", None),
            ("COMPANY", ("Studio", "Rinaldi & Associati"), "roberto", "ELECTRICITY", None),
            ("PRIVATE", ("Elena", "Pagano"), "paolo", None, None),
        ]
        c = {}
        for kind, name, ref, energy, login in customers:
            key = name[0].lower()
            c[key] = await s.customer(kind, name, f"{name[0].lower()}.{name[1].split()[0].lower()}@example.demo",
                                      ref, login_email=login, energy=energy)

        sales = [
            ("roberto", "ENER-LUCE-STD", "sara", 85), ("roberto", "TLC-FIBRA-1000", "sara", 12),
            ("laura", "ENER-GAS-STD", "sara", 70), ("giovanni", "ENER-LUCE-GREEN", "luca", 64),
            ("valentina", "TLC-FIBRA-100", "giulia", 55), ("matteo", "ENER-LUCE-STD", "andrea", 47),
            ("bar", "ENER-LUCE-STD", "elisa", 40), ("federica", "TLC-MOBILE-5G", "martina", 33),
            ("officine", "ENER-BUSINESS", "simone", 78), ("stefano", "ENER-GAS-STD", "elena", 58),
            ("chiara", "TLC-FIBRA-100", "fabio", 21), ("alessio", "ENER-LUCE-GREEN", "davide", 50),
            ("silvia", "TLC-FIBRA-1000", "anna", 16), ("riccardo", "ENER-LUCE-STD", "tommaso", 28),
            ("giorgio", "ENER-LUCE-STD", "francesca", 36), ("studio", "ENER-BUSINESS", "roberto", 62),
            ("elena", "TLC-FIBRA-1000", "paolo", 75),
        ]
        activated = []
        for cust, product, seller, days in sales:
            customer, supply_point = c[cust]
            activated.append((await s.sale(customer, supply_point, product, seller, days), days))
        await s.sale(*c["valentina"], "TLC-MOBILE-5G", "giulia", 4, target="UNDER_REVIEW")
        await s.sale(*c["matteo"], "TLC-FIBRA-100", "andrea", 3, target="UNDER_REVIEW")
        await s.sale(*c["federica"], "TLC-FIBRA-1000", "martina", 2, target="DRAFT")
        await s.sale(*c["stefano"], "TLC-MOBILE-5G", "elena", 9, target="REJECTED")
        await process_pending_outbox_events(db)

        # --- commission lifecycle: older sales approved, oldest paid --------------------
        for contract, days in activated:
            rows = list((await db.execute(select(CommissionMovement.id).where(
                CommissionMovement.contract_id == contract.id,
                CommissionMovement.beneficiary_kind == "AGENT",
            ))).scalars())
            if not rows:
                continue
            if days >= 30:
                await lifecycle.transition(db, organization_id=org.id, movement_ids=rows, to_status="APPROVED",
                                           actor_user_id=admin.id, note="Approvazione dimostrativa")
            if days >= 60:
                await lifecycle.transition(db, organization_id=org.id, movement_ids=rows, to_status="PAID",
                                           actor_user_id=admin.id, note="Bonifico dimostrativo")

        # A paid sale later cancelled: its paid shares get a reversal.
        cancelled = next(contract for contract, days in activated if days == 70)
        cancelled = await db.get(Contract, cancelled.id)
        await contract_service.transition_contract(
            db, organization_id=org.id, contract=cancelled, to_status="CANCELLED", actor_user_id=admin.id,
            reason="Recesso del cliente (dimostrativo)", notes=None, correlation_id=str(uuid.uuid4()),
        )
        await process_pending_outbox_events(db)

        # --- leads -----------------------------------------------------------------------
        for name, status in (("Martina De Santis", None), ("Pizzeria Da Gino", "QUALIFIED"), ("Carlo Benedetti", "LOST")):
            lead = await leads_service.create_lead(
                db, organization_id=org.id, promoter_agent_id=s.agents["francesca"].id, actor_user_id=admin.id,
                contact_name=name, contact_phone="+39 347 000 0000",
                product_id=s.versions["TLC-FIBRA-1000"].product_id, notes="Interessato a un'offerta combinata.",
            )
            if status:
                await leads_service.update_lead(db, organization_id=org.id, lead_id=lead.id, actor_user_id=admin.id,
                                                values={"status": status})

    print()
    print("=" * 72)
    print("  Dati dimostrativi caricati")
    print("=" * 72)
    for label, email, password in s.credentials:
        print(f"  {label:<40} {email:<32} {password}")
    print("=" * 72)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.demo.showcase")
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--superadmin-email", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.organization_name, args.superadmin_email))


if __name__ == "__main__":
    sys.exit(main())

