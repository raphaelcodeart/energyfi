"""Collaboration application: the applicant signs a specific, versioned text.

The legal documents are served by the backend with a version, and an
application must accept every currently required document at the exact
version shown. A signature only means something together with its wording.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.security import hash_otp_code, hash_password
from app.modules.auth import service as auth_service
from app.modules.auth.models import OtpCode
from app.modules.network import collaboration_documents
from app.modules.network import service as network_service
from app.modules.rbac.models import Role
from app.modules.referral import service as referral_service
from app.modules.users.models import User

VALID_OTP_CODE = "123456"


async def _make_applicant(db, organization_id) -> User:
    """A customer attributed to a promoter, as any applicant would be."""
    role = Role(organization_id=organization_id, code="PROMOTER", name="Promoter")
    db.add(role)
    sponsor = await network_service.create_agent(
        db, organization_id=organization_id, first_name="Sponsor", last_name="Tester",
        promoter_code=f"SP-{uuid.uuid4().hex[:8]}", parent_agent_id=None,
    )
    await referral_service.get_or_create_promoter_code(
        db, organization_id=organization_id, agent_id=sponsor.id
    )
    user = User(
        organization_id=organization_id, email=f"applicant-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("irrelevant"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _fresh_otp(db, user: User) -> str:
    """Seed a known OTP directly instead of sending one by email; OTP handling
    itself is covered in test_promoter_self_service.py."""
    db.add(
        OtpCode(
            user_id=user.id,
            purpose=auth_service.PROMOTER_APPLICATION_OTP_PURPOSE,
            code_hash=hash_otp_code(VALID_OTP_CODE),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await db.commit()
    return VALID_OTP_CODE


def test_the_agreement_lives_on_the_server_and_says_it_is_a_demo():
    """While the final agreement is drafted, one generic text is served, and
    it says plainly that it is a demonstration."""
    assert [doc.key for doc in collaboration_documents.COLLABORATION_DOCUMENTS] == ["CONTRACT"]
    agreement = collaboration_documents.document_by_key("CONTRACT")
    assert agreement is not None
    text = " ".join(
        block.get("text", "") + " ".join(block.get("items", []))
        for block in agreement.blocks
    )
    assert "dimostrativo" in agreement.subtitle.lower() and "dimostrativo" in text.lower()
    assert agreement.acceptance_label.startswith("Ho letto e accetto")
    assert any(block["type"] == "signature" for block in agreement.blocks)
    assert collaboration_documents.required_versions() == {"CONTRACT": agreement.version}


def test_no_document_talks_about_the_paper_form():
    """The on-screen text must not refer the reader to a paper original they
    have never seen."""
    for doc in collaboration_documents.COLLABORATION_DOCUMENTS:
        haystack = " ".join(
            [doc.title, doc.subtitle, doc.acceptance_label]
            + [b.get("text", "") + " ".join(b.get("items", [])) for b in doc.blocks]
        ).lower()
        for forbidden in ("cartace", "sul modulo di carta", "firma separata"):
            assert forbidden not in haystack, f"{doc.key} parla del cartaceo"


def test_no_document_carries_markup():
    """Document blocks are plain text; the dashboard never renders HTML, so
    any tag would appear literally."""
    for doc in collaboration_documents.COLLABORATION_DOCUMENTS:
        for block in doc.blocks:
            payload = block.get("text", "") + " ".join(block.get("items", []))
            assert "<" not in payload and ">" not in payload, f"markup in {doc.key}"


@pytest.mark.asyncio
async def test_applying_records_every_document_with_its_version(db, organization_id):
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    agent = await network_service.apply_as_promoter(
        db, organization_id=organization_id, user_id=user.id,
        first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
        accepted_documents=collaboration_documents.required_versions(),
    )

    recorded = agent.collaboration_accepted_documents
    assert set(recorded) == set(collaboration_documents.required_versions())
    for key, version in collaboration_documents.required_versions().items():
        assert recorded[key]["version"] == version
        assert recorded[key]["accepted_at"], "manca il momento dell'accettazione"
    assert agent.collaboration_accepted_at is not None


@pytest.mark.asyncio
async def test_missing_one_document_is_refused(db, organization_id):
    """An application that leaves out a required document is rejected."""
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    partial = collaboration_documents.required_versions()
    partial.pop("CONTRACT")

    with pytest.raises(network_service.ContractNotAcceptedError, match="Accordo di collaborazione"):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents=partial,
        )


@pytest.mark.asyncio
async def test_accepting_a_stale_version_is_refused(db, organization_id):
    """An acceptance for an outdated version is rejected rather than recorded
    against the current wording."""
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    stale = {key: "1999.0" for key in collaboration_documents.required_versions()}

    with pytest.raises(network_service.ContractNotAcceptedError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents=stale,
        )


@pytest.mark.asyncio
async def test_sending_nothing_at_all_is_refused(db, organization_id):
    user = await _make_applicant(db, organization_id)
    code = await _fresh_otp(db, user)

    with pytest.raises(network_service.ContractNotAcceptedError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code=code,
            accepted_documents={},
        )


@pytest.mark.asyncio
async def test_the_otp_is_still_required_on_top_of_the_acceptances(db, organization_id):
    """Acceptance requires the emailed OTP, proving the account holder
    agreed."""
    user = await _make_applicant(db, organization_id)

    with pytest.raises(network_service.InvalidOtpError):
        await network_service.apply_as_promoter(
            db, organization_id=organization_id, user_id=user.id,
            first_name="Nuovo", last_name="Promoter", accept_contract=True, otp_code="000000",
            accepted_documents=collaboration_documents.required_versions(),
        )
