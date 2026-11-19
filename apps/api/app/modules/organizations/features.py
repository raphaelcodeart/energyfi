"""FastAPI guard for the optional features (organizations/service.py::FEATURES)."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user
from app.modules.organizations import service as organizations_service

MESSAGES = {
    "wallet": "Il portafoglio SosnetCash non è attivo.",
    "dropshipping": "Questo negozio non è attivo.",
    "invoice_cashback": "Il riscatto del cashback non è attivo.",
    "welcome_bonus": "L'omaggio di benvenuto non è attivo.",
    "friend_referrals": "«Porta un amico» non è attivo.",
    "external_wallet": "I saldi MAMIX e CASHBACK non sono attivi.",
}


def require_feature(name: str):
    """Router dependency: 404-like refusal while the feature is switched off,
    so hidden parts cannot be reached by calling the API directly."""

    async def _checker(
        current_user: CurrentUser = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if not await organizations_service.is_feature_enabled(
            db, organization_id=current_user.organization_id, name=name
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, MESSAGES.get(name, "Funzione non attiva."))

    return _checker
