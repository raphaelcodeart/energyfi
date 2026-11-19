import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.modules.payments import service as payments_service

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/stripe/webhook/{organization_id}")
async def stripe_webhook(
    organization_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    """Unauthenticated by design: the Stripe signature, verified against
    this organization's own webhook secret, is the authentication. The
    organization_id in the path lets one endpoint serve every tenant."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        await payments_service.handle_webhook_event(
            db, organization_id=organization_id, payload=payload, sig_header=sig_header
        )
    except payments_service.StripeNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except payments_service.WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {"received": True}
