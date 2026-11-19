import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.modules.accounting import details as accounting_details
from app.modules.accounting import service as accounting_service
from app.modules.accounting.schemas import (
    AccountingDetailRead,
    AccountingSummaryRead,
    FinancialMovementRead,
)

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("/mine", response_model=list[FinancialMovementRead])
async def get_my_movements(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """The caller's own SosnetCash and real-money movements."""
    return await accounting_service.list_my_movements(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )


@router.get("/admin", response_model=list[FinancialMovementRead])
async def get_all_movements(
    customer_user_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """All customers' movements, optionally filtered to one customer."""
    return await accounting_service.list_all_movements(
        db, organization_id=current_user.organization_id, customer_user_id=customer_user_id
    )


@router.get("/mine/summary", response_model=AccountingSummaryRead)
async def get_my_summary(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The caller's own totals: paid by card and bank transfer, SosnetCash,
    contracts, and commissions when they are also a promoter."""
    return await accounting_service.my_summary(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )


@router.get("/mine/detail", response_model=AccountingDetailRead)
async def get_my_detail(
    ref: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Detail for `ref` (wallet:/order:/redemption:/contract:<id>); anything
    not owned by the caller is reported as not found."""
    try:
        return await accounting_details.build_detail(
            db, organization_id=current_user.organization_id, ref=ref, owner_user_id=current_user.user_id
        )
    except accounting_details.DetailNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movimento non trovato.") from exc


@router.get("/admin/detail", response_model=AccountingDetailRead)
async def get_admin_detail(
    ref: str,
    current_user: CurrentUser = Depends(require_permission("wallet.manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        return await accounting_details.build_detail(
            db, organization_id=current_user.organization_id, ref=ref, owner_user_id=None
        )
    except accounting_details.DetailNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movimento non trovato.") from exc
