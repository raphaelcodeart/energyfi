"""Contract dossier: every attachment plus a summary PDF.

Lets administrators send a contract's paperwork outside the platform
(supplier, accountant, lawyer) in one piece. The same content is delivered
as a browser zip (`router.py::download_contract_dossier`) or a Google Drive
folder (`integrations/google_drive.py`); only this module builds it, so the
two cannot diverge.

Folder/archive name: `<customer name>-<contract id>`, using the display name
from `customers/service.py::display_name_for` and the full UUID.
"""

import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.storage import download_document
from app.modules.catalog.models import Product, ProductVersion
from app.modules.contracts.models import Contract, ContractAttribution
from app.modules.customers.models import Address, Company, Customer, CustomerProfile, SupplyPoint
from app.modules.customers.service import display_name_for
from app.modules.documents import service as documents_service
from app.modules.documents.models import Document
from app.modules.documents.schemas import DOCUMENT_TYPE_LABELS
from app.modules.network.models import AgentProfile
from app.modules.organizations.models import Organization

SUMMARY_FILENAME = "00 - Riepilogo contratto.pdf"

CUSTOMER_KIND_LABELS = {
    "PRIVATE": "Privato",
    "SOLE_PROPRIETOR": "Ditta individuale / Partita IVA",
    "COMPANY": "Azienda",
    "CONDOMINIUM": "Condominio",
}
ENERGY_TYPE_LABELS = {"ELECTRICITY": "Luce", "GAS": "Gas", "DUAL_FUEL": "Luce e Gas"}
CONTRACT_STATUS_LABELS = {
    "DRAFT": "Bozza", "SUBMITTED": "Inviata", "DOCUMENTS_PENDING": "Documenti mancanti",
    "UNDER_REVIEW": "In revisione", "APPROVED": "Approvata",
    "PAYMENT_PENDING": "In attesa di pagamento", "PAID": "Pagata",
    "ACTIVATION_PENDING": "In attivazione", "ACTIVE": "Attiva", "SUSPENDED": "Sospesa",
    "CANCELLED": "Cessata", "EXPIRED": "Scaduta", "RENEWED": "Rinnovata", "REJECTED": "Respinta",
}
DOCUMENT_STATUS_LABELS = {
    "PENDING_REVIEW": "In attesa di verifica", "APPROVED": "Approvato", "REJECTED": "Respinto",
}
PAYMENT_PLAN_LABELS = {
    "FULL": "Soluzione unica", "INSTALMENTS_3": "3 rate mensili", "MONTHLY_12": "12 rate mensili",
}

#: Characters Windows, macOS or Drive reject or interpret in file names.
#: Spaces are kept so names match the customer's.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
#: Windows device names, reserved regardless of extension.
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
MAX_NAME_COMPONENT = 80


def sanitize_filename_component(value: str, *, fallback: str = "documento") -> str:
    """A file-name component safe on Windows, macOS, Linux and Drive.

    Accents are kept. Path-breaking characters, trailing dots/spaces (which
    Windows would strip silently) and reserved DOS device names are removed
    or escaped."""
    cleaned = _ILLEGAL_FILENAME_CHARS.sub(" ", value)
    cleaned = " ".join(cleaned.split()).strip(" .")
    if cleaned.upper() in _RESERVED_WINDOWS_NAMES:
        cleaned = f"_{cleaned}"
    if len(cleaned) > MAX_NAME_COMPONENT:
        cleaned = cleaned[:MAX_NAME_COMPONENT].strip(" .")
    return cleaned or fallback


@dataclass(frozen=True)
class DossierFile:
    name: str
    content: bytes
    content_type: str


@dataclass(frozen=True)
class Dossier:
    contract_id: uuid.UUID
    customer_name: str
    #: "<customer name>-<contract id>": zip name (without extension) and
    #: Drive folder name.
    folder_name: str
    files: list[DossierFile]

    @property
    def zip_filename(self) -> str:
        return f"{self.folder_name}.zip"


def _fmt_date(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _fmt_datetime(value: datetime | None) -> str:
    return value.strftime("%d/%m/%Y %H:%M") if value else "—"


def _fmt_cents(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 100:,.2f} €".replace(",", "_").replace(".", ",").replace("_", ".")


def _fmt_address(address: Address | None) -> str:
    if address is None:
        return "—"
    return f"{address.street}, {address.postal_code} {address.city} ({address.province}) {address.country}"


def _or_dash(value: str | None) -> str:
    return value if value else "—"


def _extension_for(document: Document) -> str:
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
    }.get(document.content_type, "")


def _document_label(document: Document) -> str:
    if document.description:
        return document.description
    return DOCUMENT_TYPE_LABELS.get(document.document_type, document.document_type)


# --- Data loading ------------------------------------------------------------


@dataclass
class _ContractContext:
    contract: Contract
    customer: Customer | None
    customer_name: str
    company: Company | None
    supply_point: SupplyPoint | None
    supply_address: Address | None
    billing_address: Address | None
    product_name: str | None
    product_code: str | None
    producer_name: str | None
    first_referrer_name: str | None
    organization_name: str
    documents: list[Document]


async def _agent_name(db: AsyncSession, agent_id: uuid.UUID | None) -> str | None:
    if agent_id is None:
        return None
    agent = await db.get(AgentProfile, agent_id)
    return agent.display_name if agent else None


async def _load_context(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract
) -> _ContractContext:
    customer = await db.get(Customer, contract.customer_id)
    profile = await db.get(CustomerProfile, customer.id) if customer else None
    company = await db.get(Company, customer.id) if customer else None
    customer_name = display_name_for(customer.kind, profile, company) if customer else "Cliente"

    supply_point = await db.get(SupplyPoint, contract.supply_point_id)
    supply_address = await db.get(Address, supply_point.supply_address_id) if supply_point else None
    billing_address = None
    if customer is not None:
        billing_address = (
            await db.execute(
                select(Address).where(
                    Address.customer_id == customer.id, Address.kind == "BILLING"
                )
            )
        ).scalars().first()

    product_name = product_code = None
    version = await db.get(ProductVersion, contract.product_version_id) if contract.product_version_id else None
    if version is not None:
        product_name = version.name
        product = await db.get(Product, version.product_id)
        product_code = product.code if product else None

    producer_name = first_referrer_name = None
    if contract.contract_attribution_id is not None:
        attribution = await db.get(ContractAttribution, contract.contract_attribution_id)
        if attribution is not None:
            producer_name = await _agent_name(db, attribution.producer_agent_id)
    first_referrer_name = await _agent_name(db, contract.first_referrer_agent_id)

    organization = await db.get(Organization, organization_id)

    # Shared request documents (identity, tax code, company registration)
    # first, then this contract's own, so each dossier is self-contained.
    shared = await documents_service.list_documents_for_request(
        db, organization_id=organization_id, contract_request_id=contract.contract_request_id
    )
    own = await documents_service.list_documents_for_contract(
        db, organization_id=organization_id, contract_id=contract.id
    )
    # Lists come newest first; the dossier uses upload order.
    documents = list(reversed(shared)) + list(reversed(own))

    return _ContractContext(
        contract=contract,
        customer=customer,
        customer_name=customer_name,
        company=company,
        supply_point=supply_point,
        supply_address=supply_address,
        billing_address=billing_address,
        product_name=product_name,
        product_code=product_code,
        producer_name=producer_name,
        first_referrer_name=first_referrer_name,
        organization_name=organization.name if organization else "—",
        documents=documents,
    )


# --- Summary PDF -------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DossierTitle", parent=base["Title"], fontSize=17, leading=21,
            alignment=TA_LEFT, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "DossierSubtitle", parent=base["Normal"], fontSize=9, leading=12,
            textColor=colors.HexColor("#64748b"),
        ),
        "section": ParagraphStyle(
            "DossierSection", parent=base["Heading2"], fontSize=11, leading=14,
            spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#0842b0"),
        ),
        "cell": ParagraphStyle("DossierCell", parent=base["Normal"], fontSize=8.5, leading=11),
        "footer": ParagraphStyle(
            "DossierFooter", parent=base["Normal"], fontSize=7.5, leading=10,
            textColor=colors.HexColor("#94a3b8"),
        ),
    }


def _facts_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(f"<b>{label}</b>", styles["cell"]), Paragraph(value, styles["cell"])]
            for label, value in rows]
    table = Table(data, colWidths=[52 * mm, 116 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e2e8f0")),
        ])
    )
    return table


def _escape(value: str) -> str:
    """Escape text for reportlab's markup so values like '&' cannot break
    the PDF."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_summary_pdf(ctx: _ContractContext, *, generated_at: datetime) -> bytes:
    styles = _styles()
    c = ctx.contract
    story: list = []

    story.append(Paragraph(_escape(f"Riepilogo contratto — {ctx.customer_name}"), styles["title"]))
    story.append(Paragraph(
        _escape(
            f"{ctx.organization_name} · contratto {c.id} · documento generato il "
            f"{_fmt_datetime(generated_at)}"
        ),
        styles["subtitle"],
    ))

    story.append(Paragraph("Contratto", styles["section"]))
    story.append(_facts_table([
        ("Stato", CONTRACT_STATUS_LABELS.get(c.status, c.status)),
        ("Prodotto", _escape(_or_dash(ctx.product_name))),
        ("Codice prodotto", _escape(_or_dash(ctx.product_code))),
        ("Creato il", _fmt_datetime(c.created_at)),
        ("Attivato il", _fmt_date(c.activated_at)),
        ("Scadenza / rinnovo", _fmt_date(c.expires_at)),
        ("Intestatario", _escape(_or_dash(
            " ".join(part for part in (c.holder_first_name, c.holder_last_name) if part) or None
        ))),
        ("Email del contratto", _escape(_or_dash(c.email))),
        ("PEC del contratto", _escape(_or_dash(c.pec))),
        ("Note", _escape(_or_dash(c.notes))),
    ], styles))

    story.append(Paragraph("Cliente", styles["section"]))
    customer = ctx.customer
    customer_rows = [
        ("Intestatario", _escape(ctx.customer_name)),
        ("Tipologia", CUSTOMER_KIND_LABELS.get(customer.kind, customer.kind) if customer else "—"),
        ("Codice fiscale", _escape(_or_dash(customer.fiscal_code if customer else None))),
        ("Partita IVA", _escape(_or_dash(customer.vat_number if customer else None))),
    ]
    if ctx.company is not None:
        customer_rows += [
            ("Ragione sociale", _escape(ctx.company.company_name)),
            ("Forma giuridica", _escape(_or_dash(ctx.company.legal_form))),
            ("Codice SDI", _escape(_or_dash(ctx.company.sdi_code))),
        ]
    customer_rows += [
        ("Email", _escape(_or_dash(customer.email if customer else None))),
        ("Telefono", _escape(_or_dash(customer.phone if customer else None))),
        ("PEC", _escape(_or_dash(customer.pec if customer else None))),
        ("Indirizzo di fatturazione", _escape(_fmt_address(ctx.billing_address))),
    ]
    story.append(_facts_table(customer_rows, styles))

    story.append(Paragraph("Punto di fornitura", styles["section"]))
    sp = ctx.supply_point
    story.append(_facts_table([
        ("Denominazione", _escape(_or_dash(sp.label if sp else None))),
        ("Tipo di fornitura", _escape(_or_dash(ENERGY_TYPE_LABELS.get(sp.energy_type, sp.energy_type) if sp else None))),
        ("Codice POD", _escape(_or_dash(sp.pod_code if sp else None))),
        ("Codice PDR", _escape(_or_dash(sp.pdr_code if sp else None))),
        ("Matricola contatore", _escape(_or_dash(sp.meter_number if sp else None))),
        ("Indirizzo di fornitura", _escape(_fmt_address(ctx.supply_address))),
    ], styles))

    story.append(Paragraph("Importi e pagamento", styles["section"]))
    vat_rate = f"{float(c.vat_rate):.0f}%" if c.vat_rate is not None else "—"
    story.append(_facts_table([
        ("Imponibile", _fmt_cents(c.net_amount_cents)),
        ("IVA", f"{_fmt_cents(c.vat_amount_cents)} ({vat_rate})"),
        ("Totale", _fmt_cents(c.gross_amount_cents)),
        ("Modalità scelta", PAYMENT_PLAN_LABELS.get(c.payment_plan or "", _or_dash(c.payment_plan))),
        ("Metodo", _escape(_or_dash(c.payment_method))),
        ("Pagato il", _fmt_datetime(c.paid_at)),
        ("IBAN per l'addebito", _escape(_or_dash(c.iban))),
        ("Riferimento Stripe", _escape(_or_dash(c.stripe_subscription_id or c.stripe_checkout_session_id))),
    ], styles))

    story.append(Paragraph("Rete commerciale", styles["section"]))
    story.append(_facts_table([
        ("Promoter che ha attivato", _escape(_or_dash(ctx.producer_name))),
        ("Promoter che ha portato il cliente", _escape(_or_dash(ctx.first_referrer_name))),
        ("Creato da", _escape(_or_dash(c.created_by_role))),
        ("Condizioni accettate il", _fmt_datetime(c.terms_accepted_at)),
    ], styles))

    story.append(Paragraph("Documenti allegati", styles["section"]))
    if not ctx.documents:
        story.append(Paragraph("Nessun documento allegato a questo contratto.", styles["cell"]))
    else:
        header = [Paragraph(f"<b>{h}</b>", styles["cell"])
                  for h in ("File", "Documento", "Stato", "Caricato il")]
        rows = [header]
        for index, document in enumerate(ctx.documents, start=1):
            rows.append([
                Paragraph(_escape(_file_name_for(index, document)), styles["cell"]),
                Paragraph(_escape(_document_label(document)), styles["cell"]),
                Paragraph(DOCUMENT_STATUS_LABELS.get(document.status, document.status), styles["cell"]),
                Paragraph(_fmt_date(document.created_at), styles["cell"]),
            ])
        table = Table(rows, colWidths=[62 * mm, 50 * mm, 32 * mm, 24 * mm], hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#cbd5e1")),
            ("LINEBELOW", (0, 1), (-1, -2), 0.4, colors.HexColor("#e2e8f0")),
        ]))
        story.append(table)

    story.append(Spacer(1, 10 * mm))
    story.append(KeepTogether(Paragraph(
        "Documento generato automaticamente dal gestionale. Contiene dati personali: "
        "trattalo di conseguenza e non ricondividerlo oltre chi ne ha bisogno.",
        styles["footer"],
    )))

    buffer = io.BytesIO()
    SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Riepilogo contratto {ctx.contract.id}",
        author=ctx.organization_name,
    ).build(story)
    return buffer.getvalue()


def _file_name_for(index: int, document: Document) -> str:
    """`NN - <label><ext>`. Numbered to preserve order and to disambiguate
    attachments sharing a label."""
    label = sanitize_filename_component(_document_label(document), fallback="Documento")
    return f"{index:02d} - {label}{_extension_for(document)}"


# --- Assembly ----------------------------------------------------------------


async def build_dossier(
    db: AsyncSession, *, organization_id: uuid.UUID, contract: Contract, generated_at: datetime | None = None
) -> Dossier:
    """Download every attachment from private storage and add the summary
    PDF. Authorization is the caller's responsibility."""
    ctx = await _load_context(db, organization_id=organization_id, contract=contract)
    generated_at = generated_at or datetime.now(UTC)

    files = [
        DossierFile(
            name=SUMMARY_FILENAME,
            content=render_summary_pdf(ctx, generated_at=generated_at),
            content_type="application/pdf",
        )
    ]

    used_names = {SUMMARY_FILENAME.lower()}
    for index, document in enumerate(ctx.documents, start=1):
        try:
            content = download_document(storage_key=document.storage_key)
        except Exception as exc:  # noqa: BLE001 -- see below
            # A missing object must not fail the whole dossier; a text
            # placeholder states what is missing.
            content = (
                f"Il file non è stato recuperato dall'archivio.\n\n"
                f"Documento: {_document_label(document)}\n"
                f"Nome originale: {document.original_filename}\n"
                f"ID documento: {document.id}\n"
                f"Errore: {type(exc).__name__}\n"
            ).encode()
            name = f"{index:02d} - {sanitize_filename_component(_document_label(document))} (MANCANTE).txt"
            files.append(DossierFile(name=name, content=content, content_type="text/plain"))
            continue

        name = _file_name_for(index, document)
        if name.lower() in used_names:
            stem, _, extension = name.rpartition(".")
            name = f"{stem} ({index}).{extension}" if stem else f"{name} ({index})"
        used_names.add(name.lower())
        files.append(DossierFile(name=name, content=content, content_type=document.content_type))

    folder_name = f"{sanitize_filename_component(ctx.customer_name, fallback='Cliente')}-{contract.id}"
    return Dossier(
        contract_id=contract.id,
        customer_name=ctx.customer_name,
        folder_name=folder_name,
        files=files,
    )


def zip_bytes(dossier: Dossier) -> bytes:
    """Deflate: attachments are mostly pre-compressed, but the summary and
    placeholders are not, and the cost is negligible."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in dossier.files:
            archive.writestr(file.name, file.content)
    return buffer.getvalue()
