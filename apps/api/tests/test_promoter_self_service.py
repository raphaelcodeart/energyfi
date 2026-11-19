"""Self-service promoter application (apply_as_promoter) and the update_agent()
guard that reserves PENDING_APPROVAL -> ACTIVE for approve_agent().

Guarantees:
- a SUSPENDED agent cannot lift the suspension by re-applying;
- update_agent() (network.manage) cannot activate a PENDING_APPROVAL agent,
  so the network.approve gate cannot be bypassed."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.security import hash_otp_code, hash_password
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.network import collaboration_documents
from app.modules.network import service as network_service
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User

VALID_OTP_CODE = "123456"


async def _apply_as_promoter(db, organization_id, user_id, *, first_name, last_name):
    """apply_as_promoter() requires accepted documents and a valid OTP; seed
    the OTP directly instead of sending it by email."""
    db.add(
        OtpCode(
            user_id=user_id,
            purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()
    return await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=user_id, first_name=first_name, last_name=last_name,
        accept_contract=True, otp_code=VALID_OTP_CODE,
        # All currently required documents at their current version, derived
        # so that new documents are included automatically. Partial acceptance
        # is covered in test_collaboration_documents.py.
        accepted_documents=collaboration_documents.required_versions(),
    )


async def _get_or_create_role(db, organization_id, *, role_code: str) -> Role:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Role).where(Role.organization_id == organization_id, Role.code == role_code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    role = Role(organization_id=organization_id, code=role_code, name=role_code.title())
    db.add(role)
    await db.flush()
    return role


async def _ensure_promoter_role(db, organization_id) -> None:
    """Create the PROMOTER role, which assign_role() requires to exist."""
    await _get_or_create_role(db, organization_id, role_code="PROMOTER")
    await db.commit()


async def _make_user_with_role(db, organization_id, *, role_code: str):
    user = User(
        organization_id=organization_id, email=f"{role_code.lower()}-{uuid.uuid4().hex[:6]}@example.demo",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.flush()
    role = await _get_or_create_role(db, organization_id, role_code=role_code)
    db.add(UserRole(user_id=user.id, organization_id=organization_id, role_id=role.id))
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_apply_as_promoter_auto_activates_a_brand_new_applicant(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Nuovo", last_name="Promoter",
    )

    assert agent.status == "ACTIVE"
    assert agent.user_id == customer_user.id


@pytest.mark.asyncio
async def test_reapplying_while_suspended_requires_manual_approval_not_auto_reactivation(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Sospeso", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="SUSPENDED", current_rank_id=None, actor_user_id=admin.id,
    )

    reapplied = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Sospeso", last_name="Promoter",
    )

    assert reapplied.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_reapplying_while_terminated_and_not_blacklisted_still_auto_reactivates(db, organization_id):
    """A TERMINATED (deactivated) agent can reactivate by applying again,
    unlike a SUSPENDED one."""
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Cessato", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="TERMINATED", current_rank_id=None, actor_user_id=admin.id,
    )

    reapplied = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Cessato", last_name="Promoter",
    )

    assert reapplied.status == "ACTIVE"


@pytest.mark.asyncio
async def test_reapplying_while_blacklisted_requires_manual_approval(db, organization_id):
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")

    agent = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Blacklist", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="TERMINATED", current_rank_id=None, actor_user_id=admin.id, is_blacklisted=True,
    )

    reapplied = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Blacklist", last_name="Promoter",
    )

    assert reapplied.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_update_agent_refuses_to_activate_a_pending_approval_agent(db, organization_id):
    """PATCH /network/agents/{id} (network.manage) cannot move a
    PENDING_APPROVAL agent to ACTIVE; only approve_agent() under
    network.approve can."""
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    agent = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Suggerito", last_name="Promoter",
        promoter_code=f"SUG-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
        actor_user_id=admin.id, status="PENDING_APPROVAL",
    )

    with pytest.raises(network_service.AgentApprovalError):
        await network_service.update_agent(
            db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
            status_value="ACTIVE", current_rank_id=None, actor_user_id=admin.id,
        )


@pytest.mark.asyncio
async def test_update_agent_still_allows_reactivating_a_suspended_agent(db, organization_id):
    """Reactivation (SUSPENDED/TERMINATED -> ACTIVE) remains available under
    network.manage."""
    await _ensure_promoter_role(db, organization_id)
    admin = await _make_user_with_role(db, organization_id, role_code="ADMIN")
    customer_user = await _make_user_with_role(db, organization_id, role_code="CUSTOMER")
    agent = await _apply_as_promoter(
        db, organization_id, customer_user.id, first_name="Riattiva", last_name="Promoter",
    )
    await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="SUSPENDED", current_rank_id=None, actor_user_id=admin.id,
    )

    reactivated = await network_service.update_agent(
        db, organization_id=organization_id, agent_id=agent.id, first_name=None, last_name=None,
        status_value="ACTIVE", current_rank_id=None, actor_user_id=admin.id,
    )

    assert reactivated.status == "ACTIVE"
