"""/marketplaces -- the rules shared by the imported-product shops."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.marketplaces import rules

router = APIRouter(prefix="/marketplaces", tags=["marketplaces"])


class ShopSectionRead(BaseModel):
    label: str
    enabled: bool


class ShopSectionUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=40)
    enabled: bool | None = None


class MarketplaceConfigRead(BaseModel):
    labels: dict[str, str]
    #: The Shop's own sections (internal / partner / dropshipping).
    sections: dict[str, ShopSectionRead]
    bank_transfer_discount_percentage: int
    #: VAT rate added on top of the displayed (net) prices.
    vat_percentage: int
    default_credit_percentage: int
    max_credit_percentage: int


class MarketplaceConfigUpdate(BaseModel):
    labels: dict[str, str] | None = None
    sections: dict[str, ShopSectionUpdate] | None = None
    bank_transfer_discount_percentage: int | None = Field(default=None, ge=0, le=rules.MAX_BANK_TRANSFER_DISCOUNT_PERCENTAGE)
    vat_percentage: int | None = Field(default=None, ge=0, le=rules.MAX_VAT_PERCENTAGE)


@router.get("/config", response_model=MarketplaceConfigRead)
async def get_marketplace_config(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceConfigRead:
    """Open to every logged-in user: the Shop needs tab names, the
    bank-transfer discount and the VAT rate to render prices."""
    return MarketplaceConfigRead(**await rules.get_config(db, organization_id=current_user.organization_id))


@router.patch("/config", response_model=MarketplaceConfigRead)
async def update_marketplace_config(
    payload: MarketplaceConfigUpdate,
    current_user: CurrentUser = Depends(require_permission("products.manage")),
    db: AsyncSession = Depends(get_db),
) -> MarketplaceConfigRead:
    return MarketplaceConfigRead(
        **await rules.update_config(
            db, organization_id=current_user.organization_id, labels=payload.labels,
            bank_transfer_discount_percentage=payload.bank_transfer_discount_percentage,
            vat_percentage=payload.vat_percentage,
            sections=(
                {k: v.model_dump(exclude_unset=True) for k, v in payload.sections.items()}
                if payload.sections is not None
                else None
            ),
        )
    )
