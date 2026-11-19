import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.organizations.schemas import OrganizationSettingsUpdate, PaymentSettingsUpdate

SETTINGS_KEYS = (
    "bank_iban", "bank_account_holder", "bank_transfer_instructions", "admin_notification_email",
    "contract_instalment_cashback_mode", "contract_full_payment_discount_percentage",
)
PAYMENT_SETTINGS_KEYS = ("stripe_publishable_key", "stripe_secret_key", "stripe_webhook_secret")

DEFAULT_ADMIN_NOTIFICATION_EMAIL = "admin@mamify.ai"

#: How a contract paid in 3 or 12 instalments earns its SosnetCash cashback,
#: chosen by the administrator in Impostazioni:
#:   PER_INSTALMENT -- a slice with every instalment collected (default);
#:   UPFRONT        -- the whole cashback once the first instalment is paid.
CASHBACK_PER_INSTALMENT = "PER_INSTALMENT"
CASHBACK_UPFRONT = "UPFRONT"
CONTRACT_INSTALMENT_CASHBACK_MODES = frozenset({CASHBACK_PER_INSTALMENT, CASHBACK_UPFRONT})


async def get_contract_instalment_cashback_mode(db: AsyncSession, *, organization_id: uuid.UUID) -> str:
    org = await db.get(Organization, organization_id)
    mode = (org.settings or {}).get("contract_instalment_cashback_mode") if org is not None else None
    return mode if mode in CONTRACT_INSTALMENT_CASHBACK_MODES else CASHBACK_PER_INSTALMENT


#: Discount on a contract paid in one go, percent of the price;
#: 3 and 12 instalments are never discounted. 0 switches it off.
DEFAULT_FULL_PAYMENT_DISCOUNT_PERCENTAGE = 32


async def get_contract_full_payment_discount_percentage(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    org = await db.get(Organization, organization_id)
    value = (org.settings or {}).get("contract_full_payment_discount_percentage") if org is not None else None
    if value is None:
        return DEFAULT_FULL_PAYMENT_DISCOUNT_PERCENTAGE
    try:
        return max(0, min(90, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_FULL_PAYMENT_DISCOUNT_PERCENTAGE


async def get_settings(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    if org is None:
        return {key: None for key in SETTINGS_KEYS}
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}


async def update_settings(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: OrganizationSettingsUpdate
) -> dict:
    """Merge into the existing settings dict, never replace it, so unrelated
    keys in the JSONB survive. Only fields present in `payload` (exclude_unset)
    are overwritten."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")

    updates = payload.model_dump(exclude_unset=True)
    # In-place mutation of a JSONB dict is not tracked by SQLAlchemy; assign a
    # new dict.
    org.settings = {**org.settings, **updates}
    await db.commit()
    await db.refresh(org)
    return {key: org.settings.get(key) for key in SETTINGS_KEYS}


async def get_stripe_secret_key(db: AsyncSession, *, organization_id: uuid.UUID) -> str | None:
    """Internal use only (checkout-session creation): the raw secret, never
    returned by an endpoint. get_payment_settings() is the masked view."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return None
    return org.settings.get("stripe_secret_key") or None


async def is_bank_transfer_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Whether "Paga con bonifico" is offered
    (orders/service.py::get_available_payment_methods()). Only the IBAN
    matters; holder name and instructions are cosmetic."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return False
    return bool(org.settings.get("bank_iban"))


async def is_stripe_configured(db: AsyncSession, *, organization_id: uuid.UUID) -> bool:
    """Whether "Paga con carta" is offered (see
    orders/service.py::get_available_payment_methods() and payments/service.py).
    Requires both the secret key (server-side Checkout Session) and the
    publishable key (client-side redirect)."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return False
    return bool(org.settings.get("stripe_secret_key")) and bool(org.settings.get("stripe_publishable_key"))


async def get_admin_notification_email(db: AsyncSession, *, organization_id: uuid.UUID) -> str:
    """Recipient of the new-ticket alert: admin-editable override of
    DEFAULT_ADMIN_NOTIFICATION_EMAIL."""
    org = await db.get(Organization, organization_id)
    if org is None:
        return DEFAULT_ADMIN_NOTIFICATION_EMAIL
    return org.settings.get("admin_notification_email") or DEFAULT_ADMIN_NOTIFICATION_EMAIL


async def get_stripe_webhook_secret(db: AsyncSession, *, organization_id: uuid.UUID) -> str | None:
    org = await db.get(Organization, organization_id)
    if org is None:
        return None
    return org.settings.get("stripe_webhook_secret") or None


async def get_payment_settings(db: AsyncSession, *, organization_id: uuid.UUID) -> dict:
    org = await db.get(Organization, organization_id)
    settings = org.settings if org else {}
    secret_key = settings.get("stripe_secret_key") or None
    return {
        "stripe_publishable_key": settings.get("stripe_publishable_key") or None,
        "stripe_secret_key_configured": secret_key is not None,
        "stripe_secret_key_last4": secret_key[-4:] if secret_key else None,
        "stripe_webhook_secret_configured": bool(settings.get("stripe_webhook_secret")),
    }


async def update_payment_settings(
    db: AsyncSession, *, organization_id: uuid.UUID, payload: PaymentSettingsUpdate
) -> dict:
    """Merges like update_settings(). An omitted field (as opposed to an empty
    one) leaves the stored secret untouched, so the form never re-sends
    unchanged secrets."""
    org = await db.get(Organization, organization_id)
    if org is None:
        raise ValueError("Organization not found")

    updates = payload.model_dump(exclude_unset=True)
    org.settings = {**org.settings, **updates}
    await db.commit()
    await db.refresh(org)
    return await get_payment_settings(db, organization_id=organization_id)


# --- Optional features ------------------------------------------------------------

#: Parts of the platform an organization can switch on or off, with their
#: default. Stored in `organizations.settings` as `feature_<name>`; an
#: organization that never touched a switch gets the default.
#:
#: - dropshipping: the CJ, Shopify and AliExpress shops;
#: - wallet: the SosnetCash wallet (balances, top-ups, transfers, paying with
#:   credits, automatic cashback);
#: - invoice_cashback: "Incassa il cashback" (invoice redemptions); needs wallet;
#: - welcome_bonus: the welcome gift in SosnetCash; needs wallet;
#: - friend_referrals: "Porta un amico", the one-level invite list and its reward;
#: - profile_gate: the fiscal code / residence form that blocks the dashboard
#:   until filled (off: the data can be filled any time in "Il mio profilo");
#: - external_wallet: the MAMIX / CASHBACK balances from the partner's wallet.
FEATURE_DEFAULTS: dict[str, bool] = {
    "dropshipping": False,
    "wallet": False,
    "invoice_cashback": False,
    "welcome_bonus": False,
    "friend_referrals": False,
    "profile_gate": False,
    "external_wallet": True,
}
FEATURES = tuple(FEATURE_DEFAULTS)
#: Features that only make sense with another one on.
FEATURE_REQUIRES: dict[str, str] = {"invoice_cashback": "wallet", "welcome_bonus": "wallet"}


async def get_features(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, bool]:
    """Effective switches: a feature whose prerequisite is off counts as off."""
    org = await db.get(Organization, organization_id)
    settings = (org.settings or {}) if org else {}
    raw = {name: bool(settings.get(f"feature_{name}", default)) for name, default in FEATURE_DEFAULTS.items()}
    return {name: on and raw.get(FEATURE_REQUIRES.get(name, name), True) for name, on in raw.items()}


async def get_feature_switches(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, bool]:
    """Switches as set, before prerequisites are applied (for the settings page)."""
    org = await db.get(Organization, organization_id)
    settings = (org.settings or {}) if org else {}
    return {name: bool(settings.get(f"feature_{name}", default)) for name, default in FEATURE_DEFAULTS.items()}


async def is_feature_enabled(db: AsyncSession, *, organization_id: uuid.UUID, name: str) -> bool:
    return (await get_features(db, organization_id=organization_id)).get(name, False)


async def update_features(
    db: AsyncSession, *, organization_id: uuid.UUID, changes: dict[str, bool], actor_user_id: uuid.UUID
) -> dict[str, bool]:
    from app.modules.audit import service as audit_service

    org = await db.get(Organization, organization_id)
    before = await get_feature_switches(db, organization_id=organization_id)
    settings = dict(org.settings or {})
    for name, enabled in changes.items():
        if name in FEATURES:
            settings[f"feature_{name}"] = bool(enabled)
    org.settings = settings
    after = await get_feature_switches(db, organization_id=organization_id)
    await audit_service.record(
        db, organization_id=organization_id, actor_user_id=actor_user_id,
        action="organization.features_updated", entity_type="organization", entity_id=str(organization_id),
        previous_value=before, new_value=after,
    )
    await db.commit()
    return after
