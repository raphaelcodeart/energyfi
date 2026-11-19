from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.organizations import service as organizations_service
from app.modules.organizations.schemas import (
    OrganizationSettingsRead,
    OrganizationSettingsUpdate,
    PaymentSettingsRead,
    PaymentSettingsUpdate,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me/settings", response_model=OrganizationSettingsRead)
async def get_my_organization_settings(
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsRead:
    settings = await organizations_service.get_settings(db, organization_id=current_user.organization_id)
    return OrganizationSettingsRead(**settings)


@router.patch("/me/settings", response_model=OrganizationSettingsRead)
async def update_my_organization_settings(
    payload: OrganizationSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> OrganizationSettingsRead:
    settings = await organizations_service.update_settings(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return OrganizationSettingsRead(**settings)


@router.get("/me/payment-settings", response_model=PaymentSettingsRead)
async def get_my_payment_settings(
    current_user: CurrentUser = Depends(require_permission("organization.manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> PaymentSettingsRead:
    """Stripe configuration, gated on organization.manage_payments (SUPER_ADMIN
    only), stricter than the bank settings: card-payment control is kept to a
    smaller circle than bank-transfer details."""
    settings = await organizations_service.get_payment_settings(db, organization_id=current_user.organization_id)
    return PaymentSettingsRead(**settings)


@router.patch("/me/payment-settings", response_model=PaymentSettingsRead)
async def update_my_payment_settings(
    payload: PaymentSettingsUpdate,
    current_user: CurrentUser = Depends(require_permission("organization.manage_payments")),
    db: AsyncSession = Depends(get_db),
) -> PaymentSettingsRead:
    settings = await organizations_service.update_payment_settings(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return PaymentSettingsRead(**settings)


@router.get("/me/features")
async def get_my_features(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Which optional parts of the platform are on (prerequisites applied);
    every area reads it to show or hide them."""
    return await organizations_service.get_features(db, organization_id=current_user.organization_id)


@router.get("/me/features/switches")
async def get_my_feature_switches(
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The switches as set, their defaults and prerequisites, for Impostazioni → Funzioni."""
    return {
        "switches": await organizations_service.get_feature_switches(db, organization_id=current_user.organization_id),
        "defaults": organizations_service.FEATURE_DEFAULTS,
        "requires": organizations_service.FEATURE_REQUIRES,
    }


@router.patch("/me/features")
async def update_my_features(
    payload: dict[str, bool],
    current_user: CurrentUser = Depends(require_permission("organization.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    return await organizations_service.update_features(
        db, organization_id=current_user.organization_id, changes=payload, actor_user_id=current_user.user_id,
    )
