import logging
import secrets
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.email import send_html_email_best_effort
from app.foundation.email_templates import render_email
from app.modules.audit import service as audit_service
from app.modules.customers.models import Company, Customer, CustomerProfile
from app.modules.customers.service import display_name_for
from app.modules.network.models import AgentProfile
from app.modules.notifications import service as notifications_service
from app.modules.rbac import service as rbac_service
from app.modules.users.models import User
from app.modules.wallets.models import Wallet, WalletTransaction

logger = logging.getLogger(__name__)


class WalletError(Exception):
    pass


class WalletNotFoundError(WalletError):
    pass


class InsufficientBalanceError(WalletError):
    pass


class SelfTransferError(WalletError):
    pass


class TransferNotAllowedError(WalletError):
    pass


def _generate_address() -> str:
    """Crypto-style address; uniqueness is enforced by a DB constraint."""
    return f"0x{secrets.token_hex(20)}"


# One-off welcome bonus (20 SosnetCash), claimable once per account. A code
# constant rather than a setting: it mints credit not backed by real money
# (see docs/business-rules.md#internal-wallet), so changing it should require
# a deploy.
WELCOME_BONUS_CENTS = 20_00
WELCOME_BONUS_SOURCE = "WELCOME_BONUS"


def _welcome_bonus_idempotency_key(user_id: uuid.UUID) -> str:
    """Server-derived key that doubles as the "already claimed" marker: the
    unique index on idempotency_key allows at most one bonus row per user,
    even under concurrent requests, with no separate flag to drift."""
    return f"welcome-bonus:{user_id}"


async def has_claimed_welcome_bonus(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    existing = await _get_by_idempotency_key(
        db, idempotency_key=_welcome_bonus_idempotency_key(user_id)
    )
    return existing is not None


async def claim_welcome_bonus(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[WalletTransaction, bool]:
    """Returns (transaction, newly_claimed). A repeat claim returns the
    original row with newly_claimed=False instead of raising."""
    already = await has_claimed_welcome_bonus(db, user_id=user_id)
    wallet = await get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    txn = await credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=WELCOME_BONUS_CENTS,
        type_="ADMIN_CREDIT", actor_user_id=user_id, source=WELCOME_BONUS_SOURCE,
        note="Omaggio di benvenuto SOSNET",
        idempotency_key=_welcome_bonus_idempotency_key(user_id),
    )
    return txn, not already


async def get_or_create_wallet(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> Wallet:
    """Returns the user's single wallet, creating it on first access.
    Race-safe: losing the INSERT race on the unique user_id re-reads the
    winner's row."""
    wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
    if wallet is not None:
        return wallet

    wallet = Wallet(organization_id=organization_id, user_id=user_id, address=_generate_address())
    db.add(wallet)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
        if wallet is None:
            raise
        return wallet
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def get_wallet_by_user_id(db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> Wallet | None:
    stmt = select(Wallet).where(Wallet.organization_id == organization_id, Wallet.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_wallet_by_address(db: AsyncSession, *, organization_id: uuid.UUID, address: str) -> Wallet | None:
    # Addresses are globally unique, but other tenants' wallets must stay
    # invisible, so the org filter is always applied.
    stmt = select(Wallet).where(Wallet.organization_id == organization_id, Wallet.address == address)
    return (await db.execute(stmt)).scalar_one_or_none()


async def set_transfer_permission(
    db: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, can_transfer: bool
) -> Wallet:
    """Sets whether the user's wallet may send transfers, creating the
    wallet if it does not exist yet."""
    wallet = await get_or_create_wallet(db, organization_id=organization_id, user_id=user_id)
    wallet.can_transfer = can_transfer
    await db.commit()
    await db.refresh(wallet)
    return wallet


async def _get_by_idempotency_key(db: AsyncSession, *, idempotency_key: str) -> WalletTransaction | None:
    stmt = select(WalletTransaction).where(WalletTransaction.idempotency_key == idempotency_key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def credit_wallet(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    type_: str,
    actor_user_id: uuid.UUID | None,
    reference_contract_id: uuid.UUID | None = None,
    reference_invoice_redemption_id: uuid.UUID | None = None,
    reference_order_id: uuid.UUID | None = None,
    source: str | None = None,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """Credits a wallet from outside the wallet system. A plain additive
    UPDATE suffices because a credit cannot make the balance negative. A
    repeated idempotency_key returns the existing row instead of crediting
    twice."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    await db.execute(
        update(Wallet).where(Wallet.id == wallet_id).values(balance_cents=Wallet.balance_cents + amount_cents)
    )
    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=None,
        to_wallet_id=wallet_id,
        amount_cents=amount_cents,
        type=type_,
        reference_contract_id=reference_contract_id,
        reference_invoice_redemption_id=reference_invoice_redemption_id,
        reference_order_id=reference_order_id,
        source=source,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.credited", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={"to_wallet_id": str(wallet_id), "amount_cents": amount_cents, "type": type_},
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="CASHBACK_RECEIVED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"Hai ricevuto {amount_cents / 100:.2f} EUR sul tuo wallet",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)

    # Invoice-redemption and order cashback credits are announced by their
    # own flows' emails (invoice_redemptions confirm_payment, orders
    # _send_order_paid_email), so skip the generic one to avoid duplicates.
    if reference_invoice_redemption_id is None and reference_order_id is None:
        await _send_wallet_credited_email(
            db, user_id=wallet.user_id, amount_cents=amount_cents, note=note, source=source
        )
    return txn


async def _send_wallet_credited_email(
    db: AsyncSession, *, user_id: uuid.UUID, amount_cents: int, note: str | None, source: str | None = None
) -> None:
    """Best-effort notification sent after the credit is committed; email
    failures must not affect the credit. Wording depends on `source`, since
    a self-claimed welcome bonus was not credited by an admin."""
    from app.foundation.config import get_settings

    user = await db.get(User, user_id)
    if user is None:
        return

    if source == WELCOME_BONUS_SOURCE:
        heading = "Benvenuto in SOSNET!"
        preheader = "Il tuo omaggio di benvenuto è sul wallet"
        subject = "Il tuo omaggio di benvenuto - SOSNET"
        intro = "<p>Grazie per esserti registrato: ecco il tuo omaggio di benvenuto.</p>"
    else:
        heading = "Wallet ricaricato"
        preheader = "Hai ricevuto un accredito sul tuo wallet"
        subject = "Ricarica wallet - SOSNET"
        intro = "<p>Un amministratore ha accreditato manualmente il tuo wallet SOSNET.</p>"

    body_html = (
        intro
        + f'<p style="font-size:22px; font-weight:700; color:#0a54e0; margin:20px 0;">'
        f"+{amount_cents / 100:.2f} SosnetCash</p>"
    )
    if note and source != WELCOME_BONUS_SOURCE:
        body_html += f"<p><strong>Nota:</strong> {note}</p>"
    body_html += "<p>L'importo è già disponibile per i tuoi acquisti sul tuo wallet SOSNET.</p>"

    html = render_email(
        preheader=preheader,
        heading=heading,
        body_html=body_html,
        cta_label="Vai al wallet",
        cta_url=f"{get_settings().public_app_base_url}/customer?tab=wallet",
    )
    # Must never raise: the money has already moved. An error here would make
    # the admin retry with a fresh idempotency key and credit twice.
    send_html_email_best_effort(
        context=f"Wallet-credited email (user={user_id})",
        to=user.email,
        subject=subject,
        html_body=html,
        text_body=f"Il tuo wallet SOSNET è stato ricaricato di {amount_cents / 100:.2f} SosnetCash.",
    )


async def debit_and_transfer(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    from_wallet_id: uuid.UUID,
    to_address: str,
    amount_cents: int,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """Peer-to-peer transfer to an address in the same organization. The
    debit is an atomic conditional UPDATE (WHERE balance_cents >= amount)
    checked via rowcount, instead of row locking."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    from_wallet = await db.get(Wallet, from_wallet_id)
    if from_wallet is None:
        raise WalletNotFoundError("Wallet not found")
    if not from_wallet.can_transfer:
        raise TransferNotAllowedError("Il tuo account non è abilitato a inviare bonifici wallet.")

    to_wallet = await get_wallet_by_address(db, organization_id=organization_id, address=to_address)
    if to_wallet is None:
        raise WalletNotFoundError("Wallet not found")
    if to_wallet.id == from_wallet_id:
        raise SelfTransferError("Cannot send to your own wallet")

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == from_wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        # Nothing was written, so no rollback is needed (an explicit one would
        # also break the test suite's SAVEPOINT-wrapped session).
        raise InsufficientBalanceError("Insufficient balance")

    await db.execute(
        update(Wallet).where(Wallet.id == to_wallet.id).values(balance_cents=Wallet.balance_cents + amount_cents)
    )

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet.id,
        amount_cents=amount_cents,
        type="TRANSFER",
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.transferred", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(from_wallet_id), "to_wallet_id": str(to_wallet.id), "amount_cents": amount_cents,
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=to_wallet.user_id, type_="WALLET_TRANSFER_RECEIVED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"Hai ricevuto {amount_cents / 100:.2f} EUR sul tuo wallet",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_wallet_for_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """Spends wallet credit on an order (PURCHASE_DEBIT, to_wallet_id NULL).
    Unlike a credit, a debit needs the atomic balance guard. Idempotent on
    idempotency_key.

    The debit_wallet_for_*_purchase siblings below are identical except for
    which order table the row references."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_order_id=reference_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={"from_wallet_id": str(wallet_id), "amount_cents": amount_cents, "reference_order_id": str(reference_order_id)},
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_wallet_for_imported_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_imported_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """debit_wallet_for_purchase for imported-product orders."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_imported_order_id=reference_imported_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(wallet_id), "amount_cents": amount_cents,
            "reference_imported_order_id": str(reference_imported_order_id),
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn



async def debit_wallet_for_cj_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_cj_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """debit_wallet_for_purchase for CJ dropshipping orders."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_cj_order_id=reference_cj_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(wallet_id), "amount_cents": amount_cents,
            "reference_cj_order_id": str(reference_cj_order_id),
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_wallet_for_shopify_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_shopify_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """debit_wallet_for_purchase for Shopify orders."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_shopify_order_id=reference_shopify_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(wallet_id), "amount_cents": amount_cents,
            "reference_shopify_order_id": str(reference_shopify_order_id),
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_wallet_for_aliexpress_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_aliexpress_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """debit_wallet_for_purchase for AliExpress DS API orders."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_aliexpress_order_id=reference_aliexpress_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(wallet_id), "amount_cents": amount_cents,
            "reference_aliexpress_order_id": str(reference_aliexpress_order_id),
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def debit_wallet_for_sosnet_market_purchase(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    wallet_id: uuid.UUID,
    amount_cents: int,
    reference_sosnet_market_order_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: str | None = None,
    idempotency_key: str,
) -> WalletTransaction:
    """debit_wallet_for_purchase for Sosnet Market grocery orders."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    result = await db.execute(
        update(Wallet)
        .where(Wallet.id == wallet_id, Wallet.balance_cents >= amount_cents)
        .values(balance_cents=Wallet.balance_cents - amount_cents)
    )
    if result.rowcount == 0:
        raise InsufficientBalanceError("Insufficient balance")

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=wallet_id,
        to_wallet_id=None,
        amount_cents=amount_cents,
        type="PURCHASE_DEBIT",
        reference_sosnet_market_order_id=reference_sosnet_market_order_id,
        note=note,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent request with the same idempotency key (or a stale
        # reference id) fails here; replay the winning row instead of a 500.
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise

    wallet = await db.get(Wallet, wallet_id)
    assert wallet is not None
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.debited_for_purchase", entity_type="wallet_transaction", entity_id=str(txn.id),
        new_value={
            "from_wallet_id": str(wallet_id), "amount_cents": amount_cents,
            "reference_sosnet_market_order_id": str(reference_sosnet_market_order_id),
        },
    )
    await notifications_service.notify_user(
        db, organization_id=organization_id, user_id=wallet.user_id, type_="ORDER_CREDIT_APPLIED",
        entity_type="wallet_transaction", entity_id=txn.id,
        title=f"{amount_cents / 100:.2f} EUR di credito usati per un tuo ordine",
        body=note,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn

async def reverse_transaction(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    transaction_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    reason: str,
    idempotency_key: str,
) -> WalletTransaction:
    """Admin correction: inserts a REVERSAL row and never mutates the
    original. A REVERSAL cannot itself be reversed. Reversing a TRANSFER
    re-debits the recipient and fails with InsufficientBalanceError if the
    funds are gone (accepted behaviour, see
    docs/business-rules.md#internal-wallet). Reversing a PURCHASE_DEBIT just
    refunds the buyer."""
    existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
    if existing is not None:
        return existing

    original = await db.get(WalletTransaction, transaction_id)
    if original is None or original.organization_id != organization_id:
        raise WalletNotFoundError("Transaction not found")
    if original.type == "REVERSAL":
        raise WalletError("Cannot reverse a REVERSAL")

    # Debit the original recipient (if any), credit the original source (if any).
    if original.to_wallet_id is not None:
        result = await db.execute(
            update(Wallet)
            .where(Wallet.id == original.to_wallet_id, Wallet.balance_cents >= original.amount_cents)
            .values(balance_cents=Wallet.balance_cents - original.amount_cents)
        )
        if result.rowcount == 0:
            # Nothing written yet; no rollback needed.
            raise InsufficientBalanceError("Insufficient balance to reverse this transaction")

    if original.from_wallet_id is not None:
        await db.execute(
            update(Wallet)
            .where(Wallet.id == original.from_wallet_id)
            .values(balance_cents=Wallet.balance_cents + original.amount_cents)
        )

    txn = WalletTransaction(
        organization_id=organization_id,
        from_wallet_id=original.to_wallet_id,
        # Sides are swapped; an ADMIN_CREDIT reversal therefore has no target.
        to_wallet_id=original.from_wallet_id,
        amount_cents=original.amount_cents,
        type="REVERSAL",
        reverses_transaction_id=original.id,
        note=reason,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    await db.flush()

    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="wallet.reversed", entity_type="wallet_transaction", entity_id=str(txn.id),
        previous_value={"reverses_transaction_id": str(original.id)},
        new_value={"amount_cents": original.amount_cents, "reason": reason},
        reason=reason,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await _get_by_idempotency_key(db, idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        raise
    await db.refresh(txn)
    return txn


async def _resolve_display_names(
    db: AsyncSession, *, organization_id: uuid.UUID, user_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Display name per user_id: promoter display name first, then the
    customer's person/company name, falling back to the email."""
    if not user_ids:
        return {}

    names: dict[uuid.UUID, str] = {}

    agents = (
        await db.execute(
            select(AgentProfile.user_id, AgentProfile.display_name).where(
                AgentProfile.organization_id == organization_id, AgentProfile.user_id.in_(user_ids)
            )
        )
    ).all()
    for user_id, display_name in agents:
        names[user_id] = display_name

    remaining = user_ids - names.keys()
    if remaining:
        customers = (
            await db.execute(
                select(Customer).where(Customer.organization_id == organization_id, Customer.user_id.in_(remaining))
            )
        ).scalars().all()
        if customers:
            customer_ids = [c.id for c in customers]
            profiles = {
                p.customer_id: p
                for p in (
                    await db.execute(select(CustomerProfile).where(CustomerProfile.customer_id.in_(customer_ids)))
                ).scalars()
            }
            companies = {
                c.customer_id: c
                for c in (
                    await db.execute(select(Company).where(Company.customer_id.in_(customer_ids)))
                ).scalars()
            }
            for customer in customers:
                if customer.user_id is None:  # excluded by the query; keeps the type checker happy
                    continue
                names[customer.user_id] = display_name_for(
                    customer.kind, profiles.get(customer.id), companies.get(customer.id)
                )

    remaining = user_ids - names.keys()
    if remaining:
        users = (await db.execute(select(User.id, User.email).where(User.id.in_(remaining)))).all()
        for user_id, email in users:
            names[user_id] = email

    return names


def _to_transaction_dict(txn: WalletTransaction, wallets_by_id: dict[uuid.UUID, Wallet], names: dict[uuid.UUID, str]) -> dict:
    from_wallet = wallets_by_id.get(txn.from_wallet_id) if txn.from_wallet_id else None
    to_wallet = wallets_by_id.get(txn.to_wallet_id) if txn.to_wallet_id else None
    return {
        "id": txn.id,
        "from_wallet_id": txn.from_wallet_id,
        "from_address": from_wallet.address if from_wallet else None,
        "from_display_name": names.get(from_wallet.user_id) if from_wallet else None,
        # from_user_id/to_user_id are not in WalletTransactionRead (ignored
        # there); accounting uses them to attribute rows without extra lookups.
        "from_user_id": from_wallet.user_id if from_wallet else None,
        "to_wallet_id": txn.to_wallet_id,
        "to_address": to_wallet.address if to_wallet else None,
        "to_display_name": names.get(to_wallet.user_id) if to_wallet else None,
        "to_user_id": to_wallet.user_id if to_wallet else None,
        "amount_cents": txn.amount_cents,
        "currency": txn.currency,
        "type": txn.type,
        "source": txn.source,
        "reference_contract_id": txn.reference_contract_id,
        "reference_invoice_redemption_id": txn.reference_invoice_redemption_id,
        "reference_order_id": txn.reference_order_id,
        "reference_imported_order_id": txn.reference_imported_order_id,
        "reference_cj_order_id": txn.reference_cj_order_id,
        "reference_shopify_order_id": txn.reference_shopify_order_id,
        "reference_aliexpress_order_id": txn.reference_aliexpress_order_id,
        "reverses_transaction_id": txn.reverses_transaction_id,
        "note": txn.note,
        "actor_user_id": txn.actor_user_id,
        "created_at": txn.created_at,
    }


async def hydrate_transactions(db: AsyncSession, *, organization_id: uuid.UUID, transactions: list[WalletTransaction]) -> list[dict]:
    if not transactions:
        return []

    wallet_ids: set[uuid.UUID] = set()
    for txn in transactions:
        if txn.from_wallet_id:
            wallet_ids.add(txn.from_wallet_id)
        if txn.to_wallet_id:
            wallet_ids.add(txn.to_wallet_id)

    wallets = (await db.execute(select(Wallet).where(Wallet.id.in_(wallet_ids)))).scalars().all()
    wallets_by_id = {w.id: w for w in wallets}
    names = await _resolve_display_names(
        db, organization_id=organization_id, user_ids={w.user_id for w in wallets}
    )
    return [_to_transaction_dict(txn, wallets_by_id, names) for txn in transactions]


async def list_transactions_for_wallet(
    db: AsyncSession, *, organization_id: uuid.UUID, wallet_id: uuid.UUID, limit: int = 100
) -> list[dict]:
    stmt = (
        select(WalletTransaction)
        .where(
            WalletTransaction.organization_id == organization_id,
            (WalletTransaction.from_wallet_id == wallet_id) | (WalletTransaction.to_wallet_id == wallet_id),
        )
        .order_by(WalletTransaction.created_at.desc())
        .limit(limit)
    )
    transactions = (await db.execute(stmt)).scalars().all()
    return await hydrate_transactions(db, organization_id=organization_id, transactions=list(transactions))


async def list_all_transactions_for_org(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    type_: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = 500,
) -> list[dict]:
    stmt = select(WalletTransaction).where(WalletTransaction.organization_id == organization_id)
    if type_ is not None:
        stmt = stmt.where(WalletTransaction.type == type_)
    if user_id is not None:
        wallet = await get_wallet_by_user_id(db, organization_id=organization_id, user_id=user_id)
        wallet_id = wallet.id if wallet is not None else uuid.uuid4()  # no match, never equal to a real row
        stmt = stmt.where(
            (WalletTransaction.from_wallet_id == wallet_id) | (WalletTransaction.to_wallet_id == wallet_id)
        )
    stmt = stmt.order_by(WalletTransaction.created_at.desc()).limit(limit)
    transactions = (await db.execute(stmt)).scalars().all()
    return await hydrate_transactions(db, organization_id=organization_id, transactions=list(transactions))


async def list_all_wallets_for_org(db: AsyncSession, *, organization_id: uuid.UUID) -> list[dict]:
    wallets = (
        await db.execute(
            select(Wallet).where(Wallet.organization_id == organization_id).order_by(Wallet.created_at.desc())
        )
    ).scalars().all()
    if not wallets:
        return []

    names = await _resolve_display_names(db, organization_id=organization_id, user_ids={w.user_id for w in wallets})
    users = (
        await db.execute(select(User.id, User.email).where(User.id.in_([w.user_id for w in wallets])))
    ).all()
    emails: dict[uuid.UUID, str] = dict(users)  # type: ignore[arg-type]

    result = []
    for wallet in wallets:
        roles = await rbac_service.get_roles_for_user(db, user_id=wallet.user_id, organization_id=organization_id)
        result.append(
            {
                "id": wallet.id,
                "user_id": wallet.user_id,
                "address": wallet.address,
                "balance_cents": wallet.balance_cents,
                "currency": wallet.currency,
                "can_transfer": wallet.can_transfer,
                "created_at": wallet.created_at,
                "owner_display_name": names.get(wallet.user_id, "—"),
                "owner_email": emails.get(wallet.user_id, "—"),
                "owner_roles": roles,
            }
        )
    return result
