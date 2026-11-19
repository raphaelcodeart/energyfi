"""Typed access to Organization.settings (JSONB), such as the bank IBAN for
wire transfers. Updates merge into the dict: unrelated keys and omitted fields
are preserved."""

import pytest

from app.modules.organizations import service as organizations_service
from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate


@pytest.mark.asyncio
async def test_get_settings_defaults_to_none_when_nothing_set(db, organization_id):
    settings = await organizations_service.get_settings(db, organization_id=organization_id)
    assert settings == {
        "bank_iban": None,
        "bank_account_holder": None,
        "bank_transfer_instructions": None,
        "admin_notification_email": None,
        "contract_instalment_cashback_mode": None,
        "contract_full_payment_discount_percentage": None,
    }


@pytest.mark.asyncio
async def test_update_settings_merges_and_partial_update_preserves_the_rest(db, organization_id):
    org = await db.get(Organization, organization_id)
    # Unrelated key that the endpoint must preserve.
    org.settings = {**org.settings, "unrelated_future_setting": "keep-me"}
    await db.commit()

    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT60X0542811101000000123456", bank_account_holder="SOSNET Srl"),
    )
    assert updated == {
        "bank_iban": "IT60X0542811101000000123456",
        "bank_account_holder": "SOSNET Srl",
        "bank_transfer_instructions": None,
        "admin_notification_email": None,
        "contract_instalment_cashback_mode": None,
        "contract_full_payment_discount_percentage": None,
    }

    partial = await organizations_service.update_settings(
        db, organization_id=organization_id, payload=OrganizationSettingsUpdate(bank_account_holder="New Holder"),
    )
    assert partial["bank_iban"] == "IT60X0542811101000000123456"
    assert partial["bank_account_holder"] == "New Holder"

    org_after = await db.get(Organization, organization_id)
    assert org_after.settings["unrelated_future_setting"] == "keep-me"


@pytest.mark.asyncio
async def test_bank_transfer_instructions_field_merges_like_the_others(db, organization_id):
    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_iban="IT66W0883330410000000015702"),
    )
    updated = await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(bank_transfer_instructions="Includi il codice ordine nella causale."),
    )
    assert updated["bank_iban"] == "IT66W0883330410000000015702"  # omitted, so unchanged
    assert updated["bank_transfer_instructions"] == "Includi il codice ordine nella causale."


@pytest.mark.asyncio
async def test_admin_notification_email_defaults_and_can_be_overridden(db, organization_id):
    default = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    assert default == organizations_service.DEFAULT_ADMIN_NOTIFICATION_EMAIL

    await organizations_service.update_settings(
        db, organization_id=organization_id,
        payload=OrganizationSettingsUpdate(admin_notification_email="ops@sosnet.mamify.ai"),
    )
    overridden = await organizations_service.get_admin_notification_email(db, organization_id=organization_id)
    assert overridden == "ops@sosnet.mamify.ai"


@pytest.mark.asyncio
async def test_payment_settings_never_echo_the_secret_and_merge_correctly(db, organization_id):
    empty = await organizations_service.get_payment_settings(db, organization_id=organization_id)
    assert empty == {
        "stripe_publishable_key": None,
        "stripe_secret_key_configured": False,
        "stripe_secret_key_last4": None,
        "stripe_webhook_secret_configured": False,
    }

    updated = await organizations_service.update_payment_settings(
        db, organization_id=organization_id,
        payload=PaymentSettingsUpdate(
            stripe_publishable_key="pk_test_abc123",
            stripe_secret_key="sk_test_verysecretkey9999",
            stripe_webhook_secret="whsec_testsecret",
        ),
    )
    assert updated["stripe_publishable_key"] == "pk_test_abc123"  # public key, returned in full
    assert updated["stripe_secret_key_configured"] is True
    assert updated["stripe_secret_key_last4"] == "9999"  # never the full secret
    assert updated["stripe_webhook_secret_configured"] is True

    # Omitting the secret on a later PATCH keeps the stored one.
    updated2 = await organizations_service.update_payment_settings(
        db, organization_id=organization_id, payload=PaymentSettingsUpdate(stripe_publishable_key="pk_test_new"),
    )
    assert updated2["stripe_publishable_key"] == "pk_test_new"
    assert updated2["stripe_secret_key_configured"] is True
    assert updated2["stripe_secret_key_last4"] == "9999"

    raw_secret = await organizations_service.get_stripe_secret_key(db, organization_id=organization_id)
    assert raw_secret == "sk_test_verysecretkey9999"
