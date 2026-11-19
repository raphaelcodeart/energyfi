"""/external-wallet -- the signed-in person's MAMIX and MamiCash balances, read from Mamify."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user
from app.modules.external_wallet import service
from app.modules.organizations.features import require_feature

router = APIRouter(prefix="/external-wallet", tags=["external-wallet"])


@router.get("/me", dependencies=[Depends(require_feature("external_wallet"))])
async def my_balances(
    fresh: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The caller's MAMIX and MamiCash (personal and business) from Mamify;
    `connected` is false for someone who is not in the Mamify network."""
    return await service.fetch_balances(db, organization_id=current_user.organization_id,
                                        user_id=current_user.user_id, fresh=fresh)
