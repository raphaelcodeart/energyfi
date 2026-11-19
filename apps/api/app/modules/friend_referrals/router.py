import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.foundation.db import get_db
from app.foundation.deps import CurrentUser, get_current_user, require_permission
from app.foundation.rate_limit import rate_limit
from app.modules.organizations.features import require_feature
from app.modules.friend_referrals import service as friend_referrals_service
from app.modules.friend_referrals.schemas import (
    FriendReferralAdminClaimRead,
    FriendReferralClaimUpdate,
    FriendReferralSummaryRead,
)

router = APIRouter(prefix="/friend-referrals", tags=["friend-referrals"])


@router.get("/me", response_model=FriendReferralSummaryRead)
async def get_my_friend_referrals(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FriendReferralSummaryRead:
    """The caller's own one-level referral list; authentication only, user id
    taken from the session."""
    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return FriendReferralSummaryRead(**summary)


@router.post(
    "/me/reward-claims", response_model=FriendReferralSummaryRead, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_feature("friend_referrals"))],
)
async def request_my_reward(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limit("friend-referral-reward", max_requests=10, window_seconds=300)),
) -> FriendReferralSummaryRead:
    """Request the gift for the next milestone, recomputed server-side from
    stored referrals; the client never names the milestone."""
    try:
        await friend_referrals_service.request_reward(
            db, organization_id=current_user.organization_id, user_id=current_user.user_id
        )
    except friend_referrals_service.FriendReferralError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    summary = await friend_referrals_service.get_my_summary(
        db, organization_id=current_user.organization_id, user_id=current_user.user_id
    )
    return FriendReferralSummaryRead(**summary)


@router.get("/admin/reward-claims", response_model=list[FriendReferralAdminClaimRead])
async def list_reward_claims(
    status_filter: str = "REQUESTED",
    current_user: CurrentUser = Depends(require_permission("customers.read")),
    db: AsyncSession = Depends(get_db),
) -> list[FriendReferralAdminClaimRead]:
    """Gated on customers.read: customer requests are the same tier of
    information the customer screens already expose."""
    rows = await friend_referrals_service.list_claims(
        db, organization_id=current_user.organization_id, status=status_filter
    )
    return [FriendReferralAdminClaimRead(**row) for row in rows]


@router.patch("/admin/reward-claims/{claim_id}", response_model=FriendReferralAdminClaimRead)
async def handle_reward_claim(
    claim_id: uuid.UUID,
    payload: FriendReferralClaimUpdate,
    current_user: CurrentUser = Depends(require_permission("customers.update")),
    db: AsyncSession = Depends(get_db),
) -> FriendReferralAdminClaimRead:
    claim = await friend_referrals_service.handle_claim(
        db, organization_id=current_user.organization_id, claim_id=claim_id,
        status=payload.status, note=payload.note, actor_user_id=current_user.user_id,
    )
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata")
    rows = await friend_referrals_service.list_claims(
        db, organization_id=current_user.organization_id, status="ALL"
    )
    row = next((r for r in rows if r["id"] == claim.id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Richiesta non trovata")
    return FriendReferralAdminClaimRead(**row)
