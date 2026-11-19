"""A second, richer layer of showcase data on top of app.demo.showcase.

Adds 50 more accounts (20 collaborators, 30 customers), contract requests
paid in every way the platform supports (card in one payment, card in 3 or
12 instalments with a failed month, bank transfer confirmed, announced or
with a receipt, still unpaid), the commissions they generate across their
lifecycle, SosnetCash top-ups, welcome bonuses and transfers, the "Fai la
Spesa con Sosnet" shop with producers, photographed products and orders,
product photos for the catalog, support tickets and more leads.

Everything goes through the same services the application uses, then dates
are moved into the past so reports show a realistic spread. Product photos
come from Unsplash (free to use under the Unsplash License) and are copied
into our own media storage.

Emails are not wanted for this data: run it with SMTP disabled.

Usage (inside the api container, after app.demo.showcase):
    SMTP_HOST= python -m app.demo.enrich --organization-name SOSNET --superadmin-email admin@mamify.ai
"""

import argparse
import asyncio
import random
import sys
import urllib.request
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select, update

from app.demo.showcase import DEMO_DOMAIN, NOW, Showcase
from app.foundation.config import get_settings
from app.foundation.db import AsyncSessionLocal
from app.foundation.storage import upload_media
from app.modules.sosnet_market import service as market_service
from app.modules.sosnet_market.models import SosnetMarketOrder, SosnetMarketProducer
from app.modules.catalog.models import Product, ProductCategory, ProductVersion
from app.modules.commercial import service as commercial_service
from app.modules.commissions.models import CommissionCalculation, CommissionMovement, Rank
from app.modules.commissions.services import lifecycle
from app.modules.commissions.tasks.dispatch import process_pending_outbox_events
from app.modules.contracts import instalments as instalments_service
from app.modules.contracts import payment_plans
from app.modules.contracts import requests as requests_service
from app.modules.contracts import service as contract_service
from app.modules.contracts.models import Contract, ContractInstalment, ContractRequest, ContractRequestCheckout
from app.modules.contracts.requests import AddressData, HolderData
from app.modules.contracts.state_machine import ALLOWED_TRANSITIONS
from app.modules.customers.models import Customer
from app.modules.leads import service as leads_service
from app.modules.network import service as network_service
from app.modules.network.models import AgentProfile
from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.referral.models import PromoterCode
from app.modules.registry import load_model_metadata
from app.modules.support import service as support_service
from app.modules.support.models import Ticket
from app.modules.support.schemas import TicketCreate, TicketMessageCreate, TicketStatusUpdate
from app.modules.users.models import User
from app.modules.wallets import service as wallets_service
from app.modules.wallets.models import WalletTransaction

MARKER_PRODUCER = "Frantoio Colle Verde"
DEMO_IBAN = "IT60X0542811101000000123456"
TODAY = NOW.date()

random.seed(2026)

UNSPLASH = "https://images.unsplash.com/photo-{id}?w=1200&h=900&fit=crop&q=80&auto=format"

CATALOG_PHOTOS = {
    "ENER-LUCE-STD": "1474631245212-32dc3c8310c6",
    "ENER-LUCE-GREEN": "1509391366360-2e959784a276",
    "ENER-GAS-STD": "1590794056226-79ef3a8147e1",
    "ENER-BUSINESS": "1473341304170-971dccb5ac1e",
    "TLC-FIBRA-1000": "1558494949-ef010cbdcc31",
    "TLC-FIBRA-100": "1611095973763-414019e72400",
    "TLC-MOBILE-5G": "1512941937669-90a1b58e7e9c",
}

PRODUCERS = {
    "colle": (MARKER_PRODUCER, "Olio extravergine da olive raccolte a mano sulle colline umbre.", "Spoleto (PG)"),
    "cascina": ("Cascina dei Sapori", "Formaggi, riso e conserve di una cascina a conduzione familiare.", "Vercelli (VC)"),
    "aurora": ("Torrefazione Aurora", "Caffè tostato a legna in piccoli lotti, dal 1962.", "Napoli (NA)"),
    "fiorita": ("Apicoltura Valle Fiorita", "Miele di montagna e dolci artigianali.", "Aosta (AO)"),
    "molino": ("Pastificio Molino Antico", "Pasta trafilata al bronzo ed essiccata lentamente.", "Gragnano (NA)"),
    "poggio": ("Cantina Poggio Rosso", "Vini rossi da vigne storiche del Chianti.", "Greve in Chianti (FI)"),
    "orto": ("Orto di Casa", "Frutta e verdura di stagione raccolta il giorno prima della consegna.", "Latina (LT)"),
}

# (producer, name, description, photo, [(variant, price_cents, inventory)], credit %, unit cost)
MARKET_PRODUCTS = [
    ("colle", "Olio extravergine d'oliva", "Spremitura a freddo, fruttato medio, note di carciofo e mandorla.",
     "1474979266404-7eaacbcd87c5", [("Bottiglia 0,75 l", 1490, 120), ("Latta 3 l", 4990, 40)], 30, 820),
    ("aurora", "Caffè in grani Miscela Aurora", "70% arabica, 30% robusta, tostatura media: crema densa e persistente.",
     "1447933601403-0c6688de566e", [("Busta 500 g", 1190, 200), ("Busta 1 kg", 2090, 90)], 30, 610),
    ("cascina", "Pecorino stagionato 12 mesi", "Latte ovino crudo, crosta naturale, sapore deciso.",
     "1486297678162-eb2a19b0a32d", [("Spicchio 500 g", 1590, 60), ("Forma intera 2 kg", 5490, 12)], 25, 900),
    ("poggio", "Chianti Classico DOCG", "Sangiovese in purezza, 12 mesi in botte grande.",
     "1510812431401-41d2bd2722f3", [("Bottiglia", 1890, 80), ("Cassa da 6", 10490, 20)], 20, 1100),
    ("molino", "Penne rigate trafilate al bronzo", "Semola di grano duro italiano, essiccazione a bassa temperatura.",
     "1621996346565-e3dbc646d9a9", [("Pacco 500 g", 290, 400), ("Scatola 6 pacchi", 1590, 70)], 40, 140),
    ("fiorita", "Biscotti di frolla al burro", "Burro di montagna e uova fresche, senza conservanti.",
     "1558961363-fa8fdf82db35", [("Sacchetto 300 g", 690, 150)], 35, 320),
    ("fiorita", "Cioccolato fondente 72%", "Cacao monorigine con granella di nocciole.",
     "1606312619070-d48b4c652a52", [("Tavoletta 100 g", 450, 300), ("Confezione da 5", 1990, 60)], 35, 210),
    ("cascina", "Riso Carnaroli", "Il riso da risotto per eccellenza, lavorato a pietra.",
     "1586201375761-83865001e31c", [("Sacchetto 1 kg", 590, 250)], 40, 260),
    ("fiorita", "Miele millefiori di montagna", "Raccolto sopra i 1.200 metri, cristallizzazione fine.",
     "1558642452-9d2a7deb7f62", [("Vasetto 500 g", 990, 110), ("Vasetto 1 kg", 1790, 50)], 30, 520),
    ("cascina", "Passata di pomodoro", "Pomodori maturati al sole, solo pomodoro e un pizzico di sale.",
     "1592924357228-91a4daadcfea", [("Bottiglia 700 g", 350, 320), ("Cartone da 12", 3690, 40)], 40, 160),
    ("orto", "Cassetta frutta e verdura", "Un assortimento di stagione per una famiglia per una settimana.",
     "1542838132-92c53300491e", [("Cassetta 5 kg", 2490, 60), ("Cassetta 9 kg", 3990, 30)], 20, 1500),
    ("orto", "Cesta di frutta estiva", "Anguria, pesche e albicocche: il meglio dell'estate.",
     "1587049352846-4a222e784d38", [("Cesta 6 kg", 2990, 25)], 20, 1800),
]

# (key, first, last, commercial role, parent key, level, joined days ago)
NEW_AGENTS = [
    ("lorenzo", "Lorenzo", "De Luca", "NETWORKER", "sara", "SP2", 320),
    ("beatrice", "Beatrice", "Serra", "NETWORKER", "sara", "SP1", 210),
    ("nicola", "Nicola", "Ferrara", "NETWORKER", "lorenzo", "SP1", 190),
    ("ilaria", "Ilaria", "Bruno", "NETWORKER", "elisa", "SP2", 280),
    ("gabriele", "Gabriele", "Marchetti", "NETWORKER", "ilaria", "SP1", 150),
    ("sofia", "Sofia", "Rizzo", "NETWORKER", "martina", "SP1", 170),
    ("emanuele", "Emanuele", "Lombardi", "NETWORKER", "paolo", "SP3", 350),
    ("alice", "Alice", "Cattaneo", "NETWORKER", "emanuele", "SP1", 140),
    ("pietro", "Pietro", "Gentile", "PROMOTER", "giulia", "SP1", 120),
    ("camilla", "Camilla", "Monti", "PROMOTER", "emanuele", "SP1", 110),
    ("michele", "Michele", "Pellegrino", "AGENTE_PAP", "roberto", "SP2", 300),
    ("veronica", "Veronica", "Farina", "AGENTE_PAP", "roberto", "SP1", 260),
    ("daniele", "Daniele", "Orlando", "AGENTE_PAP", "roberto", "SP1", 180),
    ("marta", "Marta", "Sartori", "DELEGATO_INFLUENCER", "chiara", "SP1", 230),
    ("filippo", "Filippo", "Morelli", "DELEGATO_INFLUENCER", "chiara", "SP1", 160),
    ("greta", "Greta", "Valentini", "INFLUENCER", "marco", "SL1", 330),
    ("leonardo", "Leonardo", "Guerra", "DELEGATO_INFLUENCER", "greta", "SP1", 200),
    ("aurora", "Aurora", "Ferri", "NETWORKER", "andrea", "SP1", 130),
    ("tiziano", "Tiziano", "Rossetti", "NETWORKER", "nicola", "SP1", 125),
    ("noemi", "Noemi", "Caputo", "NETWORKER", "gabriele", "SP1", 115),
]

CITIES = [
    ("Via Garibaldi 14", "Torino", "TO", "10122"), ("Corso Buenos Aires 60", "Milano", "MI", "20124"),
    ("Via dei Mille 8", "Bologna", "BO", "40121"), ("Via Toledo 210", "Napoli", "NA", "80134"),
    ("Via Nazionale 45", "Roma", "RM", "00184"), ("Via Maqueda 120", "Palermo", "PA", "90133"),
    ("Corso Italia 33", "Firenze", "FI", "50123"), ("Via XX Settembre 5", "Genova", "GE", "16121"),
    ("Via Sparano 70", "Bari", "BA", "70121"), ("Riva degli Schiavoni 9", "Venezia", "VE", "30122"),
]

# (first, last, kind, referrer, product, points, payment scenario, days ago)
NEW_CUSTOMERS = [
    ("Martina", "Galli", "PRIVATE", "lorenzo", "ENER-LUCE-GREEN", 1, "card_full", 82),
    ("Tommaso", "Ricci", "PRIVATE", "lorenzo", "TLC-FIBRA-1000", 1, "card_12", 88),
    ("Giada", "Fontana", "PRIVATE", "beatrice", "ENER-GAS-STD", 1, "transfer_confirmed", 76),
    ("Andrea", "Marini", "PRIVATE", "nicola", "TLC-MOBILE-5G", 2, "card_3", 71),
    ("Elisa", "Coppola", "PRIVATE", "ilaria", "ENER-LUCE-STD", 1, "card_12_failed", 95),
    ("Pasticceria", "Dolce Vita", "SOLE_PROPRIETOR", "ilaria", "ENER-LUCE-STD", 2, "transfer_confirmed", 66),
    ("Francesco", "Leone", "PRIVATE", "gabriele", "TLC-FIBRA-100", 1, "card_full", 60),
    ("Irene", "Silvestri", "PRIVATE", "sofia", "ENER-LUCE-GREEN", 1, "card_3", 57),
    ("Carlo", "Vitale", "PRIVATE", "emanuele", "ENER-GAS-STD", 1, "card_12", 52),
    ("Serena", "Longo", "PRIVATE", "alice", "TLC-FIBRA-1000", 1, "transfer_confirmed", 48),
    ("Hotel", "Belvedere Srl", "COMPANY", "michele", "ENER-BUSINESS", 3, "card_12", 90),
    ("Autofficina", "Rossi Snc", "COMPANY", "veronica", "ENER-BUSINESS", 1, "transfer_confirmed", 44),
    ("Luisa", "Pace", "PRIVATE", "daniele", "ENER-LUCE-STD", 1, "card_full", 40),
    ("Roberta", "Neri", "PRIVATE", "marta", "TLC-FIBRA-1000", 1, "card_3", 37),
    ("Massimo", "Barone", "PRIVATE", "filippo", "ENER-LUCE-GREEN", 1, "card_12", 34),
    ("Giulia", "Messina", "PRIVATE", "leonardo", "TLC-MOBILE-5G", 1, "card_full", 30),
    ("Davide", "Greco", "PRIVATE", "greta", "ENER-LUCE-STD", 1, "transfer_confirmed", 27),
    ("Chiara", "Villa", "PRIVATE", "aurora", "TLC-FIBRA-100", 1, "card_3", 24),
    ("Enrico", "Santoro", "PRIVATE", "tiziano", "ENER-GAS-STD", 1, "card_12", 21),
    ("Ristorante", "Il Faro", "SOLE_PROPRIETOR", "noemi", "ENER-LUCE-STD", 2, "card_full", 18),
    ("Paola", "Martinelli", "PRIVATE", "sara", "TLC-FIBRA-1000", 1, "transfer_proof", 9),
    ("Alberto", "Costa", "PRIVATE", "luca", "ENER-LUCE-GREEN", 1, "transfer_pending", 7),
    ("Federico", "Moretti", "PRIVATE", "lorenzo", "TLC-MOBILE-5G", 1, "transfer_pending", 5),
    ("Studio", "Legale Ferri", "COMPANY", "michele", "ENER-BUSINESS", 1, "approved_unpaid", 6),
    ("Valeria", "Rinaldi", "PRIVATE", "beatrice", "ENER-LUCE-STD", 1, "approved_unpaid", 4),
    ("Stefania", "Gatti", "PRIVATE", "sofia", "TLC-FIBRA-100", 1, "under_review", 3),
    ("Marco", "Pellegrini", "PRIVATE", "gabriele", "ENER-GAS-STD", 1, "documents", 2),
    ("Anna", "De Rosa", "PRIVATE", "camilla", "TLC-FIBRA-1000", 1, "card_full_review", 3),
    ("Simona", "Ferraro", "PRIVATE", "pietro", "ENER-LUCE-STD", 1, "rejected", 12),
    ("Lucio", "Marchi", "PRIVATE", "alice", "TLC-MOBILE-5G", 1, "draft", 1),
]

PLAN_BY_SCENARIO = {
    "card_full": payment_plans.PLAN_FULL, "card_full_review": payment_plans.PLAN_FULL,
    "card_3": "INSTALMENTS_3", "card_12": "MONTHLY_12", "card_12_failed": "MONTHLY_12",
}

TOPUP_NOTES = [
    "Ricarica promozionale di benvenuto nella rete", "Premio gara di vendita di stagione",
    "Bonus fedeltà clienti storici", "Rimborso spese evento regionale", "Ricarica per acquisti nello Shop",
    "Premio obiettivo mensile raggiunto", "Compensazione disservizio",
]

TICKETS = [
    ("Fattura di agosto non ricevuta", "FATTURAZIONE", "Buongiorno, non trovo la fattura del mese di agosto nell'area clienti.",
     "Gliel'abbiamo appena rigenerata: la trova in Movimenti contabili.", "RESOLVED"),
    ("Cambio IBAN per l'addebito", "CONTRATTO", "Vorrei addebitare le prossime rate su un altro conto corrente.",
     "Certo: ci invii il nuovo IBAN intestato a lei e aggiorniamo il mandato.", "IN_PROGRESS"),
    ("Fibra lenta la sera", "ASSISTENZA_TECNICA", "Dalle 21 la velocità scende sotto i 50 Mega.", None, "OPEN"),
    ("Quando arriva il mio ordine?", "ALTRO", "Ho ordinato olio e miele cinque giorni fa, c'è un numero di tracciamento?",
     "L'ordine è partito ieri: trova il tracciamento nella sezione I miei ordini.", "CLOSED"),
    ("Provvigione non ancora visibile", "COMMISSIONI", "Il contratto di mia cliente è attivo da una settimana ma non vedo la quota.",
     "La quota matura con il primo incasso: è in approvazione, la vede tra le provvigioni da approvare.", "RESOLVED"),
    ("Documento d'identità scaduto", "CONTRATTO", "Mi avete chiesto un nuovo documento, posso caricarlo dall'app?", None, "OPEN"),
]

LEADS = [
    ("pietro", "Bar Sport Centrale", "QUALIFIED", "ENER-BUSINESS"), ("pietro", "Luigi Fabbri", None, "TLC-FIBRA-1000"),
    ("camilla", "Famiglia Gallo", None, "ENER-LUCE-GREEN"), ("camilla", "Palestra Energy Fit", "QUALIFIED", "ENER-BUSINESS"),
    ("francesca", "Gianna Rota", "LOST", "TLC-MOBILE-5G"), ("pietro", "Ottica Visione", None, "ENER-LUCE-STD"),
    ("camilla", "B&B Il Glicine", "QUALIFIED", "TLC-FIBRA-100"), ("francesca", "Mario Esposito", None, "ENER-GAS-STD"),
]

# A one-page PDF used as the bank transfer receipt of one request.
RECEIPT_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 66>>stream\nBT /F1 18 Tf 72 760 Td (Ricevuta bonifico - documento dimostrativo) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


def ago(days: float, hour: int = 10) -> datetime:
    moment = NOW - timedelta(days=days)
    return moment.replace(hour=hour, minute=random.randint(0, 59), second=0, microsecond=0)


def at_day(day: date, hour: int = 9) -> datetime:
    return datetime.combine(day, time(hour, random.randint(0, 59)), tzinfo=timezone.utc)


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month, d)
        except ValueError:
            continue
    return date(year, month, 28)


def fetch_photo(photo_id: str) -> bytes | None:
    request = urllib.request.Request(UNSPLASH.format(id=photo_id), headers={"User-Agent": "SOSNET demo seeder"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except Exception as exc:  # noqa: BLE001 -- a missing photo must not stop the seeding
        print(f"  foto {photo_id} non scaricata: {exc}", file=sys.stderr)
        return None


def store_photo(photo_id: str, prefix: str) -> str | None:
    data = fetch_photo(photo_id)
    if data is None:
        return None
    return upload_media(file_bytes=data, content_type="image/jpeg", key_prefix=prefix)


class Enrichment(Showcase):
    def __init__(self, db, org_id: uuid.UUID):
        super().__init__(db, org_id)
        self.users_by_agent: dict[str, User] = {}
        self.new_contracts: list[Contract] = []

    async def load(self) -> None:
        db = self.db
        self.roles = {r.code: r for r in await commercial_service.list_roles(db, organization_id=self.org_id)}
        self.categories = {c.code: c for c in (await db.execute(
            select(ProductCategory).where(ProductCategory.organization_id == self.org_id))).scalars()}
        self.ranks = {r.code: r for r in (await db.execute(
            select(Rank).where(Rank.organization_id == self.org_id))).scalars()}
        for product, version in (await db.execute(
            select(Product, ProductVersion).join(ProductVersion, ProductVersion.product_id == Product.id)
            .where(Product.organization_id == self.org_id, ProductVersion.status == "ACTIVE")
        )).all():
            self.versions[product.code] = version
        for code, agent in (await db.execute(
            select(PromoterCode, AgentProfile).join(AgentProfile, AgentProfile.id == PromoterCode.agent_id)
            .where(PromoterCode.organization_id == self.org_id)
        )).all():
            key = (agent.first_name or agent.display_name.split()[0]).lower()
            self.agents.setdefault(key, agent)
            self.codes.setdefault(key, code)
            if agent.user_id:
                self.users_by_agent[key] = await db.get(User, agent.user_id)

    # --- people -----------------------------------------------------------------

    async def new_agent(self, key, first, last, role, parent, rank, joined_days) -> None:
        joined = ago(joined_days)
        user = await self.user(f"{key}.{last.lower().replace(' ', '')}@{DEMO_DOMAIN}", first, last, ["PROMOTER"],
                               "Collaboratore")
        user.created_at = joined
        code = f"SOS-{first[:1]}{last}".upper().replace(" ", "").replace("'", "")[:20]
        agent = await network_service.create_agent(
            self.db, organization_id=self.org_id, first_name=first, last_name=last, promoter_code=code,
            parent_agent_id=self.agents[parent].id, joined_at=joined, actor_user_id=self.actor_id,
            current_rank_id=self.ranks[rank].id if rank in self.ranks else None,
            user_id=user.id, commercial_role_id=self.roles[role].id,
        )
        promoter_code = PromoterCode(
            organization_id=self.org_id, agent_id=agent.id, code=code,
            personal_link=f"{get_settings().public_app_base_url}/r/{code}", status="ACTIVE", valid_from=joined,
        )
        self.db.add(promoter_code)
        await self.db.commit()
        self.agents[key] = agent
        self.codes[key] = promoter_code
        self.users_by_agent[key] = user

    async def new_customer(self, first, last, kind, referrer, index) -> tuple[Customer, User]:
        email = f"{first.lower()}.{last.lower().split()[0]}{index}@{DEMO_DOMAIN}"
        customer, _ = await self.customer(kind, (first, last), email, referrer, login_email=email)
        user = await self.db.get(User, customer.user_id)
        street, city, province, postal = CITIES[index % len(CITIES)]
        user.residence_street, user.residence_city = street, city
        user.residence_province, user.residence_postal_code = province, postal
        await self.db.commit()
        return customer, user

    # --- contract requests ------------------------------------------------------

    async def advance(self, contract: Contract, targets: list[str], reason: str) -> Contract:
        """Walk the contract through the allowed transitions toward each
        target in turn, skipping the ones already passed."""
        for target in targets:
            contract = await self.db.get(Contract, contract.id)
            if contract.status == target or contract.status == "ACTIVE":
                continue
            if target not in ALLOWED_TRANSITIONS.get(contract.status, []):
                continue
            contract = await contract_service.transition_contract(
                self.db, organization_id=self.org_id, contract=contract, to_status=target,
                actor_user_id=self.actor_id, reason=reason, notes=None, correlation_id=str(uuid.uuid4()),
            )
        return contract

    async def pay_by_card(self, request: ContractRequest, plan_key: str, payer_id: uuid.UUID) -> None:
        points = requests_service.payable_points(await requests_service.list_points(self.db, request=request))
        plan = payment_plans.plan_by_key(plan_key)
        discount = 0
        if plan.instalments <= 1:
            discount = await organizations_service.get_contract_full_payment_discount_percentage(
                self.db, organization_id=self.org_id)
        option = next(o for o in requests_service.plan_options(points, discount_percentage=discount)
                      if o.plan.key == plan_key)
        lines = []
        for contract in points:
            breakdown = payment_plans.breakdown_for(plan, int(contract.gross_amount_cents or 0),
                                                    discount_percentage=discount)
            lines.append({"contract_id": str(contract.id), "gross_cents": int(contract.gross_amount_cents or 0),
                          "instalment_cents": breakdown.instalment_cents, "discount_cents": breakdown.discount_cents})
        checkout = ContractRequestCheckout(
            organization_id=self.org_id, contract_request_id=request.id,
            stripe_checkout_session_id=f"cs_demo_{uuid.uuid4().hex[:24]}", payment_plan=plan_key, lines=lines,
            total_cents=option.total_cents, instalment_cents=option.instalment_cents, created_by_user_id=payer_id,
        )
        self.db.add(checkout)
        await self.db.commit()
        subscription = f"sub_demo_{uuid.uuid4().hex[:20]}" if plan.instalments > 1 else None
        await requests_service.apply_checkout(
            self.db, checkout=checkout, stripe_invoice_id=f"in_demo_{uuid.uuid4().hex[:20]}",
            stripe_subscription_id=subscription, stripe_customer_id=f"cus_demo_{uuid.uuid4().hex[:14]}",
            subscription_items={str(c.id): f"si_demo_{uuid.uuid4().hex[:16]}" for c in points} if subscription else {},
        )

    async def pratica(self, customer: Customer, user: User, first: str, last: str, referrer: str, product: str,
                      points: int, scenario: str, days_ago: int, index: int) -> None:
        db = self.db
        sold = ago(days_ago, hour=11)
        street, city, province, postal = CITIES[index % len(CITIES)]
        promoter_user = self.users_by_agent.get(referrer)
        actor_id = promoter_user.id if promoter_user else self.actor_id
        request = await requests_service.create_request(
            db, organization_id=self.org_id, customer_id=customer.id,
            holder=HolderData(first_name=first, last_name=last, email=customer.email, pec=None, iban=DEMO_IBAN,
                              address=AddressData(street=street, city=city, province=province, postal_code=postal)),
            actor_user_id=actor_id, actor_role="PROMOTER" if promoter_user else "ADMIN",
            promoter_agent_id=self.agents[referrer].id, points_count=points,
            product_version_id=self.versions[product].id,
        )
        contracts = await requests_service.list_points(db, request=request)
        for contract in contracts:
            contract.sold_at = sold
            contract.created_at = sold
        request.created_at = sold
        await db.commit()
        if scenario == "draft":
            return

        request = await db.get(ContractRequest, request.id)
        await requests_service.submit_request(db, request=request, actor_user_id=actor_id)
        request = await db.get(ContractRequest, request.id)
        request.submitted_at = sold + timedelta(hours=1)
        await db.commit()
        if scenario == "documents":
            return

        # Payment first, as customers usually pay while the documents are checked.
        plan_key = PLAN_BY_SCENARIO.get(scenario)
        if plan_key:
            await self.pay_by_card(request, plan_key, user.id)
        elif scenario.startswith("transfer"):
            await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)
            request = await db.get(ContractRequest, request.id)
            request.bank_transfer_requested_at = sold + timedelta(hours=2)
            await db.commit()
            if scenario == "transfer_proof":
                await requests_service.upload_bank_transfer_proof(
                    db, request=request, file_bytes=RECEIPT_PDF, content_type="application/pdf",
                    original_filename="ricevuta-bonifico.pdf", actor_user_id=user.id,
                )
            if scenario == "transfer_confirmed":
                await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=self.actor_id)
                request = await db.get(ContractRequest, request.id)
                request.bank_transfer_confirmed_at = sold + timedelta(days=2)
                await db.commit()

        # Review outcome.
        contracts = await requests_service.list_points(db, request=request)
        for contract in contracts:
            if scenario in ("under_review", "card_full_review", "transfer_pending", "transfer_proof"):
                await self.advance(contract, ["UNDER_REVIEW"], "Documenti ricevuti")
            elif scenario == "rejected":
                await self.advance(contract, ["UNDER_REVIEW", "REJECTED"], "Documento d'identità non leggibile")
            elif scenario == "approved_unpaid":
                await self.advance(contract, ["UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING"], "Documenti approvati")
            else:
                await self.advance(contract, ["UNDER_REVIEW", "APPROVED", "PAYMENT_PENDING", "PAID", "ACTIVE"],
                                   "Documenti approvati")
            contract = await db.get(Contract, contract.id)
            await self.backdate_payments(contract, sold, scenario)
            self.new_contracts.append(contract)

    async def backdate_payments(self, contract: Contract, sold: datetime, scenario: str) -> None:
        """Move the payment schedule to the sale date and collect the monthly
        instalments already due, like Stripe would have."""
        db = self.db
        rows = await instalments_service.list_instalments(db, contract_id=contract.id)
        if not rows or contract.paid_at is None:
            return
        first_paid = sold + (timedelta(days=2) if scenario.startswith("transfer") else timedelta(hours=3))
        contract.paid_at = first_paid
        if contract.activated_at is not None:
            contract.activated_at = first_paid + timedelta(days=1)
            if contract.expires_at is not None:
                contract.expires_at = contract.activated_at + timedelta(days=365)
        for row in rows:
            row.due_date = add_months(first_paid.date(), row.number - 1)
            if row.status == "PAID":
                row.paid_at = first_paid
        await db.commit()
        if contract.status != "ACTIVE":
            return
        due = [r for r in rows if r.number > 1 and r.due_date <= TODAY]
        for row in due:
            invoice = f"in_demo_{uuid.uuid4().hex[:20]}"
            if scenario == "card_12_failed" and row is due[-1]:
                await instalments_service.record_failure(db, contract=contract, invoice_id=invoice)
                await db.commit()
                continue
            paid = await instalments_service.record_payment(
                db, contract=contract, source=instalments_service.SOURCE_STRIPE_INVOICE,
                number=row.number, invoice_id=invoice,
            )
            if paid is not None:
                paid.paid_at = at_day(row.due_date, hour=7)
            await db.commit()


async def backdate_commissions(db, contract_ids: list[uuid.UUID]) -> None:
    """Date each calculation and its movements on the instalment that
    released them, so reports spread over the months."""
    rows = list((await db.execute(select(ContractInstalment).where(
        ContractInstalment.contract_id.in_(contract_ids),
        ContractInstalment.commission_calculation_id.is_not(None),
    ))).scalars())
    for row in rows:
        when = row.paid_at or at_day(row.due_date)
        await db.execute(update(CommissionMovement).where(
            CommissionMovement.calculation_id == row.commission_calculation_id,
        ).values(created_at=when, effective_date=when.date()))
        await db.execute(update(CommissionCalculation).where(
            CommissionCalculation.id == row.commission_calculation_id,
        ).values(created_at=when))
    await db.commit()


async def commission_lifecycle(db, org_id: uuid.UUID, admin_id: uuid.UUID, contract_ids: list[uuid.UUID]) -> None:
    """Older shares are approved, then payable, then paid."""
    movements = list((await db.execute(select(CommissionMovement).where(
        CommissionMovement.contract_id.in_(contract_ids),
        CommissionMovement.beneficiary_kind == "AGENT",
        CommissionMovement.status == "PENDING",
    ))).scalars())
    by_step: dict[str, list[uuid.UUID]] = {"APPROVED": [], "PAYABLE": [], "PAID": []}
    for movement in movements:
        age = (NOW - movement.created_at).days
        if age >= 20:
            by_step["APPROVED"].append(movement.id)
        if age >= 40:
            by_step["PAYABLE"].append(movement.id)
        if age >= 55:
            by_step["PAID"].append(movement.id)
    notes = {"APPROVED": "Verifica mensile", "PAYABLE": "Pronta per il bonifico", "PAID": "Bonifico provvigioni"}
    for step, ids in by_step.items():
        if ids:
            await lifecycle.transition(db, organization_id=org_id, movement_ids=ids, to_status=step,
                                       actor_user_id=admin_id, note=notes[step])


async def wallets(db, org_id: uuid.UUID, admin_id: uuid.UUID, customers: list[User], promoters: list[User]) -> int:
    count = 0
    for i, user in enumerate(customers[:18]):
        txn, _ = await wallets_service.claim_welcome_bonus(db, organization_id=org_id, user_id=user.id)
        txn.created_at = ago(random.randint(20, 90))
        count += 1
    people = customers[::2] + promoters
    for i, user in enumerate(people):
        wallet = await wallets_service.get_or_create_wallet(db, organization_id=org_id, user_id=user.id)
        for n in range(random.randint(1, 3)):
            txn = await wallets_service.credit_wallet(
                db, organization_id=org_id, wallet_id=wallet.id, amount_cents=random.choice([500, 1000, 1500, 2500, 5000, 7500, 10000]),
                type_="ADMIN_CREDIT", actor_user_id=admin_id, source="MANUAL_ADMIN",
                note=random.choice(TOPUP_NOTES), idempotency_key=f"demo-topup:{user.id}:{n}",
            )
            txn.created_at = ago(random.randint(3, 120))
            count += 1
    await db.commit()
    # A few collaborators may send SosnetCash to each other.
    senders = promoters[:5]
    for i, sender in enumerate(senders):
        wallet = await wallets_service.set_transfer_permission(db, organization_id=org_id, user_id=sender.id,
                                                               can_transfer=True)
        target = promoters[(i + 3) % len(promoters)]
        target_wallet = await wallets_service.get_or_create_wallet(db, organization_id=org_id, user_id=target.id)
        await db.commit()
        if wallet.balance_cents >= 1000:
            txn = await wallets_service.debit_and_transfer(
                db, organization_id=org_id, from_wallet_id=wallet.id, to_address=target_wallet.address,
                amount_cents=1000, actor_user_id=sender.id, note="Grazie per l'aiuto con il cliente",
                idempotency_key=f"demo-transfer:{sender.id}",
            )
            txn.created_at = ago(random.randint(2, 30))
            count += 1
    await db.commit()
    return count


async def market(db, org_id: uuid.UUID, admin_id: uuid.UUID, buyers: list[User]) -> tuple[int, int]:
    settings_row = await market_service.get_settings_row(db, organization_id=org_id)
    await market_service.update_settings(db, row=settings_row, actor_user_id=admin_id, updates={
        "enabled": True, "shipping_mode": "CUSTOMER_PAYS", "shipping_flat_cents": 690, "shipping_days": "2-4",
    })
    producers = {}
    for key, (name, description, city) in PRODUCERS.items():
        producers[key] = await market_service.create_producer(db, organization_id=org_id, actor_user_id=admin_id, payload={
            "name": name, "description": description, "address": city,
            "email": f"ordini@{key}.example.demo", "phone": "+39 0000 000000", "vat_number": "IT00000000000",
        })
    variants = []
    for producer, name, description, photo, variant_rows, credit, cost in MARKET_PRODUCTS:
        image = store_photo(photo, "demo/market")
        product = await market_service.create_product(db, organization_id=org_id, actor_user_id=admin_id, payload={
            "name": name, "description": description, "image_url": image, "images": [image] if image else [],
            "credit_discount_percentage": credit, "unit_cost_cents": cost, "producer_id": producers[producer].id,
            "variants": [{"label": label, "price_cents": price, "inventory": stock} for label, price, stock in variant_rows],
        })
        variants.extend(await market_service._variants(db, product.id))

    # (days ago, payment, outcome)
    plans = [
        (58, "BANK_TRANSFER", "delivered"), (51, "CARD", "delivered"), (44, "CARD", "delivered"),
        (37, "BANK_TRANSFER", "delivered"), (29, "CARD", "shipped"), (22, "BANK_TRANSFER", "shipped"),
        (16, "CARD", "paid"), (12, "BANK_TRANSFER", "paid"), (9, "CARD", "paid"), (6, "BANK_TRANSFER", "awaiting"),
        (4, "BANK_TRANSFER", "awaiting"), (3, "CARD", "cancelled"), (2, "BANK_TRANSFER", "awaiting"), (1, "CARD", "paid"),
        (33, "BANK_TRANSFER", "cancelled"), (26, "CARD", "delivered"),
    ]
    orders = 0
    carriers = ["BRT", "GLS", "SDA", "Poste Italiane"]
    for i, (days, method, outcome) in enumerate(plans):
        buyer = buyers[i % len(buyers)]
        picks = random.sample(variants, k=random.randint(1, 3))
        lines = [(v.id, random.randint(1, 3)) for v in picks]
        order = await market_service.create_order(
            db, organization_id=org_id, customer_user_id=buyer.id,
            address={"recipient_name": buyer.email.split("@")[0].replace(".", " ").title(), "recipient_phone": "+39 333 000 0000",
                     "address_line1": buyer.residence_street or "Via Roma 1", "city": buyer.residence_city or "Milano",
                     "province": buyer.residence_province or "MI", "postal_code": buyer.residence_postal_code or "20100"},
            credit_applied_cents=0, payment_method="BANK_TRANSFER", actor_user_id=buyer.id, otp_code=None,
            note=None, lines=lines,
        )
        created = ago(days, hour=random.randint(8, 21))
        order = await db.get(SosnetMarketOrder, order.id)
        if method == "CARD":
            order.payment_method = "CARD"
            order.stripe_checkout_session_id = f"cs_demo_{uuid.uuid4().hex[:24]}"
            await db.commit()
        if outcome in ("paid", "shipped", "delivered"):
            if method == "CARD":
                await market_service.mark_paid_by_session(
                    db, organization_id=org_id, stripe_checkout_session_id=order.stripe_checkout_session_id)
            else:
                await market_service.confirm_payment(db, organization_id=org_id, order_id=order.id, actor_user_id=admin_id)
        if outcome in ("shipped", "delivered"):
            await market_service.mark_shipped(
                db, organization_id=org_id, order_id=order.id, actor_user_id=admin_id,
                tracking_number=f"DEMO{random.randint(10**9, 10**10 - 1)}", tracking_url=None,
                tracking_company=random.choice(carriers),
            )
        if outcome == "delivered":
            await market_service.mark_delivered(db, organization_id=org_id, order_id=order.id, actor_user_id=admin_id)
        if outcome == "cancelled":
            await market_service.cancel_order(db, organization_id=org_id, order_id=order.id,
                                              reason="Il cliente ha annullato l'ordine", actor_user_id=admin_id)
        order = await db.get(SosnetMarketOrder, order.id)
        order.created_at = created
        if order.paid_at is not None:
            order.paid_at = created + timedelta(hours=2 if method == "CARD" else 30)
        await db.commit()
        orders += 1
    return len(MARKET_PRODUCTS), orders


async def run(organization_name: str, superadmin_email: str) -> int:
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organization).where(Organization.name == organization_name))).scalars().first()
        if org is None:
            print(f"Organizzazione «{organization_name}» non trovata.", file=sys.stderr)
            return 1
        admin = (await db.execute(select(User).where(
            User.organization_id == org.id, User.email == superadmin_email.lower()))).scalars().first()
        if admin is None:
            print(f"Nessun account {superadmin_email} in «{organization_name}».", file=sys.stderr)
            return 1
        if not (await db.execute(select(User.id).where(User.email == f"admin@{DEMO_DOMAIN}"))).first():
            print("Prima carica i dati di base con app.demo.showcase.", file=sys.stderr)
            return 1
        if (await db.execute(select(SosnetMarketProducer.id).where(
                SosnetMarketProducer.organization_id == org.id, SosnetMarketProducer.name == MARKER_PRODUCER))).first():
            print("I dati aggiuntivi sono già presenti: niente da fare.", file=sys.stderr)
            return 1

        s = Enrichment(db, org.id)
        s.actor_id = admin.id
        await s.load()

        # Bank transfers need an IBAN on the organization; a demo one is set for
        # the duration of the seeding and the previous settings are restored.
        original_settings = dict(org.settings or {})
        org.settings = {**original_settings, "bank_iban": DEMO_IBAN, "bank_holder": "SOSNET S.r.l. (demo)"}
        await db.commit()
        try:
            print("Foto del catalogo…")
            for code, photo in CATALOG_PHOTOS.items():
                version = s.versions.get(code)
                if version is not None and not version.image_url:
                    version.image_url = store_photo(photo, "demo/catalog")
            await db.commit()

            print("Collaboratori…")
            for row in NEW_AGENTS:
                await s.new_agent(*row)

            print("Clienti e pratiche…")
            customer_users = []
            for i, (first, last, kind, referrer, product, points, scenario, days) in enumerate(NEW_CUSTOMERS):
                customer, user = await s.new_customer(first, last, kind, referrer, i)
                customer_users.append(user)
                await s.pratica(customer, user, first, last, referrer, product, points, scenario, days, i)
            await process_pending_outbox_events(db)

            contract_ids = [c.id for c in s.new_contracts]
            await backdate_commissions(db, contract_ids)
            await commission_lifecycle(db, org.id, admin.id, contract_ids)

            print("Portafogli…")
            promoter_users = [s.users_by_agent[key] for key, *_ in NEW_AGENTS]
            wallet_rows = await wallets(db, org.id, admin.id, customer_users, promoter_users)

            print("Fai la Spesa con Sosnet…")
            market_products, market_orders = await market(db, org.id, admin.id, customer_users)

            print("Assistenza e segnalazioni…")
            for i, (subject, category, message, answer, status) in enumerate(TICKETS):
                opener = customer_users[i * 3] if i % 2 == 0 else promoter_users[i]
                role = "CUSTOMER" if i % 2 == 0 else "PROMOTER"
                ticket = await support_service.create_ticket(
                    db, organization_id=org.id, actor_user_id=opener.id, actor_role=role,
                    payload=TicketCreate(subject=subject, category=category, message=message),
                )
                if answer:
                    await support_service.add_message(
                        db, organization_id=org.id, ticket_id=ticket.id, actor_user_id=admin.id, actor_role="ADMIN",
                        requester_is_staff=True, payload=TicketMessageCreate(body=answer),
                    )
                if status != "OPEN":
                    await support_service.update_status(
                        db, organization_id=org.id, ticket_id=ticket.id, actor_user_id=admin.id,
                        payload=TicketStatusUpdate(status=status),
                    )
                ticket = await db.get(Ticket, ticket.id)
                ticket.created_at = ago(random.randint(1, 25))
                await db.commit()
            for promoter, name, status, product in LEADS:
                lead = await leads_service.create_lead(
                    db, organization_id=org.id, promoter_agent_id=s.agents[promoter].id, actor_user_id=admin.id,
                    contact_name=name, contact_phone="+39 340 000 0000",
                    product_id=s.versions[product].product_id, notes="Contatto raccolto a un evento sul territorio.",
                )
                if status:
                    await leads_service.update_lead(db, organization_id=org.id, lead_id=lead.id, actor_user_id=admin.id,
                                                    values={"status": status})
        finally:
            org = await db.get(Organization, org.id)
            org.settings = original_settings
            await db.commit()

        movements = (await db.execute(select(CommissionMovement.status).where(
            CommissionMovement.contract_id.in_(contract_ids)))).scalars().all()
        instalments = (await db.execute(select(ContractInstalment.status).where(
            ContractInstalment.contract_id.in_(contract_ids)))).scalars().all()
        wallet_total = (await db.execute(select(WalletTransaction.id).where(
            WalletTransaction.organization_id == org.id))).scalars().all()

    print()
    print("=" * 72)
    print("  Dati aggiuntivi caricati")
    print("=" * 72)
    print(f"  Account nuovi            {len(NEW_AGENTS) + len(NEW_CUSTOMERS)} ({len(NEW_AGENTS)} collaboratori, {len(NEW_CUSTOMERS)} clienti)")
    print(f"  Contratti nuovi          {len(contract_ids)}")
    print(f"  Rate                     " + ", ".join(f"{s} {instalments.count(s)}" for s in sorted(set(instalments))))
    print(f"  Provvigioni              " + ", ".join(f"{s} {movements.count(s)}" for s in sorted(set(movements))))
    print(f"  Movimenti portafoglio    {wallet_rows} nuovi, {len(wallet_total)} in totale")
    print(f"  Shop                     {market_products} prodotti, {market_orders} ordini")
    print(f"  Ticket / segnalazioni    {len(TICKETS)} / {len(LEADS)}")
    print("=" * 72)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Every model must be known before the first flush: wallet rows reference shop tables.
    load_model_metadata()
    parser = argparse.ArgumentParser(prog="python -m app.demo.enrich")
    parser.add_argument("--organization-name", required=True)
    parser.add_argument("--superadmin-email", required=True)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.organization_name, args.superadmin_email))


if __name__ == "__main__":
    sys.exit(main())
