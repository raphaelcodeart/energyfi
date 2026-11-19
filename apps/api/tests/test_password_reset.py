"""Password reset: requests are enumeration-safe, tokens are single-use and
expire, and a successful reset revokes all sessions."""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.security import hash_password, verify_password
from app.modules.auth import service as auth_service
from app.modules.auth.models import PasswordResetToken, Session
from app.modules.users.models import User


async def _make_user(db, organization_id, *, email="reset-target@example.com"):
    user = User(
        organization_id=organization_id, email=email, password_hash=hash_password("OldPassword123!"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_request_password_reset_for_unknown_email_does_not_raise(db, organization_id):
    # Unknown email: no exception and no observable difference.
    await auth_service.request_password_reset(
        db, organization_id=organization_id, email="nobody@example.com", ip_address=None, user_agent=None,
    )


@pytest.mark.asyncio
async def test_request_password_reset_creates_a_token_for_a_real_user(db, organization_id):
    user = await _make_user(db, organization_id)
    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=user.email, ip_address="1.2.3.4", user_agent="pytest",
    )
    from sqlalchemy import select

    tokens = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    ).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].used_at is None
    assert tokens[0].expires_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_reset_password_with_valid_token_changes_password_and_revokes_sessions(db, organization_id):
    user = await _make_user(db, organization_id)
    db.add(
        Session(
            user_id=user.id, refresh_token_hash="somehash", expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db.commit()

    from app.foundation.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await db.commit()

    await auth_service.reset_password(db, token=raw_token, new_password="BrandNewPassword456!")

    await db.refresh(user)
    assert verify_password("BrandNewPassword456!", user.password_hash)
    assert not verify_password("OldPassword123!", user.password_hash)

    from sqlalchemy import select

    sessions = (await db.execute(select(Session).where(Session.user_id == user.id))).scalars().all()
    assert all(s.revoked_at is not None for s in sessions)


@pytest.mark.asyncio
async def test_reset_password_token_is_single_use(db, organization_id):
    user = await _make_user(db, organization_id)
    from app.foundation.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await db.commit()

    await auth_service.reset_password(db, token=raw_token, new_password="FirstNewPassword1!")

    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token=raw_token, new_password="SecondNewPassword2!")


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_token(db, organization_id):
    user = await _make_user(db, organization_id)
    from app.foundation.security import generate_password_reset_token, hash_password_reset_token

    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id, token_hash=hash_password_reset_token(raw_token),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),  # expired
        )
    )
    await db.commit()

    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token=raw_token, new_password="WontBeApplied1!")


@pytest.mark.asyncio
async def test_reset_password_rejects_unknown_token(db, organization_id):
    with pytest.raises(auth_service.PasswordResetError):
        await auth_service.reset_password(db, token="not-a-real-token", new_password="WontBeApplied2!")


def _capture_sent_email(monkeypatch) -> list[dict]:
    """Capture outgoing emails. SMTP is not configured in tests, so the
    sender is patched by name on auth/service.py, where the call resolves."""
    sent: list[dict] = []
    monkeypatch.setattr(
        auth_service, "send_html_email",
        lambda **kwargs: sent.append(kwargs),
    )
    return sent


@pytest.mark.asyncio
async def test_admin_reset_email_goes_to_the_admin_account_itself(
    db, organization_id, monkeypatch
):
    """An administrator's reset email goes to that administrator and no one
    else."""
    sent = _capture_sent_email(monkeypatch)
    admin = await _make_user(db, organization_id, email="superadmin@sosnet.mamify.ai")

    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=admin.email, ip_address=None, user_agent=None,
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "superadmin@sosnet.mamify.ai"

    from sqlalchemy import select

    tokens = (
        await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == admin.id))
    ).scalars().all()
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_ordinary_user_reset_email_still_goes_to_their_own_address(db, organization_id, monkeypatch):
    sent = _capture_sent_email(monkeypatch)
    user = await _make_user(db, organization_id, email="normale@example.com")

    await auth_service.request_password_reset(
        db, organization_id=organization_id, email=user.email, ip_address=None, user_agent=None,
    )

    assert len(sent) == 1
    assert sent[0]["to"] == "normale@example.com"
