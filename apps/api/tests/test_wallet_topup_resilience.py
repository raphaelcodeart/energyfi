"""A successful wallet credit is never reported as failed.

The credit is committed before a courtesy email is sent, so any mail failure
(refused login, timeout, DNS or TLS error) must be swallowed rather than
turned into an error on an operation that already succeeded. Retrying with the
same idempotency key must never credit the wallet twice.
"""

import smtplib
import uuid

import pytest

from app.foundation import email as email_module
from app.foundation.security import hash_password
from app.modules.users.models import User
from app.modules.wallets import service as wallets_service


def _break_smtp(monkeypatch, failure: Exception) -> None:
    """Make SMTP fail at `smtplib.SMTP` itself, so any code path that really
    sends mail hits the failure regardless of how it imports its helpers.

    The test settings leave smtp_host empty, which would short-circuit with
    EmailNotConfiguredError, so a host is set first."""
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.invalid.test")

    def _explode(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(email_module.smtplib, "SMTP", _explode)


async def _make_user(db, organization_id) -> User:
    user = User(
        organization_id=organization_id, email=f"topup-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPAuthenticationError(535, b"authentication failed"),
        smtplib.SMTPServerDisconnected("connection closed"),
        TimeoutError("timed out"),
        ConnectionRefusedError("connection refused"),
    ],
    ids=["auth-refused", "server-disconnected", "timeout", "connection-refused"],
)
@pytest.mark.asyncio
async def test_a_wallet_topup_survives_any_smtp_failure(db, organization_id, monkeypatch, failure):
    user = await _make_user(db, organization_id)
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )

    _break_smtp(monkeypatch, failure)

    txn = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=406_26,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="1a Tranche Corso", idempotency_key=f"topup-{uuid.uuid4()}",
    )

    assert txn.amount_cents == 406_26
    await db.refresh(wallet)
    assert wallet.balance_cents == 406_26


@pytest.mark.asyncio
async def test_retrying_the_same_topup_key_never_doubles_the_balance(db, organization_id, monkeypatch):
    """Retrying a top-up with the same idempotency key is a no-op. The
    dashboard keeps one key per top-up until it succeeds."""
    user = await _make_user(db, organization_id)
    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )

    _break_smtp(monkeypatch, smtplib.SMTPException("relay temporarily unavailable"))

    key = f"topup-{uuid.uuid4()}"
    first = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=50_00,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="Ricarica", idempotency_key=key,
    )
    second = await wallets_service.credit_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id, amount_cents=50_00,
        type_="ADMIN_CREDIT", actor_user_id=user.id, source="MANUAL_ADMIN",
        note="Ricarica", idempotency_key=key,
    )

    assert second.id == first.id
    await db.refresh(wallet)
    assert wallet.balance_cents == 50_00


@pytest.mark.asyncio
async def test_the_welcome_bonus_also_survives_a_broken_mail_server(db, organization_id, monkeypatch):
    """Claiming the welcome bonus also succeeds when email sending fails."""
    user = await _make_user(db, organization_id)

    _break_smtp(monkeypatch, smtplib.SMTPException("greylisted"))

    txn, newly_claimed = await wallets_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )
    assert newly_claimed is True
    assert txn.amount_cents == wallets_service.WELCOME_BONUS_CENTS

    wallet = await wallets_service.get_or_create_wallet(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == wallets_service.WELCOME_BONUS_CENTS
