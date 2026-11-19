"""Reading Mamify's answers into plain values. Pure functions, no I/O.

Shapes seen on the real service API (4/11/2026):

- `rag/customer/find`: {"customer": {id, first_name, last_name, email, phone,
  registration_date, invite_code, ...}, "sponsor": {...} | null,
  "network": {"direct": n, "total": n}};
- `rag/customer/network` (scope "all"): {"customer", "sponsor", "scope",
  "total", "page", "list": [{id, first_name, last_name, email, phone,
  registration_date, level, sponsor_id, direct, total}]}, 50 rows a page,
  newest person first;
- `rag/customer/orders`: {"customer", "total", "page", "list": [{id, date,
  status ("0", "3"...), status_label, paid, total, products: [{name,
  quantity, price, type, app}], status_history}]}, newest first. The
  product lines carry no product id: they are matched to the catalog by app,
  name and price (`resolve_line`).

The readers still accept other plausible spellings (webhook bodies are not
documented field by field); what is read is kept in `raw` on the row, and the
admin page shows it, so a wrong guess is visible instead of silent.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _first(d: dict, *keys: str) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None


def ident(value: Any) -> str | None:
    """An id as a string, from a scalar or from an object carrying one."""
    if value is None or value == "" or value is False:
        return None
    if isinstance(value, dict):
        return ident(_first(value, "id", "customer_id", "id_customer", "product_id", "code"))
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text if text and text not in ("0", "None", "null") else None


def items(data: Any) -> list[dict]:
    """The list in an answer that is either a list or {"list": [...]}."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("list", "items", "data", "results", "orders", "customers", "rows"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict) and value is not data:
                inner = items(value)
                if inner:
                    return inner
    return []


def total_count(data: Any) -> int | None:
    if isinstance(data, dict):
        for key in ("total", "count", "total_count"):
            value = data.get(key)
            if isinstance(value, int | float | str) and str(value).isdigit():
                return int(value)
    return None


def money(value: Any) -> Decimal | None:
    """1234.5, "1234.50", "1.234,50", "€ 1.234,50" -> Decimal."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = "".join(ch for ch in str(value) if ch.isdigit() or ch in ",.-")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def moment(value: Any) -> datetime | None:
    """ISO strings, "YYYY-MM-DD HH:MM:SS", "DD/MM/YYYY", unix seconds."""
    if value in (None, "", 0):
        return None
    if isinstance(value, int | float) or (isinstance(value, str) and value.isdigit()):
        try:
            return datetime.fromtimestamp(int(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip().replace("Z", "+00:00")
    for parse in (
        datetime.fromisoformat,
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t, "%d/%m/%Y %H:%M"),
        lambda t: datetime.strptime(t, "%d/%m/%Y"),
    ):
        try:
            parsed = parse(text)
        except ValueError:
            continue
        # Mamify is an Italian service: a naive time is read as UTC only to
        # be stored; periods are computed from the receipt time anyway.
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _flag(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "si", "sì", "paid", "pagato")


# --- Network ----------------------------------------------------------------


@dataclass
class Member:
    customer_id: str
    sponsor_id: str | None
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    level: int | None
    registered_at: datetime | None
    raw: dict = field(default_factory=dict)


def customer_of(answer: Any) -> dict:
    """The person in an answer of rag/customer/find (or of a login)."""
    if isinstance(answer, dict) and isinstance(answer.get("customer"), dict):
        return answer["customer"]
    return answer if isinstance(answer, dict) else {}


def member(row: dict, *, parent_hint: str | None = None) -> Member | None:
    """One person of downline/list or rag/customer/network. `parent_hint` is
    the node whose children were asked for, used when the row itself does not
    say who its sponsor is."""
    customer_id = ident(_first(row, "id", "customer_id", "id_customer", "customer"))
    if customer_id is None:
        return None
    sponsor = _first(row, "upline", "upline_id", "parent", "parent_id", "sponsor", "sponsor_id", "id_parent", "referrer_id")
    level = _first(row, "level", "livello", "depth")
    try:
        level = int(level) if level is not None else None
    except (TypeError, ValueError):
        level = None
    email = _first(row, "email", "mail")
    return Member(
        customer_id=customer_id,
        sponsor_id=ident(sponsor) or parent_hint,
        first_name=str(_first(row, "name", "nome", "firstname", "first_name") or "").strip(),
        last_name=str(_first(row, "surname", "cognome", "lastname", "last_name") or "").strip(),
        email=str(email).strip().lower() if email else None,
        phone=str(_first(row, "phone", "telefono", "mobile") or "").strip() or None,
        level=level,
        registered_at=moment(_first(row, "registration_date", "date_registration", "data_registrazione", "registered_at",
                                    "created_at", "date_add", "date")),
        raw=row,
    )


def child_count(row: dict) -> int | None:
    value = _first(row, "children", "figli", "children_count")
    if isinstance(value, list):
        return len(value)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# --- Orders -----------------------------------------------------------------


@dataclass
class OrderLine:
    #: Mamify product id when the line carries one, else the one resolved
    #: from the catalog (see resolve_line), else None.
    product_id: str | None
    quantity: int
    #: Value of the whole line (unit price x quantity when only the unit is given).
    amount: Decimal | None
    name: str | None = None
    app: str | None = None
    unit_price: Decimal | None = None

    @property
    def label(self) -> str:
        """How the line is named on the admin page when it has no id."""
        if self.product_id:
            return self.product_id
        price = f" {self.unit_price}" if self.unit_price is not None else ""
        return f"{self.app or '?'} · {self.name or '?'}{price}"


@dataclass
class Order:
    order_id: str
    buyer_id: str | None
    status_code: str | None
    status_title: str | None
    paid: bool | None
    total: Decimal | None
    ordered_at: datetime | None
    lines: list[OrderLine]


def _status(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        return ident(_first(value, "id", "code", "status_id")), _first(value, "title", "name", "label")
    if value is None:
        return None, None
    text = str(value).strip()
    return (text, None) if text.isdigit() else (text.lower(), text)


def _lines(order: dict) -> list[OrderLine]:
    rows: list = []
    for key in ("products", "items", "lines", "cart", "rows", "order_products"):
        value = order.get(key)
        if isinstance(value, dict):
            value = items(value) or list(value.values())
        if isinstance(value, list) and value:
            rows = value
            break
    if not rows and order.get("product") is not None:
        rows = [order["product"] if isinstance(order["product"], dict) else {"product_id": order["product"]}]
    out = []
    for row in rows:
        if not isinstance(row, dict):
            pid = ident(row)
            if pid:
                out.append(OrderLine(pid, 1, None))
            continue
        pid = ident(_first(row, "product_id", "id_product", "product", "id"))
        name = _first(row, "name", "title", "product_name")
        if pid is None and not name:
            continue
        try:
            qty = max(1, int(_first(row, "quantity", "qty", "quantita") or 1))
        except (TypeError, ValueError):
            qty = 1
        unit = money(_first(row, "price", "prezzo", "unit_price"))
        line_total = money(_first(row, "total", "subtotal", "price_total"))
        if line_total is None and unit is not None:
            line_total = (unit * qty).quantize(Decimal("0.01"))
        app = _first(row, "app", "functionality")
        out.append(OrderLine(pid, qty, line_total, name=str(name).strip() if name else None,
                             app=str(app).strip() if app else None, unit_price=unit))
    return out


def resolve_line(line: OrderLine, catalog: list[dict]) -> str | None:
    """The Mamify product id of a line that carries only app, name and price.

    `catalog` rows are {"id", "app", "name", "price", "promo_price"}. Same app
    and same name first; when several products share the name (the yearly
    and the monthly «Pacchetto Start»), the price decides. No match, or still
    more than one, gives None: the line is then shown as not mapped rather
    than guessed.

    Mamify can move a product to another app (the 49 € «Digital Ambassador»
    went from sos-affiliate to digitalambassador): when the app no longer
    matches the copied catalog, the same name and price still identify it."""
    if line.product_id:
        return line.product_id
    if not line.name:
        return None
    name = line.name.strip().lower()
    named = [p for p in catalog if str(p.get("name") or "").strip().lower() == name]
    same = [p for p in named if not line.app or not p.get("app") or p.get("app") == line.app]
    if not same and line.unit_price is not None:
        # Moved to another app: only with the same price too.
        same = [p for p in named if line.unit_price in {money(p.get("price")), money(p.get("promo_price"))}]
    if len(same) > 1 and line.unit_price is not None:
        priced = [p for p in same if line.unit_price in {money(p.get("price")), money(p.get("promo_price"))}]
        same = priced
    return str(same[0]["id"]) if len(same) == 1 else None


def order(payload: dict, *, status_override: Any = None) -> Order | None:
    """An order from a webhook body ({"order": ..., "status": ...}), from
    rag/customer/orders or from orders/list."""
    data = payload.get("order") if isinstance(payload.get("order"), dict) else payload
    order_id = ident(_first(data, "id", "order_id", "id_order", "number"))
    if order_id is None:
        return None
    # A webhook carries the new status next to the order, which may still
    # hold the old one; that outer status wins.
    raw_status = status_override
    if raw_status is None and payload is not data:
        raw_status = payload.get("status")
    if raw_status is None:
        raw_status = _first(data, "status", "status_id", "state", "stato")
    status_code, status_title = _status(raw_status)
    if status_title is None:
        status_title = _first(data, "status_label", "status_title", "status_name")
    buyer = _first(data, "customer_id", "id_customer", "customer", "buyer_id", "client_id")
    return Order(
        order_id=order_id,
        buyer_id=ident(buyer),
        status_code=status_code,
        status_title=str(status_title) if status_title else None,
        paid=_flag(_first(data, "paid", "is_paid", "pagato", "payed")),
        total=money(_first(data, "total", "total_price", "amount", "totale", "grand_total")),
        ordered_at=moment(_first(data, "date", "created_at", "date_add", "data", "order_date")),
        lines=_lines(data),
    )


def matches_status(order_: Order, statuses: list) -> bool:
    """Whether the order's status is one of the configured ones (by id or by
    title, case-insensitive)."""
    wanted = {str(s).strip().lower() for s in statuses or [] if str(s).strip()}
    return bool(wanted & {v.strip().lower() for v in (order_.status_code, order_.status_title) if v})
