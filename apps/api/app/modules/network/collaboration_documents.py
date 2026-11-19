"""Documents a customer must read and accept to become a Promoter.

The legal text lives on the server and reaches the dashboard through
`GET /network/agents/apply/documents`, not inside a React component: what
people sign must have exactly one versioned copy, the acceptance record is
only meaningful if text and version are defined together, and changes must
not require a dashboard release.

**Adding a document**: append to `COLLABORATION_DOCUMENTS`. The dashboard
renders one panel and one checkbox per entry, and the backend rejects any
application that does not accept every entry at its current version.

**Changing a document's text**: bump its `version`. New applicants record the
new version; past acceptances keep theirs. Never change text without bumping,
or it would silently restate what somebody already signed.
"""

from dataclasses import dataclass, field

# --- Block types the dashboard can render -----------------------------------
#
# Structured data rather than HTML or Markdown: legal text from the server is
# formatted by the UI, never interpreted as markup in the customer's browser.

BLOCK_HEADING = "heading"
BLOCK_PARAGRAPH = "paragraph"
BLOCK_CLAUSE = "clause"
BLOCK_BULLETS = "bullets"
BLOCK_TABLE = "table"
BLOCK_SIGNATURE = "signature"


def heading(text: str) -> dict:
    return {"type": BLOCK_HEADING, "text": text}


def paragraph(text: str) -> dict:
    return {"type": BLOCK_PARAGRAPH, "text": text}


def clause(number: str, text: str) -> dict:
    """A numbered contract clause, e.g. ("3.4.", "Il Procacciatore non potra ...")."""
    return {"type": BLOCK_CLAUSE, "number": number, "text": text}


def bullets(*items: str) -> dict:
    return {"type": BLOCK_BULLETS, "items": list(items)}


def table(columns: list[str], rows: list[list[str]], caption: str | None = None) -> dict:
    """For figures people agree to (e.g. Allegato A compensation, Allegato B
    progression schema), which must be readable as a table."""
    return {"type": BLOCK_TABLE, "columns": columns, "rows": rows, "caption": caption}


def signature(text: str) -> dict:
    """A document's closing declaration, rendered as a callout so it is clear
    which text the checkbox covers."""
    return {"type": BLOCK_SIGNATURE, "text": text}


@dataclass(frozen=True)
class CollaborationDocument:
    key: str
    version: str
    title: str
    subtitle: str
    #: Checkbox sentence, first person ("Ho letto e accetto..."): a recorded
    #: declaration, not an instruction.
    acceptance_label: str
    blocks: list[dict] = field(default_factory=list)


# =============================================================================
# The collaboration agreement (demonstration text)
# =============================================================================

# Generic placeholder shown while the real agreement is being drafted. When
# the final text arrives, replace these blocks and bump the version: past
# acceptances keep the version they signed.
_AGREEMENT_BLOCKS: list[dict] = [
    paragraph(
        "Testo dimostrativo. Questo documento sostituisce provvisoriamente il contratto di collaborazione "
        "definitivo, che SOSNET pubblicherà prima dell'avvio dell'attività. Serve a mostrare come funziona "
        "l'adesione alla rete."
    ),

    heading("1. Oggetto"),
    clause(
        "1.1.",
        "Con l'accettazione di questo documento chiedi di collaborare con SOSNET come promoter: potrai "
        "presentare ai clienti i prodotti e i servizi disponibili sulla piattaforma e far crescere la tua rete "
        "invitando nuovi collaboratori.",
    ),
    clause(
        "1.2.",
        "La collaborazione è autonoma e non crea un rapporto di lavoro dipendente, né un vincolo di esclusiva.",
    ),

    heading("2. Compensi"),
    clause(
        "2.1.",
        "Per le vendite andate a buon fine ricevi i compensi previsti dai piani provvigionali di ciascuna "
        "azienda, che trovi sempre aggiornati nella sezione «I miei piani» della tua area.",
    ),
    clause(
        "2.2.",
        "I compensi maturano quando il contratto del cliente è attivo e vengono pagati secondo le scadenze "
        "indicate nella piattaforma.",
    ),

    heading("3. Impegni"),
    bullets(
        "presentare i prodotti in modo corretto e trasparente, senza promettere condizioni diverse da quelle ufficiali;",
        "trattare i dati dei clienti solo per le finalità previste e nel rispetto della normativa sulla privacy;",
        "mantenere aggiornati i propri dati anagrafici e fiscali nella piattaforma.",
    ),

    heading("4. Durata e recesso"),
    clause(
        "4.1.",
        "La collaborazione dura a tempo indeterminato. Ciascuna delle parti può interromperla in qualsiasi "
        "momento con una comunicazione scritta; i compensi già maturati restano dovuti.",
    ),

    signature(
        "Accettando dichiari di aver letto questo documento e di volerti candidare come promoter SOSNET. "
        "La tua accettazione viene registrata con la versione del testo e la data."
    ),
]


COLLABORATION_DOCUMENTS: tuple[CollaborationDocument, ...] = (
    CollaborationDocument(
        key="CONTRACT",
        version="demo-2026.1",
        title="Accordo di collaborazione SOSNET",
        subtitle="Testo dimostrativo · versione provvisoria",
        acceptance_label="Ho letto e accetto l'accordo di collaborazione SOSNET.",
        blocks=_AGREEMENT_BLOCKS,
    ),
)


def document_by_key(key: str) -> CollaborationDocument | None:
    return next((doc for doc in COLLABORATION_DOCUMENTS if doc.key == key), None)


def required_versions() -> dict[str, str]:
    """{key: current version}: what an application must accept."""
    return {doc.key: doc.version for doc in COLLABORATION_DOCUMENTS}
