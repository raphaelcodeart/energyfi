"""Welcome bonus: each account can claim it exactly once. The guarantee rests
on the wallet transaction's unique idempotency key, so these tests focus on
repeated claims."""

import uuid

import pytest
from sqlalchemy import select

from app.foundation.security import hash_password
from app.modules.users.models import User
from app.modules.wallets import service as wallet_service
from app.modules.wallets.models import WalletTransaction


async def _make_user(db, organization_id):
    user = User(
        organization_id=organization_id, email=f"bonus-{uuid.uuid4().hex[:8]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_a_fresh_account_has_the_bonus_available_and_claiming_credits_the_wallet(db, organization_id):
    user = await _make_user(db, organization_id)
    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=user.id) is False

    txn, newly_claimed = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )

    assert newly_claimed is True
    assert txn.amount_cents == wallet_service.WELCOME_BONUS_CENTS == 2000
    assert txn.source == "WELCOME_BONUS"
    assert txn.type == "ADMIN_CREDIT"
    # Credited from no source wallet.
    assert txn.from_wallet_id is None
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == 2000
    assert txn.to_wallet_id == wallet.id


@pytest.mark.asyncio
async def test_claiming_twice_never_credits_twice(db, organization_id):
    """A repeated claim (double click, retry) is a harmless no-op."""
    user = await _make_user(db, organization_id)
    first, first_new = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )
    second, second_new = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=user.id
    )

    assert first_new is True
    assert second_new is False
    assert second.id == first.id

    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )
    assert wallet.balance_cents == 2000

    rows = (
        await db.execute(
            select(WalletTransaction).where(WalletTransaction.source == "WELCOME_BONUS")
        )
    ).scalars().all()
    assert len([r for r in rows if r.to_wallet_id == wallet.id]) == 1


@pytest.mark.asyncio
async def test_after_claiming_it_is_no_longer_available(db, organization_id):
    """Once claimed, the bonus is permanently unavailable."""
    user = await _make_user(db, organization_id)
    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=user.id)
    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=user.id) is True


@pytest.mark.asyncio
async def test_one_users_claim_does_not_consume_anothers(db, organization_id):
    """Claims are independent per user."""
    a = await _make_user(db, organization_id)
    b = await _make_user(db, organization_id)

    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=a.id)

    assert await wallet_service.has_claimed_welcome_bonus(db, user_id=b.id) is False
    _txn, newly_claimed = await wallet_service.claim_welcome_bonus(
        db, organization_id=organization_id, user_id=b.id
    )
    assert newly_claimed is True

    wallet_a = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=a.id)
    wallet_b = await wallet_service.get_wallet_by_user_id(db, organization_id=organization_id, user_id=b.id)
    assert wallet_a.balance_cents == 2000
    assert wallet_b.balance_cents == 2000


@pytest.mark.asyncio
async def test_the_bonus_shows_up_in_the_wallet_history(db, organization_id):
    """The bonus is an ordinary ledger row, visible in wallet history and
    labelled by its source."""
    user = await _make_user(db, organization_id)
    await wallet_service.claim_welcome_bonus(db, organization_id=organization_id, user_id=user.id)
    wallet = await wallet_service.get_wallet_by_user_id(
        db, organization_id=organization_id, user_id=user.id
    )

    rows = await wallet_service.list_transactions_for_wallet(
        db, organization_id=organization_id, wallet_id=wallet.id
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "WELCOME_BONUS"
    assert rows[0]["amount_cents"] == 2000
    assert rows[0]["reference_order_id"] is None
    assert rows[0]["reference_invoice_redemption_id"] is None
