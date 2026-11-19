"""Optional features: the dropshipping shops and the SosnetCash wallet are off
unless switched on, and while the wallet is off no cashback is credited."""

import uuid

import pytest
from sqlalchemy import select

from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.wallets.models import WalletTransaction


@pytest.mark.asyncio
async def test_features_are_off_by_default_and_can_be_switched(db):
    org = Organization(name=f"Fresh {uuid.uuid4()}", status="ACTIVE")
    db.add(org)
    await db.commit()
    features = await organizations_service.get_features(db, organization_id=org.id)
    assert features == organizations_service.FEATURE_DEFAULTS
    assert features["wallet"] is False and features["external_wallet"] is True

    # A feature whose prerequisite is off stays off in practice.
    await organizations_service.update_features(
        db, organization_id=org.id, changes={"welcome_bonus": True, "unknown": True}, actor_user_id=None,
    )
    assert (await organizations_service.get_features(db, organization_id=org.id))["welcome_bonus"] is False
    switches = await organizations_service.update_features(
        db, organization_id=org.id, changes={"wallet": True}, actor_user_id=None,
    )
    assert switches["wallet"] and switches["welcome_bonus"] and "unknown" not in switches
    assert (await organizations_service.get_features(db, organization_id=org.id))["welcome_bonus"] is True


@pytest.mark.asyncio
async def test_a_paid_pratica_credits_no_cashback_while_the_wallet_is_off(db, organization_id):
    from tests.test_contract_requests import _configure_bank, _sent_pratica
    from app.modules.contracts import requests as requests_service

    await organizations_service.update_features(
        db, organization_id=organization_id, changes={"wallet": False}, actor_user_id=None,
    )
    await _configure_bank(db, organization_id)
    user, _customer, request, contracts = await _sent_pratica(db, organization_id)
    await requests_service.request_bank_transfer(db, request=request, actor_user_id=user.id)
    paid = await requests_service.confirm_bank_transfer(db, request=request, actor_user_id=user.id)
    assert len(paid) == len(contracts)

    credits = (await db.execute(select(WalletTransaction).where(
        WalletTransaction.reference_contract_id.in_([c.id for c in contracts])
    ))).scalars().all()
    assert credits == []


@pytest.mark.asyncio
async def test_wallet_actions_are_refused_while_off(db, organization_id):
    from fastapi import HTTPException

    from app.foundation.deps import CurrentUser
    from app.modules.organizations.features import require_feature

    await organizations_service.update_features(
        db, organization_id=organization_id, changes={"wallet": False}, actor_user_id=None,
    )
    user = CurrentUser(user_id=uuid.uuid4(), organization_id=organization_id, roles=["CUSTOMER"])
    with pytest.raises(HTTPException) as exc:
        await require_feature("wallet")(current_user=user, db=db)
    assert exc.value.status_code == 403
